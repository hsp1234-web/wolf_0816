# e2e_tests/test_preview_with_special_characters.py
import os
import uuid
import json
from pathlib import Path
import pytest
from playwright.sync_api import Page, expect

# --- Test Setup ---
# 移除了所有在模組層級的設定和匯入，改為使用 Pytest Fixtures

# --- Test Fixture for Setup and Teardown ---
@pytest.fixture(scope="function")
def special_char_task(db_client): # <-- db_client 現在透過 fixture 注入
    """
    一個 Pytest fixture，用於在測試前後自動建立和清理
    一個包含特殊字元檔名的任務。
    """
    # 定義測試所需的路徑
    root_dir = Path(__file__).resolve().parent.parent
    uploads_dir = root_dir / "uploads"

    # 1. Setup: 建立假檔案和假任務
    task_id = str(uuid.uuid4())
    # 包含中文、空格、? 和 # 的特殊檔名
    special_filename = f"測試檔案 ? 問題 & 符號 # {task_id}.txt"
    dummy_file_path = uploads_dir / special_filename
    media_url_path = f"/media/{special_filename}"
    file_content = f"success_{task_id}"
    video_title = f"特殊字元測試 {task_id}"

    # 建立一個假的媒體檔案
    uploads_dir.mkdir(exist_ok=True)
    dummy_file_path.write_text(file_content, encoding="utf-8")
    print(f"建立測試檔案於: {dummy_file_path}")

    # 在資料庫中插入假任務
    # 這個 result 結構模擬了 youtube_downloader.py 的輸出
    result_payload = json.dumps({
        "output_path": media_url_path,
        "video_title": video_title,
        "original_filename": video_title
    })

    # 我們模擬一個 'youtube_download_only' 任務，因為它的結果最簡單
    db_client.add_task(
        task_id=task_id,
        payload=json.dumps({"url": "http://fake.url"}),
        task_type='youtube_download_only'
    )
    db_client.update_task_status(task_id, "completed", result_payload)
    print(f"已將任務 {task_id} 插入資料庫")

    # 使用 yield 將資料傳遞給測試函式
    yield {
        "task_id": task_id,
        "video_title": video_title,
        "media_url_path": media_url_path
    }

    # 2. Teardown: 測試結束後清理
    print(f"正在清理任務 {task_id} 和檔案...")
    try:
        if dummy_file_path.exists():
            dummy_file_path.unlink()
            print(f"已刪除測試檔案: {dummy_file_path}")
        db_client.delete_task(task_id=task_id)
        print(f"已從資料庫刪除任務 {task_id}")
    except Exception as e:
        print(f"清理過程中發生錯誤: {e}")

# --- Test Case ---
def test_preview_of_file_with_special_characters(page: Page, live_server, special_char_task):
    """
    驗證前端是否可以正確處理並預覽帶有特殊字元的檔名。
    """
    page.on("console", lambda msg: print(f"BROWSER LOG: {msg}"))

    task_info = special_char_task
    video_title = task_info["video_title"]

    print(f"正在測試標題為 '{video_title}' 的任務")
    page.goto(live_server)

    print("切換到媒體下載器分頁...")
    # JULES'S FIX (2025-08-17): 更新為 Vue app 的新版定位器
    page.get_by_role("button", name="📥 媒體下載器").click()

    # JULES'S FIX (2025-08-17): 已完成任務現在位於全域的 #completed-tasks 容器中
    completed_tasks_container = page.locator("#completed-tasks")
    # [JULES'S FIX 2025-08-17] 之前因為前端 bug，這裡用 task_id 搜尋。
    # 現在前端 bug 已修復，我們驗證正確的行為：UI 應該顯示 video_title。
    task_item = completed_tasks_container.locator(".task-item", has_text=video_title)
    expect(task_item).to_be_visible(timeout=10000)
    print(f"✅ 在 UI 上成功找到任務 '{video_title}'")

    preview_button = task_item.locator("a.btn-preview")
    expect(preview_button).to_be_visible()

    print("正在監聽 /media/ 請求...")
    with page.expect_response(
        lambda response: response.url.startswith(f"{live_server}/media/") and response.status == 200,
        timeout=10000
    ) as response_info:
        print("點擊「預覽」按鈕...")
        preview_button.click()

    response = response_info.value
    print(f"✅ 成功攔截到狀態為 200 的回應: {response.url}")

    assert "%3F" in response.url, "URL 中缺少了 '?' 的編碼 '%3F'"
    assert "%23" in response.url, "URL 中缺少了 '#' 的編碼 '%23'"
    assert "%26" in response.url, "URL 中缺少了 '&' 的編碼 '%26'"
    print("✅ URL 編碼驗證成功")

    # JULES'S FIX (2025-08-17): 修正預覽彈窗的定位器
    preview_modal = page.locator(".modal-overlay")
    expect(preview_modal).to_be_visible()
    print("✅ 預覽彈窗已成功顯示")

    modal_body = preview_modal.locator(".modal-body")
    expected_content = f"success_{task_info['task_id']}"
    expect(modal_body.locator("pre")).to_have_text(expected_content, timeout=5000)
    print("✅ 預覽內容驗證成功")
