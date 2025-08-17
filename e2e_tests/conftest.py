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
from db.database import initialize_database

log = logging.getLogger('PytestFixture')

def find_free_port():
    """尋找一個空閒的 TCP 埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

@pytest.fixture(scope="session")
def live_server():
    """
    一個 Pytest fixture，它會在測試會話開始時啟動後端伺服器，
    並在會話結束時將其關閉。
    """
    log.info("--- Setting up live server for E2E tests ---")

    # 1. 初始化資料庫
    try:
        initialize_database()
        log.info("✅ 資料庫初始化成功。")
    except Exception as e:
        pytest.fail(f"資料庫初始化失敗: {e}")

    # 2. 建置前端
    try:
        vue_app_dir = ROOT_DIR / "vue-app"
        log.info("🏗️  建置 Vue.js 前端應用程式...")
        subprocess.run(["bun", "install"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
        subprocess.run(["bun", "run", "build"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
        log.info("✅ 前端建置完成。")
    except Exception as e:
        pytest.fail(f"前端建置失敗: {e}")

    # 3. 啟動服務
    processes = []
    api_url = None
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")
        env["API_MODE"] = "mock"

        # 啟動 DB Manager
        db_manager_cmd = [sys.executable, str(ROOT_DIR / "src" / "db" / "manager.py")]
        db_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        processes.append(db_proc)
        log.info(f"  - DB Manager (PID: {db_proc.pid}) 啟動中...")
        time.sleep(3)

        # 啟動 API Server
        api_port = find_free_port()
        api_url = f"http://127.0.0.1:{api_port}"
        api_server_cmd = [sys.executable, str(ROOT_DIR / "src" / "api" / "api_server.py"), "--port", str(api_port)]
        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=env)
        processes.append(api_proc)
        log.info(f"  - API Server (PID: {api_proc.pid}) 啟動中，監聽於 {api_url}")

        # 4. 健康檢查
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

        if not health_check_passed:
            pytest.fail("伺服器健康檢查超時。")

        # 5. 將 URL 提供給測試
        yield api_url

    # 6. 清理
    finally:
        log.info("--- Tearing down live server ---")
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)
        log.info("✅ 所有服務已關閉。")

@pytest.fixture(scope="session")
def db_client_fixture(live_server):
    """
    一個依賴於 live_server 的 fixture，用於提供一個
    已連接且可用的資料庫客戶端實例。
    """
    # live_server fixture 確保了 db_manager 已經在運行
    from db import client as db_client_module

    # 我們透過重設單例來解決在模組導入時客戶端就被初始化的問題。
    # 這確保了 get_client() 會在伺服器啟動後才建立一個全新的、可用的連線。
    db_client_module._client_instance = None

    client = db_client_module.get_client()
    yield client

from unittest.mock import MagicMock

@pytest.fixture(scope="session")
def colab_boot_server():
    """
    一個專門用於測試 Colab 開機畫面的 fixture。
    它只會啟動 Colab.py 中的 TempServerManager。
    """
    # --- 模擬 Colab 環境依賴 ---
    # 為了在非 Colab 環境中測試 Colab.py，我們需要模擬它所依賴的模組
    mock_ipython = MagicMock()
    mock_ipython.display.clear_output = MagicMock()
    mock_ipython.display.display = MagicMock()
    mock_ipython.display.HTML = MagicMock()
    sys.modules['IPython'] = mock_ipython
    sys.modules['IPython.display'] = mock_ipython.display

    mock_google_colab = MagicMock()
    # 我們不需要這些函式有實際行為，只需要它們存在即可
    mock_google_colab.output.eval_js = MagicMock(return_value="")
    mock_google_colab.userdata.get = MagicMock(return_value=None)
    # 建立一個假的 google 模組，因為 `from google.colab` 需要它
    mock_google = MagicMock()
    mock_google.colab = mock_google_colab
    sys.modules['google'] = mock_google
    sys.modules['google.colab'] = mock_google_colab
    # --- 模擬結束 ---

    # Colab.py 位於根目錄，需要將其加入 sys.path
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from Colab import TempServerManager, LogManager, find_free_port
    import queue

    log.info("--- Setting up Colab boot screen server ---")
    temp_server = None
    try:
        port = find_free_port()
        server_url = f"http://127.0.0.1:{port}"

        # 為 TempServerManager 準備最小化的依賴
        log_queue = queue.Queue()
        # 使用一個簡化的 LogManager，避免寫入資料庫
        log_levels = {
            "SHOW_LOG_LEVEL_DEBUG": True, "SHOW_LOG_LEVEL_INFO": True,
            "SHOW_LOG_LEVEL_SUCCESS": True, "SHOW_LOG_LEVEL_WARN": True,
            "SHOW_LOG_LEVEL_ERROR": True, "SHOW_LOG_LEVEL_CRITICAL": True
        }
        log_manager = LogManager(max_lines=10, timezone_str="UTC", log_levels_to_show=log_levels, db_path=":memory:")

        temp_server = TempServerManager(
            port=port,
            log_manager=log_manager,
            log_queue=log_queue,
            project_root=ROOT_DIR
        )
        temp_server.start()
        log.info(f"✅ Colab boot server 啟動於 {server_url}")
        time.sleep(1) # 等待伺服器執行緒啟動

        yield server_url

    finally:
        log.info("--- Tearing down Colab boot screen server ---")
        if temp_server:
            temp_server.stop()
        log.info("✅ Colab boot server 已關閉。")
