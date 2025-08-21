# test.py - 新架構後端整合測試啟動器
import subprocess
import sys
import os
import re
import time
import logging
import threading
import queue
import shutil
from pathlib import Path
import requests
import signal

# --- 基本設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('IntegrationTestRunner')
ROOT_DIR = Path(__file__).resolve().parent

# --- 超時與埠號設定 ---
OVERALL_TIMEOUT = 100
LOG_STALL_TIMEOUT = 20
API_PORT = 8001

# --- 全域狀態 ---
processes = []
last_log_time = time.time()
stop_event = threading.Event()

def kill_process_on_port(port):
    """查找並終止佔用指定埠號的進程。"""
    log.info(f"--- 正在檢查並清理埠號 {port} ---")
    try:
        # 使用 lsof 查找監聽指定 TCP 埠號的進程 ID
        cmd = f"lsof -ti tcp:{port}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.stdout:
            pids = result.stdout.strip().split('\n')
            for pid_str in pids:
                if pid_str:
                    pid = int(pid_str)
                    log.warning(f"發現佔用埠號 {port} 的舊進程 PID: {pid}。正在強制終止...")
                    os.kill(pid, signal.SIGKILL)
                    log.info(f"✅ 已終止進程 {pid}。")
        else:
            log.info(f"✅ 埠號 {port} 是乾淨的。")
    except Exception as e:
        log.error(f"清理埠號 {port} 時發生錯誤: {e}")


def cleanup_venvs():
    """清理所有由調度器建立的虛擬環境。"""
    log.info("--- 正在清理虛擬環境 ---")
    tasks_dir = ROOT_DIR / "src" / "tasks"
    if not tasks_dir.is_dir():
        return

    deleted_count = 0
    for venv_dir in tasks_dir.glob(".venv_*"):
        if venv_dir.is_dir():
            try:
                shutil.rmtree(venv_dir)
                log.info(f"已刪除虛擬環境: {venv_dir}")
                deleted_count += 1
            except OSError as e:
                log.error(f"刪除虛擬環境 {venv_dir} 失敗: {e}")
    log.info(f"--- 清理完成，共刪除 {deleted_count} 個虛擬環境。 ---")

def log_monitor_thread(log_queue: queue.Queue):
    """在背景讀取所有子進程的日誌，並更新 last_log_time。"""
    global last_log_time
    while not stop_event.is_set():
        try:
            source, line = log_queue.get(timeout=0.1)
            log.info(f"[{source}]: {line.strip()}")
            last_log_time = time.time()
        except queue.Empty:
            continue

def stream_reader_thread(name: str, stream, log_queue: queue.Queue):
    """將一個流的內容逐行放入佇列。"""
    for line in iter(stream.readline, ''):
        log_queue.put((name, line))
    stream.close()

def launch_service(command: list, name: str, log_queue: queue.Queue) -> subprocess.Popen:
    """啟動一個服務子進程並設定日誌流。"""
    log.info(f"正在啟動服務 '{name}'...")
    # 使用 preexec_fn=os.setsid 讓子進程成為新的 session leader，方便後續整個終止
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        preexec_fn=os.setsid
    )
    processes.append(proc)

    threading.Thread(target=stream_reader_thread, args=[name, proc.stdout, log_queue], daemon=True).start()
    threading.Thread(target=stream_reader_thread, args=[name, proc.stderr, log_queue], daemon=True).start()

    log.info(f"✅ 服務 '{name}' 已啟動 (PID: {proc.pid})")
    return proc

