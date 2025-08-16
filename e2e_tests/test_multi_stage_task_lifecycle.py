# e2e_tests/test_multi_stage_task_lifecycle.py
import os
import uuid
import json
import requests
from pathlib import Path
import pytest
from playwright.sync_api import Page, expect

# --- Test Setup ---
ROOT_DIR = Path(__file__).resolve().parent.parent
# JULES'S FIX (2025-08-16): 確保從環境變數讀取正確的 API URL
# localrun.py 會將隨機指派的埠號透過 TARGET_URL 傳遞進來
TARGET_URL = os.environ.get("TARGET_URL", "http://127.0.0.1:8000")
API_URL = TARGET_URL # 使用同一個 URL，因為測試和 API 跑在同一個位址

# --- Database Client ---
import sys
sys.path.insert(0, str(ROOT_DIR / "src"))
try:
    from db.client import get_client
    db_client = get_client()
except ImportError as e:
    print(f"無法匯入資料庫客戶端: {e}")
    db_client = None

# --- Test Fixture for Setup and Teardown ---
@pytest.fixture(scope="function")
def multi_stage_task_chain():
    """
    建立一個多階段任務鏈 (youtube_download -> gemini_process) 並在測試後清理。
    """
    if not db_client:
        pytest.skip("資料庫客戶端無法使用，跳過此測試")

    # 1. Setup: 建立假任務鏈
    download_task_id = str(uuid.uuid4())
    process_task_id = str(uuid.uuid4())
    fake_url = f"https://www.youtube.com/watch?v=test_{download_task_id}"

    # 任務 A: youtube_download
    db_client.add_task(
        task_id=download_task_id,
        payload=json.dumps({"url": fake_url, "video_title": "生命週期測試影片"}),
        task_type='youtube_download'
    )
    # 它的預設狀態是 'pending'，我們手動更新為 'processing' 來模擬它正在被執行的情況
    db_client.update_task_status(download_task_id, "processing")

    # 任務 B: gemini_process (依賴於 A)
    db_client.add_task(
        task_id=process_task_id,
        payload=json.dumps({"model": "gemini-pro"}),
        task_type='gemini_process',
        depends_on=download_task_id
    )
    # 任務 B 的初始狀態預設就是 'pending'，這正是我們想要的，所以不需更新。
    print(f"已建立任務鏈: {download_task_id} -> {process_task_id}")

    yield {
        "download_task_id": download_task_id,
        "process_task_id": process_task_id,
        "video_title": "生命週期測試影片",
        "fake_url": fake_url
    }

    # 2. Teardown: 測試結束後清理
    print(f"正在清理任務 {download_task_id} 和 {process_task_id}...")
    try:
        db_client.delete_task(task_id=download_task_id)
        db_client.delete_task(task_id=process_task_id)
        print("已從資料庫刪除任務鏈")
    except Exception as e:
        print(f"清理過程中發生錯誤: {e}")

def notify_frontend_of_update(task_id: str, status: str, result: dict):
    """
    一個輔助函式，用於呼叫後端內部 API 來觸發 WebSocket 廣播。
    """
    notification_url = f"{API_URL}/api/internal/notify_task_update"
    try:
        response = requests.post(notification_url, json={
            "task_id": task_id,
            "status": status,
            "result": result
        })
        response.raise_for_status()
        print(f"已成功通知前端任務更新: {task_id} -> {status}")
    except requests.RequestException as e:
        print(f"警告：通知前端失敗: {e}")
        # 在 CI/CD 環境中，我們不希望因為這個通知失敗而中斷測試，
        # 因為我們的測試邏輯主要是依賴頁面重載來驗證最終狀態。
        pass


