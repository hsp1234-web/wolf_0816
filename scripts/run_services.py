import subprocess
import sys
import os
import signal
import time
from pathlib import Path
import threading

# 全域變數來追蹤子進程
processes = []
API_SERVER_PORT = 8000 # 與 Colabpro.py 中的設定保持一致

def log(message):
    """簡單的日誌函式，將輸出到 stderr，避免干擾 stdout 的埠號回報。"""
    print(f"[run_services] {message}", file=sys.stderr, flush=True)

def stream_output(process, name):
    """讀取並記錄子進程的輸出。"""
    if not process or not process.stdout:
        return
    for line in iter(process.stdout.readline, ''):
        log(f"[{name}] {line.strip()}")

def cleanup(signum=None, frame=None):
    """清理函式，用於終止所有子進程。"""
    log("收到關閉信號，正在終止所有子進程...")
    for p in reversed(processes):
        if p.poll() is None:
            log(f"正在終止 PID: {p.pid}...")
            # 使用 os.killpg 來確保終止整個進程組
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass # 進程可能已經自己結束了
    # 等待一會兒讓進程終止
    time.sleep(2)
    for p in reversed(processes):
        if p.poll() is None:
            log(f"強制終止 PID: {p.pid}...")
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
    log("所有子進程已清理。")
    sys.exit(0)

def main():
    # 註冊信號處理器，以便優雅關閉
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    project_root = Path(__file__).parent.parent

    try:
        # --- 步驟 1: 啟動資料庫管理器 ---
        log("步驟 1: 啟動資料庫管理器...")
        db_manager_command = [sys.executable, str(project_root / "src/db/manager.py")]
        db_proc = subprocess.Popen(
            db_manager_command, text=True, encoding='utf-8',
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            preexec_fn=os.setsid # 建立新的進程組
        )
        processes.append(db_proc)
        threading.Thread(target=stream_output, args=(db_proc, "DB_Manager"), daemon=True).start()

        # 等待資料庫管理器就緒 - 更穩健的方式是檢查某個狀態，但暫時先用 sleep
        log("等待資料庫管理器初始化...")
        time.sleep(5)
        if db_proc.poll() is not None:
            raise RuntimeError(f"資料庫管理器啟動失敗，返回碼: {db_proc.poll()}")
        log("資料庫管理器已在背景啟動。")

        # --- 步驟 2: 啟動統一 API 伺服器 ---
        log(f"步驟 2: 啟動統一 API 伺服器於埠號 {API_SERVER_PORT}...")
        # 從環境變數讀取 LIGHT_MODE
        light_mode = os.environ.get("LIGHT_MODE", "0") == "1"
        server_env = os.environ.copy()
        if light_mode:
            server_env["LIGHT_MODE"] = "1"
            log("輕量測試模式已啟用。")

        # 將靜態檔案目錄的絕對路徑傳遞給 API 伺服器
        static_dir_path = project_root / "vue-app" / "dist"
        server_env["STATIC_DIR"] = str(static_dir_path.resolve())
        log(f"將 STATIC_DIR 設為: {server_env['STATIC_DIR']}")

        server_command = [
            sys.executable, "-m", "uvicorn", "src.api_server:app",
            "--host", "0.0.0.0", "--port", str(API_SERVER_PORT)
        ]
        api_proc = subprocess.Popen(
            server_command, text=True, encoding='utf-8', env=server_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
            cwd=project_root # 關鍵修復：確保 Uvicorn 在專案根目錄下執行
        )
        processes.append(api_proc)
        threading.Thread(target=stream_output, args=(api_proc, "API_Server"), daemon=True).start()

        # 這裡可以加入更複雜的健康檢查，但目前先假設它能啟動
        time.sleep(5)
        if api_proc.poll() is not None:
            raise RuntimeError(f"API 伺服器啟動失敗，返回碼: {api_proc.poll()}")
        log(f"API 伺服器已在 http://127.0.0.1:{API_SERVER_PORT} 啟動")

        # *** 向 Colabpro.py 回報埠號 ***
        # 使用特殊的格式，避免被一般日誌干擾
        print(f"APP_PORT:{API_SERVER_PORT}", flush=True)

        # --- 步驟 3: 啟動背景工作者 ---
        log("步驟 3: 啟動背景工作者...")
        worker_command = [sys.executable, str(project_root / "workers/transcription_worker.py")]
        worker_proc = subprocess.Popen(
            worker_command, text=True, encoding='utf-8',
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            preexec_fn=os.setsid
        )
        processes.append(worker_proc)
        threading.Thread(target=stream_output, args=(worker_proc, "Worker"), daemon=True).start()
        log("轉錄工作者已在背景啟動。")

        # --- 步驟 4: 等待主服務 (API Server) 結束 ---
        log("所有服務已啟動。監控 API 伺服器狀態...")
        api_proc.wait()
        log("API 伺服器已停止。")

    except Exception as e:
        log(f"發生致命錯誤: {e}")
    finally:
        cleanup()

if __name__ == "__main__":
    main()
