# orchestrator.py
import time
import subprocess
import sys
import logging
import argparse
import threading
from pathlib import Path
import socket
import os

# --- JULES 於 2025-08-09 的修改：設定應用程式全域時區 ---
# 為了確保所有日誌和資料庫時間戳都使用一致的時區，我們在應用程式啟動的
# 最早期階段就將時區環境變數設定為 'Asia/Taipei'。
os.environ['TZ'] = 'Asia/Taipei'
if sys.platform != 'win32':
    time.tzset()
# --- 時區設定結束 ---

# 將專案根目錄加入 sys.path
# 因為此檔案現在位於 src/core/ 中，所以根目錄是其上上層目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
# sys.path hack 不再需要，因為我們現在使用 `pip install -e .`
# sys.path.insert(0, str(ROOT_DIR))

# from db import database # REMOVED: No longer used directly
from db.client import get_client

# --- 日誌設定 ---
# 使用 stdout，以便外部程序可以捕捉心跳信號和子程序日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('orchestrator')

def setup_database_logging():
    """設定資料庫日誌處理器。"""
    try:
        from db.log_handler import DatabaseLogHandler
        root_logger = logging.getLogger()
        if not any(isinstance(h, DatabaseLogHandler) for h in root_logger.handlers):
            root_logger.addHandler(DatabaseLogHandler(source='orchestrator'))
            log.info("資料庫日誌處理器設定完成 (source: orchestrator)。")
    except Exception as e:
        log.error(f"整合資料庫日誌時發生錯誤: {e}", exc_info=True)

def stream_reader(stream, prefix):
    """一個在執行緒中運行的函數，用於讀取並打印流（stdout/stderr）。"""
    for line in iter(stream.readline, ''):
        log.info(f"[{prefix}] {line.strip()}")
    stream.close()

