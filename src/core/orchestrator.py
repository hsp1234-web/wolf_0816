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

def wait_for_service(port: int, timeout: int = 45) -> bool:
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

def get_db_manager_port_from_file(port_file_path: Path, timeout: int = 45) -> int | None:
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

def wait_for_ready_file(ready_file_path: Path, timeout: int = 45) -> bool:
    """
    等待由 db_manager 建立的「就緒」信號檔案。
    這確保在繼續之前，資料庫已完全初始化。
    """
    log.info(f"正在等待資料庫就緒信號檔案 '{ready_file_path}' ({timeout}秒)...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        if ready_file_path.exists():
            log.info(f"✅ 偵測到就緒信號檔案。資料庫已準備就緒。")
            return True
        time.sleep(0.2)
    log.error(f"❌ 等待資料庫就緒信號檔案 '{ready_file_path}' 超時 ({timeout}秒)。")
    return False

def build_frontend(vue_app_dir: Path):
    """
    在指定的目錄下建置 Vue.js 前端應用。
    """
    log.info("--- [前端建置開始] ---")
    if not vue_app_dir.is_dir():
        log.error(f"❌ 前端應用程式目錄不存在: {vue_app_dir}")
        raise FileNotFoundError(f"Vue app directory not found: {vue_app_dir}")

    try:
        # 檢查 Node.js 和 npm 是否存在
        log.info("步驟 1/3: 正在檢查 Node.js 與 npm 環境...")
        subprocess.run(["node", "--version"], check=True, capture_output=True, text=True)
        subprocess.run(["npm", "--version"], check=True, capture_output=True, text=True)
        log.info("✅ Node.js 與 npm 環境已確認。")

        # 安裝前端依賴
        log.info("步驟 2/3: 正在安裝前端依賴 (npm install)...")
        is_windows = sys.platform == "win32"
        npm_install_cmd = ["npm", "install"]
        install_result = subprocess.run(npm_install_cmd, cwd=vue_app_dir, check=True, capture_output=True, text=True, shell=is_windows)
        log.info("✅ 前端依賴安裝完成。")
        log.debug(f"npm install output:\n{install_result.stdout}")

        # 建置前端應用
        log.info("步驟 3/3: 正在建置前端應用 (npm run build)...")
        npm_build_cmd = ["npm", "run", "build"]
        build_result = subprocess.run(npm_build_cmd, cwd=vue_app_dir, check=True, capture_output=True, text=True, shell=is_windows)
        log.info("✅ 前端應用建置成功！")
        log.debug(f"npm run build output:\n{build_result.stdout}")

    except FileNotFoundError as e:
        log.critical(f"❌ 建置失敗：找不到指令 (node/npm)。請確保 Node.js 已安裝並在系統 PATH 中。 {e}")
        raise
    except subprocess.CalledProcessError as e:
        log.critical(f"❌ 前端建置過程中發生錯誤 (返回碼: {e.returncode})。")
        log.critical(f"   stdout: {e.stdout}")
        log.critical(f"   stderr: {e.stderr}")
        raise
    except Exception as e:
        log.critical(f"❌ 前端建置時發生未預期的錯誤: {e}")
        raise

    log.info("--- [前端建置完成] ---")

def main():
    """
    系統的「大腦」，負責啟動、監控所有服務，並發送心跳。
    """
    # JULES'S FIX (2025-08-17): 確保依賴在啟動前都已安裝
    # 模仿 localtest.py 的行為，使 orchestrator 成為一個更可靠的獨立啟動器。
    # JULES'S FIX (2025-08-19): 新增環境變數開關，以便在測試引擎中跳過此檢查
    if os.environ.get("SKIP_DEP_CHECK"):
        log.info("環境變數 SKIP_DEP_CHECK=1 已設定，跳過內部依賴檢查。")
    else:
        try:
            log.info("正在檢查並安裝伺服器依賴 (uv)...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True, capture_output=True)
            req_file = ROOT_DIR / "requirements-server.txt"
            subprocess.run([sys.executable, "-m", "uv", "pip", "install", "-q", "-r", str(req_file)], check=True, capture_output=True, text=True)
            log.info("✅ 伺服器依賴已是最新狀態。")
        except Exception as e:
            log.critical(f"❌ 安裝依賴時發生錯誤，啟動中止: {e}", exc_info=True)
            sys.exit(1)

    parser = argparse.ArgumentParser(description="系統協調器。")
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False, # JULES: 將預設值改為 False，以啟用真實模式
        help="如果設置，則 worker 將以模擬模式運行。預設為停用。"
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

        # 根本原因修復 (2025-08-20): 將相對路徑改為基於 ROOT_DIR 的絕對路徑，
        # 以解決在不同工作目錄下執行時「找不到檔案」的問題。
        db_manager_cmd = [sys.executable, str(ROOT_DIR / "src" / "db" / "manager.py")]
        # 診斷修復 (2025-08-20): 暫時移除 DEVNULL，以便在 Colab 環境中觀察 db_manager 的輸出
        db_manager_proc = subprocess.Popen(
            db_manager_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        processes.append(db_manager_proc)
        log.info(f"✅ 資料庫管理者子程序已建立，PID: {db_manager_proc.pid}")

        # 為 db_manager 的輸出建立日誌流式讀取執行緒並立即啟動
        db_stdout_thread = threading.Thread(target=stream_reader, args=(db_manager_proc.stdout, 'db_manager'))
        db_stderr_thread = threading.Thread(target=stream_reader, args=(db_manager_proc.stderr, 'db_manager_stderr'))
        db_stdout_thread.daemon = True
        db_stderr_thread.daemon = True
        db_stdout_thread.start()
        db_stderr_thread.start()
        threads.extend([db_stdout_thread, db_stderr_thread])

        # 1a. 從檔案動態讀取 DB Manager 的埠號
        # Note: We re-use the 'port_file_path' variable from the cleanup step above.
        db_manager_port = get_db_manager_port_from_file(port_file_path)
        if db_manager_port is None:
            raise RuntimeError(f"無法從檔案 {port_file_path} 獲取 DB Manager 的埠號，啟動中止。")

        # 1b. 確認 DB Manager 服務已在監聽埠號
        if not wait_for_service(db_manager_port):
            raise RuntimeError(f"DB Manager 服務在埠號 {db_manager_port} 上未能及時就緒，啟動中止。")
        log.info("✅ TCP 服務已在埠號 {db_manager_port} 上就緒。")

        # 1c. JULES'S FIX: 等待由 db_manager 產生的「就緒」信號檔案
        ready_file_path = ROOT_DIR / "src" / "db" / "db_manager.ready"
        if not wait_for_ready_file(ready_file_path):
             raise RuntimeError("DB Manager 服務未能發送就緒信號，啟動中止。")

        # --- JULES' FIX START ---
        # 修復：在 DB Manager 就緒後，再設定資料庫日誌，以避免 race condition
        # (現在由 wait_for_ready_file 保證)
        setup_database_logging()
        log.info("Orchestrator's database logging is now configured.")
        # --- JULES' FIX END ---

        # 2. 獲取資料庫客戶端
        # 此時，我們已確認服務就緒，get_client() 應能立即成功
        db_client = get_client()

        # 2a. 建置前端應用
        build_frontend(ROOT_DIR / "vue-app")

        # 3. 根據參數決定埠號並啟動 API 伺服器
        if args.port:
            api_port = args.port
            log.info(f"使用指定的固定埠號: {api_port}")
        else:
            api_port = find_free_port()
            log.info(f"找到一個隨機的空閒埠號: {api_port}")

        # 根本原因修復 (2025-08-20): 將相對路徑改為基於 ROOT_DIR 的絕對路徑。
        api_server_cmd = [sys.executable, str(ROOT_DIR / "src" / "api" / "api_server.py"), "--port", str(api_port)]
        if args.mock:
            api_server_cmd.append("--mock")

        # JULES'S FIX (2025-08-17): 修正 API Server 的啟動環境
        # 錯誤根源：Orchestrator 未將自身的 PYTHONPATH 傳遞給 api_server 子程序，
        # 導致 api_server 因找不到 'fastapi' 等模組而啟動失敗。
        # 解決方案：為子程序建立一個包含正確 PYTHONPATH 的環境變數。
        api_env = os.environ.copy()
        # 確保 src 目錄在 PYTHONPATH 中
        api_env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + api_env.get("PYTHONPATH", "")
        # 將模擬模式也透過環境變數傳遞，與 api_server 的讀取方式保持一致
        if args.mock:
            api_env["API_MODE"] = "mock"

        log.info(f"🔧 正在啟動 API 伺服器: {' '.join(api_server_cmd)}")
        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=api_env)
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

        # 5. 啟動 api_server 的日誌流式讀取執行緒
        api_stdout_thread = threading.Thread(target=stream_reader, args=(api_proc.stdout, 'api_server'))
        api_stderr_thread = threading.Thread(target=stream_reader, args=(api_proc.stderr, 'api_server_stderr'))
        # 立即啟動，確保不錯過任何日誌
        api_stdout_thread.daemon = True
        api_stderr_thread.daemon = True
        api_stdout_thread.start()
        api_stderr_thread.start()
        threads.extend([api_stdout_thread, api_stderr_thread])

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