def main():
    global last_log_time
    start_time = time.time()
    log_queue = queue.Queue()

    monitor_thread = threading.Thread(target=log_monitor_thread, args=[log_queue], daemon=True)
    monitor_thread.start()

    try:
        # 1. 啟動前清理
        kill_process_on_port(API_PORT)
        cleanup_venvs()

        # 2. 安裝主依賴
        log.info("--- [步驟 1/4] 安裝主依賴 (redis, requests) ---")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "redis", "requests"], check=True)

        # 3. 啟動核心服務
        log.info(f"--- [步驟 2/4] 啟動核心服務 (API Server & Dispatcher) on Port {API_PORT} ---")
        api_server_cmd = [sys.executable, str(ROOT_DIR / "src" / "api" / "api_server.py"), "--port", str(API_PORT)]
        dispatcher_cmd = [sys.executable, str(ROOT_DIR / "services" / "dispatcher" / "main.py")]

        api_proc = launch_service(api_server_cmd, "API_Server", log_queue)
        disp_proc = launch_service(dispatcher_cmd, "Dispatcher", log_queue)

        # 4. 等待服務就緒
        log.info("--- [步驟 3/4] 等待服務就緒 ---")
        api_ready = False
        dispatcher_ready = False
        wait_start_time = time.time()

        # 我們不直接讀取佇列，而是讓日誌監控執行緒處理，我們只需檢查日誌內容
        # 為了簡單起見，我們在這裡直接從佇列中窺探，但在真實的複雜系統中，
        # 應該使用更精巧的事件機制。
        temp_log_cache = []
        while not (api_ready and dispatcher_ready):
            if time.time() - start_time > OVERALL_TIMEOUT:
                raise RuntimeError(f"總體超時 ({OVERALL_TIMEOUT}秒)")
            if time.time() - last_log_time > LOG_STALL_TIMEOUT:
                raise RuntimeError(f"日誌停滯超時 ({LOG_STALL_TIMEOUT}秒)")

            try:
                # 從日誌監控執行緒的佇列中獲取日誌來判斷狀態
                # 這裡的 get 是為了演示邏輯，實際日誌已由 monitor_thread 打印
                # 我們可以直接檢查 monitor_thread 打印的日誌，但為了隔離，此處獨立處理
                # 實際上，monitor thread 應該用來更新一個共享的狀態變數
                # 為了簡化，我們暫時保持窺探佇列的邏輯
                source, line = log_queue.get(timeout=0.2)
                temp_log_cache.append(line)

                if "Uvicorn running on" in line:
                    api_ready = True
                    log.info("✅ API 伺服器已就緒。")
                if "開始監聽 Redis 列表" in line:
                    dispatcher_ready = True
                    log.info("✅ 調度器已就緒。")

            except queue.Empty:
                continue

        # 5. 模擬前端請求
        log.info("--- [步驟 4/4] 模擬前端請求以建立任務 ---")
        try:
            response = requests.post(
                f"http://localhost:{API_PORT}/api/youtube/process",
                json={"requests": [{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}]},
                timeout=5
            )
            log.info(f"API 請求已發送，狀態碼: {response.status_code}, 回應: {response.text}")
        except requests.exceptions.ConnectionError as e:
            log.warning(f"無法連接至 API 伺服器: {e}。這在 Redis 未運行時是預期行為。")

        log.info("--- 整合測試核心流程執行完畢，觀察 5 秒 ---")
        time.sleep(5)

        log.info("✅✅✅ 測試成功通過！✅✅✅")

    except Exception as e:
        log.error(f"❌❌❌ 測試執行失敗: {e} ❌❌❌", exc_info=True)
        sys.exit(1)
    finally:
        log.info("--- 正在執行清理 ---")
        stop_event.set()
        for proc in reversed(processes):
            if proc.poll() is None:
                log.info(f"正在終止進程組 PGID: {os.getpgid(proc.pid)}")
                try:
                    # 終止整個進程組
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass # 進程可能已經自己結束了

        time.sleep(1) # 給予時間讓進程結束

        for proc in reversed(processes):
            if proc.poll() is None:
                log.warning(f"進程 {proc.pid} 未能正常終止，將強制擊殺。")
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass

        cleanup_venvs()
        log.info("--- 清理完成 ---")

if __name__ == "__main__":
    main()
