# e2e_tests/test_vue_app_flow.py
import subprocess
import sys
import re
import time
import pytest
import socket
import tempfile
import os
from pathlib import Path
from playwright.sync_api import Page, expect
import urllib.request

# --- 設定路徑 ---
ROOT_DIR = Path(__file__).resolve().parent.parent
TEST_MP3_PATH = ROOT_DIR / "e2e_tests" / "fixtures" / "test.mp3"

def find_free_port() -> int:
    """尋找一個空閒的 TCP 埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

@pytest.fixture(scope="session")
def live_server():
    """
    一個 Pytest session-scoped fixture，負責在測試開始前啟動後端伺服器，
    並在所有測試結束後將其關閉。
    此版本使用 circus 來管理後端服務 (db_manager, api_server, worker)，以確保穩定性。
    """
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        logs_dir = temp_dir / "logs"
        logs_dir.mkdir()

        api_port = find_free_port()
        server_url = f"http://127.0.0.1:{api_port}"
        python_exec = sys.executable

        # --- JULES'S FIX: 動態建立完整的 circus.ini 設定 ---
        circus_config = f"""
[circus]
check_delay = 5
endpoint = tcp://127.0.0.1:{find_free_port()}
pubsub_endpoint = tcp://127.0.0.1:{find_free_port()}
statsd = false

[watcher:db_manager]
cmd = {python_exec} -u -m db.manager
working_dir = {ROOT_DIR / 'src'}
stdout_stream.class = FileStream
stdout_stream.filename = {logs_dir / 'db_manager.log'}
stderr_stream.class = FileStream
stderr_stream.filename = {logs_dir / 'db_manager.err'}

[watcher:api_server]
cmd = {python_exec} -u -m api.api_server --port {api_port}
working_dir = {ROOT_DIR / 'src'}
stdout_stream.class = FileStream
stdout_stream.filename = {logs_dir / 'api_server.log'}
stderr_stream.class = FileStream
stderr_stream.filename = {logs_dir / 'api_server.err'}
env.API_MODE = real

