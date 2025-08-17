# e2e_tests/test_vue_app_flow.py
import subprocess
import sys
import time
import pytest
import socket
import tempfile
from pathlib import Path
from playwright.sync_api import Page, expect
import urllib.request

ROOT_DIR = Path(__file__).resolve().parent.parent
TEST_MP3_PATH = ROOT_DIR / "e2e_tests" / "fixtures" / "test.mp3"

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

@pytest.fixture(scope="session")
def live_server():
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        logs_dir = temp_dir / "logs"
        logs_dir.mkdir()

        api_port = find_free_port()
        server_url = f"http://127.0.0.1:{api_port}"
        python_exec = sys.executable

        circus_config = f"""
[circus]
check_delay = 5
endpoint = tcp://127.0.0.1:{find_free_port()}
pubsub_endpoint = tcp://127.0.0.1:{find_free_port()}
statsd = false

[watcher:db_manager]
cmd = {python_exec} -u -m db.manager
working_dir = {ROOT_DIR / 'src'}

[watcher:api_server]
cmd = {python_exec} -u -m api.api_server --port {api_port}
working_dir = {ROOT_DIR / 'src'}
env.API_MODE = mock

[watcher:worker]
cmd = {python_exec} -u -m tasks.worker --mock
working_dir = {ROOT_DIR / 'src'}
env.API_PORT = {api_port}
"""
        config_path = temp_dir / "circus.ini"
        config_path.write_text(circus_config)

        print("\n🔩 安裝依賴...")
        subprocess.run([python_exec, "-m", "pip", "install", "-q", "-r", "requirements-server.txt"], check=True)
        print("✅ 依賴安裝完成。")

        command = [python_exec, "-m", "circus.circusd", str(config_path)]
        circus_proc = subprocess.Popen(command)

        health_check_url = f"{server_url}/api/health"
        start_time = time.time()
        timeout = 60
        server_ready = False
        try:
            while time.time() - start_time < timeout:
                try:
                    with urllib.request.urlopen(health_check_url, timeout=2) as response:
                        if response.status == 200:
                            server_ready = True
                            break
                except Exception:
                    time.sleep(1)

            if not server_ready:
                raise RuntimeError(f"伺服器在 {timeout} 秒內未能成功啟動。")

            yield server_url
        finally:
            print("\n🛑 測試執行完畢，正在關閉 Circus 服務...")
            circus_proc.terminate()
            circus_proc.wait(timeout=10)
            print("👋 伺服器已關閉。")

def test_vue_app_full_flow(page: Page, live_server: str):
    target_url = live_server
    page.goto(target_url, timeout=20000)

    expect(page).to_have_title("音訊轉錄儀 (Vue)", timeout=10000)
    expect(page.locator("h2:has-text('📤 步驟 2: 上傳檔案')")).to_be_visible()
    expect(page.locator("h2:has-text('🔄 進行中任務')")).to_be_visible()
    expect(page.locator("h2:has-text('✅ 已完成任務')")).to_be_visible()

    file_input = page.locator('input[type="file"]')
    file_input.set_input_files(TEST_MP3_PATH)
    expect(page.locator("#file-list .task-item:has-text('test.mp3')")).to_be_visible()

    page.locator("#start-processing-btn").click()
    expect(page.locator("#file-list .task-item")).not_to_be_visible(timeout=5000)

    pending_task_selector = f"div.task-card:has-text('{TEST_MP3_PATH.name}')"
    pending_task = page.locator(pending_task_selector)
    expect(pending_task).to_be_visible(timeout=30000)
    expect(pending_task.locator(".task-status:has-text('processing')")).to_be_visible()

    completed_task_selector = f"#completed-tasks div.task-card:has-text('{TEST_MP3_PATH.name}')"
    completed_task = page.locator(completed_task_selector)
    expect(completed_task).to_be_visible(timeout=90000)
    expect(pending_task).not_to_be_visible()

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

    with page.expect_download() as download_info:
        completed_task.get_by_role("button", name="下載").click()
    download = download_info.value
    assert "result" in download.suggested_filename
    print("\n🎉🎉🎉 端對端測試流程已全部驗證成功！ 🎉🎉🎉")
