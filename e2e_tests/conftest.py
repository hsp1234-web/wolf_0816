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
