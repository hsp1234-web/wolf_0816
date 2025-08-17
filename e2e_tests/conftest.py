# e2e_tests/conftest.py
import pytest
import subprocess
import time
import requests
import socket
import os
import sys
from contextlib import closing
from pathlib import Path

# --- Path Setup ---
# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"

# **關鍵修復**：將 'src' 目錄新增至 Python 搜尋路徑。
# 這確保了 pytest 主程序（在其中執行 fixture）可以找到像 'db.client' 這樣的模組。
sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(scope="session")
def db_manager_service():
    """
    一個 session 級別的 fixture，負責啟動和關閉資料庫管理者服務。
    """
    port_file = SRC_DIR / "db" / "db_manager.port"
    if port_file.exists():
        port_file.unlink()

    command = [sys.executable, str(SRC_DIR / "db" / "manager.py")]

    # 雖然我們修改了主程序的 sys.path，但為子程序明確設定 PYTHONPATH
    # 是一種更穩健的做法，能避免潛在的環境繼承問題。
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    timeout = 30
    start_time = time.time()
    while not port_file.exists():
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(
                f"DB 管理者程序意外終止，返回碼: {process.returncode}\n"
                f"STDOUT:\n{stdout}\n"
                f"STDERR:\n{stderr}"
            )
        if time.time() - start_time > timeout:
            process.terminate()
            process.wait()
            stdout, stderr = process.communicate()
            pytest.fail(
                f"DB 管理者在 {timeout} 秒內未能啟動 (port file 未建立)。\n"
                f"STDOUT:\n{stdout}\n"
                f"STDERR:\n{stderr}"
            )
        time.sleep(0.5)

    print(f"DB 管理者服務已啟動 (程序 ID: {process.pid})。")

    yield

    print("\n正在關閉 DB 管理者服務...")
    process.terminate()
    try:
        stdout, stderr = process.communicate(timeout=5)
        print(f"DB Manager STDOUT:\n{stdout}")
        print(f"DB Manager STDERR:\n{stderr}")
    except subprocess.TimeoutExpired:
        process.kill()
        print("DB 管理者程序強制終止。")

    if port_file.exists():
        port_file.unlink()
    print("DB 管理者服務已關閉。")


@pytest.fixture(scope="session")
def db_client(db_manager_service):
    """
    一個依賴於 db_manager_service 的 fixture。
    它確保在 DB 服務就緒後才建立 DB 客戶端單例。
    """
    from db.client import get_client
    client = get_client()
    yield client


@pytest.fixture(scope="session")
def live_server(db_manager_service):
    """
    啟動一個即時的 FastAPI 伺服器以進行端對端測試。
    """
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port = s.getsockname()[1]

    host = "127.0.0.1"
    server_url = f"http://{host}:{port}"

    command = [
        "uvicorn",
        "api.api_server:app",
        "--host", host,
        "--port", str(port)
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    health_check_url = f"{server_url}/api/health"
    timeout = 30
    start_time = time.time()

    while time.time() - start_time < timeout:
        if process.poll() is not None:
             stdout, stderr = process.communicate()
             pytest.fail(
                f"API 伺服器程序意外終止，返回碼: {process.returncode}\n"
                f"STDOUT:\n{stdout}\n"
                f"STDERR:\n{stderr}"
            )
        try:
            response = requests.get(health_check_url, timeout=1)
            if response.status_code == 200:
                print(f"API 伺服器已在 {server_url} 啟動並準備就緒。")
                break
        except requests.ConnectionError:
            time.sleep(0.5)
    else:
        process.terminate()
        process.wait()
        stdout, stderr = process.communicate()
        pytest.fail(
            f"API 伺服器在 {timeout} 秒內未能啟動。\n"
            f"STDOUT:\n{stdout}\n"
            f"STDERR:\n{stderr}"
        )

    yield server_url

    print("\n正在關閉 API 伺服器...")
    process.terminate()
    try:
        stdout, stderr = process.communicate(timeout=5)
        print(f"API Server STDOUT:\n{stdout}")
        print(f"API Server STDERR:\n{stderr}")
    except subprocess.TimeoutExpired:
        process.kill()
        print("API 伺服器程序強制終止。")
    print("API 伺服器已關閉。")
