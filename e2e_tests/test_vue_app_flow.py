# e2e_tests/test_vue_app_flow.py
import subprocess
import sys
import threading
import queue
import re
import time
import pytest
from pathlib import Path
from playwright.sync_api import Page, expect

# --- 設定路徑 ---
# 取得專案根目錄 (e2e_tests/../)
ROOT_DIR = Path(__file__).resolve().parent.parent
# 測試用的音訊檔案路徑
TEST_MP3_PATH = ROOT_DIR / "e2e_tests" / "fixtures" / "test.mp3"

# --- Pytest Fixture: 自動啟動與關閉後端伺服器 ---
@pytest.fixture(scope="session")
def live_server():
    """
    一個 Pytest session-scoped fixture，負責在測試開始前啟動後端伺服器，
    並在所有測試結束後將其關閉。
    它會監聽伺服器日誌，以取得動態分配的 URL，並等待伺服器準備就緒。
    """
    log_queue = queue.Queue()
    server_url = None
    server_ready = threading.Event()

    # 執行 localrun.py 腳本
    command = [sys.executable, str(ROOT_DIR / "runner" / "localrun.py"), "--no-mock"]

    print(f"\n🚀 正在啟動伺服器: {' '.join(command)}")

    # 使用 Popen 啟動子程序
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        bufsize=1
    )

    # 在獨立執行緒中讀取伺服器日誌，避免阻塞
    def read_output():
        for line in iter(proc.stdout.readline, ''):
            clean_line = line.strip()
            print(clean_line) # 即時顯示日誌，方便偵錯
            log_queue.put(clean_line)
        proc.stdout.close()

    reader_thread = threading.Thread(target=read_output, daemon=True)
    reader_thread.start()

    # 等待伺服器啟動並取得 URL
    start_time = time.time()
    timeout = 60  # 伺服器啟動的超時時間（秒）

    try:
        while time.time() - start_time < timeout:
            try:
                line = log_queue.get(timeout=1)

                # 從日誌中尋找 API 伺服器 URL
                if "API 伺服器正在監聽" in line:
                    match = re.search(r"http://127.0.0.1:\d+", line)
                    if match:
                        server_url = match.group(0)
                        print(f"✅ 捕獲到伺服器 URL: {server_url}")

                # 檢查伺服器是否已完全就緒
                if "伺服器已成功啟動！" in line:
                    if server_url:
                        print("✅ 伺服器已準備就緒！")
                        server_ready.set()
                        break
                    else:
                        print("⚠️ 伺服器已啟動，但尚未捕獲到 URL，繼續監聽...")

            except queue.Empty:
                if proc.poll() is not None:
                    raise RuntimeError("伺服器程序在啟動過程中意外終止。")

        if not server_ready.is_set():
            raise RuntimeError(f"伺服器在 {timeout} 秒內未能成功啟動。")

        # 將 URL 交給測試使用
        yield server_url

    finally:
        # --- 測試結束後的清理工作 ---
        print("\n🛑 測試執行完畢，正在關閉伺服器...")
        if proc.poll() is None:
            proc.terminate() # 傳送 SIGTERM
            try:
                proc.wait(timeout=10) # 等待優雅關閉
            except subprocess.TimeoutExpired:
                print("⚠️ 伺服器未能優雅關閉，強制終止...")
                proc.kill() # 傳送 SIGKILL
        print("👋 伺服器已關閉。")


# --- 端對端測試案例 ---
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
    expect(page.locator("h2:has-text('1. 檔案上傳')")).to_be_visible()
    expect(page.locator("h2:has-text('進行中任務')")).to_be_visible()
    expect(page.locator("h2:has-text('已完成任務')")).to_be_visible()
    print("✅ 頁面載入成功。")

    # 步驟 2: 檔案上傳
    print("➡️ 模擬檔案上傳...")
    # 使用 set_input_files 來選擇檔案
    file_input = page.locator('input[type="file"]')
    file_input.set_input_files(TEST_MP3_PATH)

    # 驗證檔案是否出現在列表中
    expect(page.locator(".file-list-item:has-text('test.mp3')")).to_be_visible()
    print("✅ 檔案已成功加入待上傳列表。")

    # 點擊開始處理按鈕
    page.get_by_role("button", name="開始處理").click()
    print("➡️ 已點擊「開始處理」按鈕。")

    # 步驟 3: 驗證任務出現在「進行中」
    print("➡️ 驗證任務是否出現在「進行中」列表...")
    # 等待上傳列表被清空
    expect(page.locator(".file-list-item")).not.to_be_visible(timeout=5000)

    # 找到進行中任務
    pending_task_selector = f"div.task-card:has-text('{TEST_MP3_PATH.name}')"
    pending_task = page.locator(pending_task_selector)
    expect(pending_task).to_be_visible(timeout=10000)
    expect(pending_task.locator(".task-status:has-text('processing')")).to_be_visible()
    print("✅ 任務已成功進入「進行中」狀態。")

    # 步驟 4: 等待任務完成
    print("➡️ 等待任務完成並移至「已完成」列表...")
    completed_task_selector = f"#completed-tasks div.task-card:has-text('{TEST_MP3_PATH.name}')"
    completed_task = page.locator(completed_task_selector)

    # 等待最多 90 秒讓任務完成 (包含下載、轉錄等)
    expect(completed_task).to_be_visible(timeout=90000)
    # 驗證舊的進行中任務已消失
    expect(pending_task).not.to_be_visible()
    print("✅ 任務已成功移至「已完成」列表。")

    # 步驟 5: 驗證已完成任務的操作
    print("➡️ 驗證「預覽」和「下載」按鈕...")
    # 驗證預覽按鈕
    preview_button = completed_task.get_by_role("button", name="預覽")

    # 設定一個監聽器來處理 alert 對話框
    alert_triggered = False
    def handle_dialog(dialog):
        nonlocal alert_triggered
        alert_triggered = True
        assert "預覽功能尚未實作" in dialog.message
        dialog.dismiss()

    page.on("dialog", handle_dialog)

    preview_button.click()
    # 等待一小段時間以確保 dialog 事件被觸發
    page.wait_for_timeout(1000)
    assert alert_triggered, "預覽按鈕未能觸發 alert 對話框"
    print("✅ 「預覽」按鈕功能驗證成功。")

    # 驗證下載按鈕
    download_button = completed_task.get_by_role("button", name="下載")

    # 使用 page.expect_download 來等待下載事件
    with page.expect_download() as download_info:
        download_button.click()

    download = download_info.value
    # 驗證下載的檔案名稱是否符合預期
    assert "result" in download.suggested_filename
    print(f"✅ 「下載」按鈕功能驗證成功，觸發下載檔案: {download.suggested_filename}")

    print("\n🎉🎉🎉 端對端測試流程已全部驗證成功！ 🎉🎉🎉")