def find_free_port() -> int:
    """尋找一個空閒的 TCP 埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def wait_for_service(port: int, timeout: int = 15) -> bool:
    """
    在指定的超時時間內，等待特定埠號上的網路服務啟動。

    :param port: 要檢查的 TCP 埠號。
    :param timeout: 等待的總秒數。
    :return: 如果服務在超時內就緒，則返回 True，否則返回 False。
    """
    log.info(f"正在等待 127.0.0.1:{port} 的服務就緒 (超時: {timeout}秒)...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # 使用 create_connection 嘗試建立連線，並設定短暫的內部超時
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                log.info(f"✅ 服務 127.0.0.1:{port} 已成功連線。")
                return True
        except (ConnectionRefusedError, socket.timeout):
            # 服務尚未就緒，短暫等待後重試
            time.sleep(0.25)
            continue
    log.error(f"❌ 等待服務 127.0.0.1:{port} 超時 ({timeout}秒)。")
    return False

def get_db_manager_port_from_file(port_file_path: Path, timeout: int = 10) -> int | None:
    """
    從檔案中讀取 DB Manager 的埠號，並在超時前等待檔案出現。
    這解決了硬編碼埠號導致的不匹配問題。
    """
    log.info(f"正在等待埠號檔案 '{port_file_path}' ({timeout}秒)...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        if port_file_path.exists():
            try:
                content = port_file_path.read_text().strip()
                if content:
                    port = int(content)
                    log.info(f"✅ 成功從檔案中讀取到埠號: {port}")
                    return port
            except (IOError, ValueError) as e:
                log.warning(f"讀取或解析埠號檔案時發生暫時性錯誤: {e}")
        time.sleep(0.2)  # 短暫等待後重試
    log.error(f"❌ 等待埠號檔案 '{port_file_path}' 超時 ({timeout}秒)。")
    return None

def main():
    """
    系統的「大腦」，負責啟動、監控所有服務，並發送心跳。
    """
    parser = argparse.ArgumentParser(description="系統協調器。")
    parser.add_argument(
        "--mock",
        action="store_true",
        default=True, # 將模擬模式設為預設值
        help="如果設置，則 worker 將以模擬模式運行。預設為啟用。"
    )
    parser.add_argument(
        "--no-mock",
        action="store_false",
        dest="mock",
        help="如果設置，則 worker 將以真實模式運行。"
    )
    parser.add_argument(
        "--no-worker",
        action="store_true",
        help="如果設置，則不啟動 worker 程序。"
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=5,
        help="心跳及健康檢查的間隔時間（秒）。"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="指定 API 伺服器運行的固定埠號。如果未提供，將會隨機指派。"
    )
    args = parser.parse_args()

    # DB Manager 會處理初始化，所以這裡不需要再呼叫
    # database.initialize_database()
    # setup_database_logging() # 將在 DB Manager 就緒後呼叫

    log.info(f"🚀 協調器啟動。模式: {'模擬 (Mock)' if args.mock else '真實 (Real)'}")

    processes = []
    threads = []
    db_manager_proc = None
    try:
        # 1. 啟動資料庫管理者服務並等待其就緒
        log.info("🔧 正在啟動資料庫管理者服務...")

        # --- JULES' FIX START ---
        # 修復：在啟動前，先清理上一次執行可能遺留的 port 檔案
        port_file_path = ROOT_DIR / "src" / "db" / "db_manager.port"
        if port_file_path.exists():
            log.warning(f"偵測到舊的埠號檔案，正在清理: {port_file_path}")
            try:
                port_file_path.unlink()
            except OSError as e:
                log.error(f"清理舊的埠號檔案時發生錯誤: {e}")
        # --- JULES' FIX END ---

        db_manager_cmd = [sys.executable, "src/db/manager.py"]
        db_manager_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        processes.append(db_manager_proc)
        log.info(f"✅ 資料庫管理者子程序已建立，PID: {db_manager_proc.pid}")
        # 將 DB Manager 的日誌也流式輸出
        db_manager_log_thread = threading.Thread(target=stream_reader, args=(db_manager_proc.stdout, 'db_manager'))
        db_manager_log_thread.daemon = True
        db_manager_log_thread.start()
        threads.append(db_manager_log_thread)

        # 1a. 從檔案動態讀取 DB Manager 的埠號
        # Note: We re-use the 'port_file_path' variable from the cleanup step above.
        db_manager_port = get_db_manager_port_from_file(port_file_path)

        if db_manager_port is None:
            raise RuntimeError(f"無法從檔案 {port_file_path} 獲取 DB Manager 的埠號，啟動中止。")

        # 1b. 確認 DB Manager 服務已在監聽埠號
        if not wait_for_service(db_manager_port):
            raise RuntimeError(f"DB Manager 服務在埠號 {db_manager_port} 上未能及時就緒，啟動中止。")

        log.info("✅ 資料庫管理者服務已完全就緒。")

        # --- JULES' FIX START ---
        # 修復：在 DB Manager 就緒後，再設定資料庫日誌，以避免 race condition
        setup_database_logging()
        log.info("Orchestrator's database logging is now configured.")
        # --- JULES' FIX END ---

        # 2. 獲取資料庫客戶端
        # 此時，我們已確認服務就緒，get_client() 應能立即成功
        db_client = get_client()

        # 3. 根據參數決定埠號並啟動 API 伺服器
        if args.port:
            api_port = args.port
            log.info(f"使用指定的固定埠號: {api_port}")
        else:
            api_port = find_free_port()
            log.info(f"找到一個隨機的空閒埠號: {api_port}")

        api_server_cmd = [sys.executable, "src/api/api_server.py", "--port", str(api_port)]
        if args.mock:
            api_server_cmd.append("--mock")
        log.info(f"🔧 正在啟動 API 伺服器: {' '.join(api_server_cmd)}")
        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        processes.append(api_proc)
        log.info(f"✅ API 伺服器已啟動，PID: {api_proc.pid}，埠號: {api_port}")
        # --- JULES' FIX for BATTLE Environment ---
        # 根據 BATTLE 測試環境的新要求，修改握手信號的輸出格式，
        # 從 "API_PORT:..." 改為 "PROXY_URL:..."。
        proxy_url = f"http://127.0.0.1:{api_port}"
        print(f"PROXY_URL: {proxy_url}", flush=True)
        log.info(f"已向外部監聽器報告代理 URL: {proxy_url}")


        # 4. 根據旗標決定是否啟動背景工作處理器
        # --- JULES 於 2025-08-09 的修改 ---
        # 註解：
        # 根據最新的架構審查，系統已全面轉向由 api_server.py 透過 WebSocket
        # 觸發並在執行緒中處理轉錄任務的模式。舊的 worker.py 程序會與此新模式
        # 產生衝突（例如，搶佔任務），導致前端出現 WebSocket 連線錯誤和不一致的行為。
        #
        # 解決方案：
        # 因此，我們在此處永久性地停用 worker 程序，以確保只有 api_server
        # 一個服務在處理任務。--no-worker 旗標雖然保留，但此處的程式碼將不再理會它。
        log.info("🚫 [架構性決策] Worker 程序已被永久停用，以支援 WebSocket 驅動的新架構。")
        worker_proc = None
        # (Worker launch code remains commented out)

        # 5. 啟動剩餘的日誌流式讀取執行緒
        # 為 api_server 子程序的 stdout 和 stderr 建立執行緒
        api_stdout_thread = threading.Thread(target=stream_reader, args=(api_proc.stdout, 'api_server'))
        api_stderr_thread = threading.Thread(target=stream_reader, args=(api_proc.stderr, 'api_server_stderr'))
        threads.extend([api_stdout_thread, api_stderr_thread])

        # 啟動所有尚未啟動的執行緒
        for t in threads:
            if not t.is_alive():
                t.daemon = True
                t.start()

        # 6. 進入主監控與心跳迴圈
        log.info("--- [協調器進入監控模式] ---")
        while True:
            # 健康檢查
            # Note: we check all processes except the current one
            for proc in processes:
                if proc.poll() is not None:
                    raise RuntimeError(f"子程序 {proc.args[0]} (PID: {proc.pid}) 已意外終止，返回碼: {proc.returncode}")

            # 心跳檢查
            if db_client.are_tasks_active():
                log.info("HEARTBEAT: RUNNING")
            else:
                log.info("HEARTBEAT: IDLE")

            time.sleep(args.heartbeat_interval)

    except (KeyboardInterrupt, RuntimeError) as e:
        if isinstance(e, RuntimeError):
            log.error(f"協調器因錯誤而終止: {e}")
        else:
            log.info("\n🛑 收到中斷信號，正在優雅關閉所有服務...")

    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                log.info(f"⏳ 正在終止子程序 {proc.args[1]} (PID: {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                    log.info(f"✅ 子程序 {proc.pid} 已終止。")
                except subprocess.TimeoutExpired:
                    log.warning(f"⚠️ 子程序 {proc.pid} 未能正常終止，將強制擊殺 (kill)。")
                    proc.kill()

        # 等待日誌執行緒結束
        for t in threads:
            if t.is_alive():
                t.join(timeout=2)

        log.info("👋 協調器已關閉。")


if __name__ == "__main__":
    main()