# --- Test Case ---
def test_multi_stage_task_lifecycle_ui_update(page: Page, multi_stage_task_chain):
    """
    驗證前端 UI 能否正確處理一個多階段任務的完整生命週期。
    """
    # JULES'S DEBUGGING (2025-08-16): 監聽瀏覽器的 console 事件
    # 舊版 Playwright 的 'console' 事件直接傳遞字串
    page.on("console", lambda msg: print(f"BROWSER LOG: {msg}"))

    download_task_id = multi_stage_task_chain["download_task_id"]
    process_task_id = multi_stage_task_chain["process_task_id"]
    video_title = multi_stage_task_chain["video_title"]
    fake_url = multi_stage_task_chain["fake_url"]

    # --- Part 1: 驗證初始狀態 ---
    print("\n--- 階段 1: 驗證初始狀態 ---")
    page.goto(TARGET_URL)

    ongoing_tasks_list = page.locator("#ongoing-tasks")
    completed_tasks_list = page.locator("#completed-tasks")

    # 初始任務應該出現在「進行中」列表
    # JULES'S FIX (2025-08-16): 改用更可靠的 data-source-url 選擇器來定位任務
    initial_task_item = ongoing_tasks_list.locator(f'.task-item[data-source-url="{fake_url}"]')
    expect(initial_task_item).to_be_visible(timeout=10000)
    print("✅ 初始任務成功顯示在「進行中」列表")

    # 「已完成」列表不應該有這個任務
    expect(completed_tasks_list.locator(".task-item", has_text=video_title)).not_to_be_visible()
    print("✅ 「已完成」列表沒有該任務")

    # --- Part 2: 模擬第一階段 (下載) 完成 ---
    print("\n--- 階段 2: 模擬下載任務完成 ---")

    # 更新資料庫狀態
    db_client.update_task_status(download_task_id, "completed", json.dumps({"output_path": "/fake/path.mp3"}))
    # 觸發 WebSocket 通知
    notify_frontend_of_update(download_task_id, "completed", {})

    # 等待一小段時間讓 WebSocket 訊息有機會被處理
    page.wait_for_timeout(1000)

    # 驗證 UI 更新
    status_span = initial_task_item.locator(".task-status")
    expect(status_span).to_have_text("音訊下載完成，等待 AI 分析...", timeout=5000)
    print("✅ 任務狀態文字已更新為「等待 AI 分析...」")

    # 任務項必須仍然在「進行中」列表
    expect(initial_task_item).to_be_visible()
    print("✅ 任務項仍保留在「進行中」列表")

    # --- Part 3: 模擬第二階段 (分析) 完成 ---
    print("\n--- 階段 3: 模擬分析任務完成 ---")

    # 更新資料庫狀態
    final_result = {"output_path": "/fake/report.html", "video_title": video_title}
    db_client.update_task_status(process_task_id, "completed", json.dumps(final_result))
    # 觸發 WebSocket 通知
    notify_frontend_of_update(process_task_id, "completed", final_result)

    # 等待 WebSocket 訊息處理
    page.wait_for_timeout(1000)

    # 重新整理頁面以驗證基於資料庫的最終狀態渲染是否正確
    print("重新整理頁面以驗證最終狀態...")
    page.reload()

    # 最終驗證
    # 任務項必須從「進行中」列表消失
    expect(ongoing_tasks_list.locator(".task-item", has_text=video_title)).not_to_be_visible(timeout=10000)
    print("✅ 任務項已從「進行中」列表移除")

    # 任務項現在應該出現在「已完成」列表
    final_task_item = completed_tasks_list.locator(".task-item", has_text=video_title)
    expect(final_task_item).to_be_visible(timeout=10000)
    print("✅ 任務項已成功顯示在「已完成」列表")

    # 確保只有一個這樣的項目
    expect(final_task_item).to_have_count(1)
    print("✅ 「已完成」列表中只有一個該任務的項目")

    # 驗證最終按鈕是否出現
    expect(final_task_item.locator("a.btn-preview")).to_be_visible()
    expect(final_task_item.locator("a.btn-download")).to_be_visible()
    print("✅ 最終的「預覽」和「下載」按鈕已顯示")
