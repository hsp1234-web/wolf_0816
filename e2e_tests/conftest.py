import pytest
import subprocess
import sys
import time
import logging
import os
import socket
import urllib.request
from pathlib import Path

# --- 全域設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
from db.database import initialize_database, DB_FILE

log = logging.getLogger('PytestFixture')

def find_free_port():
    """尋找一個空閒的 TCP 埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

@pytest.fixture(scope="session")
def build_frontend_session():
    """
    一個 Session-scoped fixture，僅在測試會話開始時建置一次前端。
    這避免了在每個模組中重複執行耗時的建置過程。
    """
    log.info("--- (Session) Building frontend assets ---")
    try:
        vue_app_dir = ROOT_DIR / "vue-app"
        log.info("🏗️  建置 Vue.js 前端應用程式...")
        # 注意：這裡假設 bun 已安裝在環境中
        subprocess.run(["bun", "install"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
        subprocess.run(["bun", "run", "build"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
        log.info("✅ (Session) 前端建置完成。")
    except Exception as e:
        log.error(f"前端建置失敗: {e.stdout or e.stderr}")
        pytest.fail(f"前端建置失敗: {e}")

@pytest.fixture(scope="module")
def live_server(build_frontend_session):
    """
    一個 Module-scoped fixture，它會為每個測試模組（檔案）啟動一組全新的後端服務，
    並在模組測試結束時將其關閉。它依賴於 build_frontend_session 來確保前端已建置。
    """
    log.info(f"--- (Module) Setting up live server for {__name__} ---")

    # 1. 初始化資料庫
    try:
        # 為了確保每個模組的測試都在一個乾淨的環境中運行，
        # 我們在初始化前手動刪除舊的資料庫檔案。
        if DB_FILE.exists():
            DB_FILE.unlink()
            log.info(f"舊資料庫檔案 '{DB_FILE}' 已被刪除，以進行重新初始化。")

        initialize_database()
        log.info("✅ 資料庫已為此模組重新初始化。")
    except Exception as e:
        pytest.fail(f"資料庫初始化失敗: {e}")

    # 2. 啟動服務 (前端已由 build_frontend_session 處理)
    processes = []
    api_url = None
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")
        env["API_MODE"] = "mock"

        # 啟動 DB Manager
        db_manager_cmd = [sys.executable, str(ROOT_DIR / "src" / "db" / "manager.py")]
        port_file = ROOT_DIR / "src" / "db" / "db_manager.port"
        ready_file = ROOT_DIR / "src" / "db" / "db_manager.ready"
        if port_file.exists(): port_file.unlink()
        if ready_file.exists(): ready_file.unlink()

        db_proc = subprocess.Popen(db_manager_cmd, stdout=sys.stdout, stderr=sys.stderr, text=True, encoding='utf-8')
        processes.append(db_proc)
        log.info(f"  - DB Manager (PID: {db_proc.pid}) 啟動中...")

        # --- 等待 DB Manager 就緒 ---
        db_manager_port = None
        start_wait_time = time.time()
        while time.time() - start_wait_time < 20:
            if port_file.exists() and port_file.read_text().strip():
                try:
                    db_manager_port = int(port_file.read_text().strip())
                    log.info(f"✅ DB Manager 的埠號檔案已偵測到，埠號: {db_manager_port}")
                    break
                except (ValueError, IOError): pass
            time.sleep(0.2)
        if not db_manager_port: pytest.fail("DB Manager 未能在指定時間內建立有效的埠號檔案。")

        service_ready = False
        start_wait_time = time.time()
        while time.time() - start_wait_time < 20:
            try:
                with socket.create_connection(("127.0.0.1", db_manager_port), timeout=1):
                    log.info(f"✅ DB Manager 的網路服務在埠號 {db_manager_port} 上已就緒。")
                    service_ready = True
                    break
            except (ConnectionRefusedError, socket.timeout): time.sleep(0.2)
        if not service_ready: pytest.fail(f"DB Manager 的網路服務未能在埠號 {db_manager_port} 上及時就緒。")

        ready_file_appeared = False
        start_wait_time = time.time()
        while time.time() - start_wait_time < 20:
            if ready_file.exists():
                log.info("✅ DB Manager 的就緒信號檔案已偵測到。")
                ready_file_appeared = True
                break
            time.sleep(0.2)
        if not ready_file_appeared: pytest.fail("DB Manager 未能在指定時間內建立就緒檔案。")
        # --- 等待機制結束 ---

        # 啟動 API Server
        api_port = find_free_port()
        api_url = f"http://127.0.0.1:{api_port}"
        api_server_cmd = [sys.executable, str(ROOT_DIR / "src" / "api" / "api_server.py"), "--port", str(api_port)]
        api_proc = subprocess.Popen(api_server_cmd, stdout=sys.stdout, stderr=sys.stderr, text=True, encoding='utf-8', env=env)
        processes.append(api_proc)
        log.info(f"  - API Server (PID: {api_proc.pid}) 啟動中，監聽於 {api_url}")

        # 3. 健康檢查
        health_check_passed = False
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                with urllib.request.urlopen(f"{api_url}/api/health", timeout=2) as response:
                    if response.status == 200:
                        log.info("✅ 後端健康檢查成功。")
                        health_check_passed = True
                        break
            except Exception:
                time.sleep(1)
        if not health_check_passed: pytest.fail("伺服器健康檢查超時。")

        # 4. 將 URL 提供給測試
        yield api_url

    # 5. 清理
    finally:
        log.info(f"--- (Module) Tearing down live server for {__name__} ---")
        for proc in reversed(processes):
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    log.warning(f"  - 程序 (PID: {proc.pid}) 未能正常終止，已強制終止。")
        log.info("✅ 所有模組服務已關閉。")

@pytest.fixture(scope="module")
def db_client_fixture(live_server):
    """
    一個 Module-scoped fixture，提供一個對應當前模組 live_server 的資料庫客戶端。
    """
    from db import client as db_client_module
    db_client_module._client_instance = None
    client = db_client_module.get_client()
    yield client

from unittest.mock import MagicMock

@pytest.fixture(scope="session")
def colab_boot_server():
    """
    一個專門用於測試 Colab 開機畫面的 fixture。
    它只會啟動 Colab.py 中的 TempServerManager。
    此 fixture 保持 session scope，因為它輕量且與主伺服器無關。
    """
    # --- 模擬 Colab 環境依賴 ---
    mock_ipython = MagicMock()
    mock_ipython.display.clear_output = MagicMock()
    mock_ipython.display.display = MagicMock()
    mock_ipython.display.HTML = MagicMock()
    sys.modules['IPython'] = mock_ipython
    sys.modules['IPython.display'] = mock_ipython.display

    mock_google_colab = MagicMock()
    mock_google_colab.output.eval_js = MagicMock(return_value="")
    mock_google_colab.userdata.get = MagicMock(return_value=None)
    mock_google = MagicMock()
    mock_google.colab = mock_google_colab
    sys.modules['google'] = mock_google
    sys.modules['google.colab'] = mock_google_colab
    # --- 模擬結束 ---

    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from Colab import TempServerManager, LogManager, find_free_port
    import queue

    log.info("--- (Session) Setting up Colab boot screen server ---")
    temp_server = None
    try:
        port = find_free_port()
        server_url = f"http://127.0.0.1:{port}"
        log_queue = queue.Queue()
        log_levels = {
            "SHOW_LOG_LEVEL_DEBUG": True, "SHOW_LOG_LEVEL_INFO": True,
            "SHOW_LOG_LEVEL_SUCCESS": True, "SHOW_LOG_LEVEL_WARN": True,
            "SHOW_LOG_LEVEL_ERROR": True, "SHOW_LOG_LEVEL_CRITICAL": True
        }
        log_manager = LogManager(max_lines=10, timezone_str="UTC", log_levels_to_show=log_levels, db_path=":memory:")
        temp_server = TempServerManager(port=port, log_manager=log_manager, log_queue=log_queue, project_root=ROOT_DIR)
        temp_server.start()
        log.info(f"✅ Colab boot server 啟動於 {server_url}")
        time.sleep(1)

        yield server_url

    finally:
        log.info("--- (Session) Tearing down Colab boot screen server ---")
        if temp_server:
            temp_server.stop()
        log.info("✅ Colab boot server 已關閉。")