[watcher:worker]
cmd = {python_exec} -u -m tasks.worker
working_dir = {ROOT_DIR / 'src'}
stdout_stream.class = FileStream
stdout_stream.filename = {logs_dir / 'worker.log'}
stderr_stream.class = FileStream
stderr_stream.filename = {logs_dir / 'worker.err'}
env.API_PORT = {api_port}
"""
        config_path = temp_dir / "circus.ini"
        config_path.write_text(circus_config)

        # 安裝所有依賴
        print("\n🔩 安裝依賴...")
        subprocess.run([python_exec, "-m", "pip", "install", "-r", "requirements-server.txt"], check=True, capture_output=True)
        print("✅ 依賴安裝完成。")

        print(f"\n🚀 使用 Circus 啟動完整後端服務 (包含 worker)...")
        print(f"   - Circus 設定檔: {config_path}")
        print(f"   - API 伺服器 URL: {server_url}")

        command = [python_exec, "-m", "circus.circusd", str(config_path), "--log-output", str(logs_dir / "circus.log")]
        circus_proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
        )

        health_check_url = f"{server_url}/api/health"
        start_time = time.time()
        timeout = 60
        server_ready = False
        try:
            while time.time() - start_time < timeout:
                try:
                    with urllib.request.urlopen(health_check_url, timeout=2) as response:
                        if response.status == 200:
                            print("✅ 伺服器健康檢查成功，已準備就緒！")
                            server_ready = True
                            break
                except Exception:
                    time.sleep(2)

            if not server_ready:
                # 讀取日誌以幫助除錯
                for log_file in logs_dir.glob("*.log"):
                    if log_file.exists():
                        print(f"--- 日誌 (啟動失敗): {log_file.name} ---")
                        print(log_file.read_text())
                for err_file in logs_dir.glob("*.err"):
                    if err_file.exists() and err_file.read_text():
                        print(f"--- 錯誤日誌 (啟動失敗): {err_file.name} ---")
                        print(err_file.read_text())
                raise RuntimeError(f"伺服器在 {timeout} 秒內未能成功啟動。")

            yield server_url

        finally:
            print("\n🛑 測試執行完畢，正在關閉 Circus 服務...")
            for log_file in logs_dir.glob("*.log"):
                if log_file.exists():
                    print(f"\n--- 日誌: {log_file.name} ---")
                    print(log_file.read_text())
                    print(f"--- 日誌結束: {log_file.name} ---\n")
            for err_file in logs_dir.glob("*.err"):
                if err_file.exists() and err_file.read_text():
                    print(f"\n--- 錯誤日誌: {err_file.name} ---")
                    print(err_file.read_text())
                    print(f"--- 錯誤日誌結束: {err_file.name} ---\n")

            if circus_proc.poll() is None:
                circus_proc.terminate()
                try:
                    circus_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    circus_proc.kill()
            print("👋 伺服器已關閉。")


# --- 端對端測試案例 (與之前相同) ---
def test_vue_app_full_flow(page: Page, live_server: str):
    """
    驗證 Vue App 的完整使用者流程：
    1. 載入頁面並檢查元件。
    2. 上傳一個音訊檔案。
    3. 驗證任務出現在「進行中」列表。
    4. 等待任務完成，並驗證它被移至「已完成」列表。
    5. 驗證「預覽」和「下載」按鈕的功能。
    """
    target_url = live_server

    # 步驟 1: 導航並驗證頁面載入
    print(f"➡️ 導航至: {target_url}")
    page.goto(target_url, timeout=20000)

    print("➡️ 驗證頁面標題和主要元件...")
    expect(page).to_have_title("音訊轉錄儀 (Vue)", timeout=10000)
    expect(page.locator("h2:has-text('📤 步驟 2: 上傳檔案')")).to_be_visible()
    expect(page.locator("h2:has-text('🔄 進行中任務')")).to_be_visible()
    expect(page.locator("h2:has-text('✅ 已完成任務')")).to_be_visible()
    print("✅ 頁面載入成功。")

    # 步驟 2: 檔案上傳
    print("➡️ 模擬檔案上傳...")
    file_input = page.locator('input[type="file"]')
    file_input.set_input_files(TEST_MP3_PATH)

    expect(page.locator("#file-list .task-item:has-text('test.mp3')")).to_be_visible()
    print("✅ 檔案已成功加入待上傳列表。")

    page.locator("#start-processing-btn").click()
    print("➡️ 已點擊「開始處理」按鈕。")

    # 步驟 3: 驗證任務出現在「進行中」
    print("➡️ 驗證任務是否出現在「進行中」列表...")
    expect(page.locator("#file-list .task-item")).not_to_be_visible(timeout=5000)

    pending_task_selector = f"div.task-card:has-text('{TEST_MP3_PATH.name}')"
    pending_task = page.locator(pending_task_selector)
    expect(pending_task).to_be_visible(timeout=30000)
    expect(pending_task.locator(".task-status:has-text('processing')")).to_be_visible()
    print("✅ 任務已成功進入「進行中」狀態。")

    # 步驟 4: 等待任務完成
    print("➡️ 等待任務完成並移至「已完成」列表...")
    completed_task_selector = f"#completed-tasks div.task-card:has-text('{TEST_MP3_PATH.name}')"
    completed_task = page.locator(completed_task_selector)

    expect(completed_task).to_be_visible(timeout=90000)
    expect(pending_task).not_to_be_visible()
    print("✅ 任務已成功移至「已完成」列表。")

    # 步驟 5: 驗證已完成任務的操作
    print("➡️ 驗證「預覽」和「下載」按鈕...")
    preview_button = completed_task.get_by_role("button", name="預覽")

    alert_triggered = False
    def handle_dialog(dialog):
        nonlocal alert_triggered
        alert_triggered = True
        assert "預覽功能尚未實作" in dialog.message
        dialog.dismiss()

    page.on("dialog", handle_dialog)
    preview_button.click()
    page.wait_for_timeout(1000)
    assert alert_triggered, "預覽按鈕未能觸發 alert 對話框"
    print("✅ 「預覽」按鈕功能驗證成功。")

    download_button = completed_task.get_by_role("button", name="下載")
    with page.expect_download() as download_info:
        download_button.click()

    download = download_info.value
    assert "result" in download.suggested_filename
    print(f"✅ 「下載」按鈕功能驗證成功，觸發下載檔案: {download.suggested_filename}")

    print("\n🎉🎉🎉 端對端測試流程已全部驗證成功！ 🎉🎉🎉")
