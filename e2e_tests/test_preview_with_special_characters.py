# e2e_tests/test_preview_with_special_characters.py
import os
import uuid
import json
from pathlib import Path
import pytest
from playwright.sync_api import Page, expect

# --- Test Setup ---
# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = ROOT_DIR / "uploads"
TARGET_URL = os.environ.get("TARGET_URL", "http://127.0.0.1:8000")

# --- Database Client ---
# 確保 sys.path 包含 src 目錄，以便匯入 db 客戶端
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
def special_char_task():
    """
    一個 Pytest fixture，用於在測試前後自動建立和清理
    一個包含特殊字元檔名的任務。
    """
    if not db_client:
        pytest.skip("資料庫客戶端無法使用，跳過此測試")

    # 1. Setup: 建立假檔案和假任務
    task_id = str(uuid.uuid4())
    # 包含中文、空格、? 和 # 的特殊檔名
    special_filename = f"測試檔案 ? 問題 & 符號 # {task_id}.txt"
    dummy_file_path = UPLOADS_DIR / special_filename
    media_url_path = f"/media/{special_filename}"
    file_content = f"success_{task_id}"
    video_title = f"特殊字元測試 {task_id}"

    # 建立一個假的媒體檔案
    UPLOADS_DIR.mkdir(exist_ok=True)
    dummy_file_path.write_text(file_content, encoding="utf-8")
    print(f"建立測試檔案於: {dummy_file_path}")

    # 在資料庫中插入假任務
    # 這個 result 結構模擬了 youtube_downloader.py 的輸出
    # JULES'S FIX (2025-08-16): 修正 payload，output_path 應該是 /media/ URL
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
        # JULES'S FIX (2025-08-16): 使用新建的 delete_task 方法
        db_client.delete_task(task_id=task_id)
        print(f"已從資料庫刪除任務 {task_id}")
    except Exception as e:
        print(f"清理過程中發生錯誤: {e}")

# --- Test Case ---
def test_preview_of_file_with_special_characters(page: Page, special_char_task):
    """
    驗證前端是否可以正確處理並預覽帶有特殊字元的檔名。
    """
    # JULES'S DEBUGGING (2025-08-16): 監聽瀏覽器的 console 事件
    # 舊版 Playwright 的 'console' 事件直接傳遞字串
    page.on("console", lambda msg: print(f"BROWSER LOG: {msg}"))

    task_info = special_char_task
    video_title = task_info["video_title"]

    print(f"正在測試標題為 '{video_title}' 的任務")
    page.goto(TARGET_URL)

    # JULES'S FIX (2025-08-16): 移除有問題的 wait_for_response 呼叫。
    # Playwright 的 expect(...).to_be_visible() 本身就包含了足夠長的等待時間，
    # 這足以應對非同步載入，且更為穩定。
    print("切換到媒體下載器分頁...")
    page.locator('button[data-tab="downloader-tab"]').click()

    # 在 UI 上尋找已完成的任務
    # JULES'S FIX (2025-08-16): 在正確的容器中尋找任務
    completed_tasks_container = page.locator("#downloader-tasks")

    # 找到我們剛剛建立的那個特定任務項
    # 我們透過檔案標題來定位，因為它在 UI 上是可見的
    task_item = completed_tasks_container.locator(".task-item", has_text=video_title)
    expect(task_item).to_be_visible(timeout=10000)
    print(f"✅ 在 UI 上成功找到任務 '{video_title}'")

    # 找到並點擊該任務的「預覽」按鈕
    preview_button = task_item.locator("a.btn-preview")
    expect(preview_button).to_be_visible()

    # 核心驗證步驟：
    # 我們預期點擊「預覽」後，瀏覽器會發出一個對我們特殊 URL 的請求。
    # Playwright 的 expect_response 會等待這個請求發生，並允許我們檢查其回應。
    print("正在監聽 /media/ 請求...")
    with page.expect_response(
        lambda response: response.url.startswith(f"{TARGET_URL}/media/") and response.status == 200,
        timeout=10000
    ) as response_info:
        print("點擊「預覽」按鈕...")
        preview_button.click()

    # 檢查收到的回應
    response = response_info.value
    print(f"✅ 成功攔截到狀態為 200 的回應: {response.url}")

    # 驗證 URL 是否被正確編碼
    # "測試檔案 ? 問題 & 符號 # ..." -> "測試檔案%20%3F%20問題%20%26%20符號%20%23%20..."
    assert "%3F" in response.url, "URL 中缺少了 '?' 的編碼 '%3F'"
    assert "%23" in response.url, "URL 中缺少了 '#' 的編碼 '%23'"
    assert "%26" in response.url, "URL 中缺少了 '&' 的編碼 '%26'"
    print("✅ URL 編碼驗證成功")

    # 最後，驗證預覽 Modal 是否可見
    preview_modal = page.locator("#preview-modal")
    expect(preview_modal).to_be_visible()
    print("✅ 預覽彈窗已成功顯示")

    # 驗證 Modal 中的內容是否正確
    # 由於是 .txt 檔案，它應該顯示在 <pre> 標籤中
    modal_body = preview_modal.locator(".modal-body")
    expected_content = f"success_{task_info['task_id']}"
    expect(modal_body.locator("pre")).to_have_text(expected_content, timeout=5000)
    print("✅ 預覽內容驗證成功")
