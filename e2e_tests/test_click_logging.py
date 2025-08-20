# -*- coding: utf-8 -*-
"""
端對端測試：驗證全域點擊日誌已成功記錄至後端

此測試案例旨在驗證對 Vue.js 應用程式中的任何可見元素進行點擊時，
該事件不僅在前端觸發，還能成功地發送到後端 API，並被記錄到資料庫中。

測試核心流程：
1. 在執行任何點擊操作前，先透過一個專用的偵錯 API 端點
   (`/api/debug/latest_frontend_action_log`) 獲取當前最新的日誌 ID。
2. 使用 Playwright 模擬使用者點擊一個前端元件（例如按鈕、標題等）。
3. 測試腳本會開始輪詢偵錯 API，等待一個新的日誌出現（其 ID 必須大於
   步驟 1 中獲取的 ID）。
4. 一旦捕獲到新日誌，測試會驗證以下兩點：
   a. 日誌的訊息 (message) 欄位，是否準確描述了被點擊的元件。
   b. 日誌的 ID (id) 欄位是否存在且為一個有效的數字，這證明了該事件
      有一個可供追蹤的唯一編號。
5. 此流程會對多個不同類型的前端元件進行測試，以確保日誌記錄功能的通用性。
"""

import re
import time
import requests
from playwright.sync_api import Page, expect

# --- 輔助函式 (Helper Functions) ---

def get_latest_log(base_url: str) -> dict | None:
    """
    呼叫後端偵錯 API，獲取最新的前端操作日誌。

    Args:
        base_url: 後端伺服器的基礎 URL。

    Returns:
        一個包含日誌資訊的字典，如果沒有日誌則回傳 None。
    """
    try:
        response = requests.get(f"{base_url}/api/debug/latest_frontend_action_log", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("latest_log")
    except requests.RequestException as e:
        print(f"❌ 呼叫日誌 API 時發生錯誤: {e}")
        return None

def wait_for_new_log(base_url: str, last_log_id: int, timeout_seconds: int = 10) -> dict:
    """
    輪詢偵錯 API，直到出現一個 ID 大於 `last_log_id` 的新日誌。

    Args:
        base_url: 後端伺服器的基礎 URL。
        last_log_id: 上一個已知的日誌 ID。
        timeout_seconds: 等待新日誌的超時時間。

    Returns:
        新的日誌物件。

    Raises:
        TimeoutError: 如果在指定時間內沒有等到新日誌。
    """
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        latest_log = get_latest_log(base_url)
        # 注意：資料庫中的 ID 是從 1 開始的，所以我們的 last_log_id (-1) 肯定會小於第一個日誌的 ID
        if latest_log and latest_log.get("id", 0) > last_log_id:
            print(f"✅ 在 {time.time() - start_time:.2f} 秒後成功捕獲到新日誌 (ID: {latest_log['id']})。")
            return latest_log
        time.sleep(0.5)
    raise TimeoutError(f"❌ 等待新日誌超時（超過 {timeout_seconds} 秒）。")

# --- 測試主體 (Test Case) ---

def test_backend_click_logging(page: Page, live_server: str):
    """
    端對端測試主函式。
    """
    target_url = live_server

    try:
        # 步驟 1: 導航到目標頁面並驗證載入成功
        print(f"\n導航至: {target_url}")
        page.goto(target_url, timeout=20000)
        expect(page).to_have_title(re.compile("音訊轉錄儀"), timeout=10000)
        print("✅ 頁面標題驗證成功。")

        # --- 測試案例 1: 點擊「媒體下載器」分頁按鈕 ---
        print("\n--- 測試案例 1: 點擊「媒體下載器」分頁按鈕 ---")

        # a. 獲取點擊前的最新日誌 ID
        last_log = get_latest_log(target_url)
        last_log_id = last_log['id'] if last_log and last_log.get('id') is not None else -1
        print(f"點擊前的最新日誌 ID: {last_log_id}")

        # b. 定位並點擊按鈕
        downloader_tab_button = page.get_by_role("button", name="📥 媒體下載器")
        expect(downloader_tab_button).to_be_visible(timeout=5000)
        print("正在點擊 '媒體下載器' 按鈕...")
        downloader_tab_button.click()

        # c. 等待並驗證新日誌
        print("正在等待後端記錄新日誌...")
        new_log = wait_for_new_log(target_url, last_log_id)

        assert "message" in new_log, "日誌中缺少 'message' 欄位"
        assert "id" in new_log, "日誌中缺少 'id' 欄位 (追蹤編號)"
        assert isinstance(new_log['id'], int), "日誌 ID (追蹤編號) 必須是整數"

        # 驗證日誌訊息是否符合預期格式
        expected_message_part = "click-event: button with class=tab-button"
        assert expected_message_part in new_log['message'], \
            f"日誌訊息不符合預期。預期包含 '{expected_message_part}'，實際為 '{new_log['message']}'"
        print(f"✅ 日誌驗證成功: Message='{new_log['message']}'")

        # --- 測試案例 2: 點擊 H1 標題 ---
        print("\n--- 測試案例 2: 點擊 H1 標題 ---")

        # a. 再次獲取最新日誌 ID
        last_log_id = new_log['id']
        print(f"點擊前的最新日誌 ID: {last_log_id}")

        # b. 定位並點擊標題
        header_title = page.get_by_role("heading", name="音訊轉錄儀 (Vue)")
        expect(header_title).to_be_visible(timeout=5000)
        print("正在點擊 H1 標題...")
        header_title.click()

        # c. 等待並驗證新日誌
        print("正在等待後端記錄新日誌...")
        new_log = wait_for_new_log(target_url, last_log_id)

        assert "message" in new_log
        assert "id" in new_log
        assert isinstance(new_log['id'], int)

        # H1 標籤沒有 class，日誌應回退到使用 tag 作為識別碼
        expected_message_part = "click-event: h1 with tag=h1"
        assert expected_message_part in new_log['message'], \
            f"日誌訊息不符合預期。預期包含 '{expected_message_part}'，實際為 '{new_log['message']}'"
        print(f"✅ 日誌驗證成功: Message='{new_log['message']}'")

        print("\n🎉🎉🎉 恭喜！所有前端點擊事件均已成功驗證在後端留下記錄！")

    except Exception as e:
        print(f"❌ 測試過程中發生無法預期的錯誤: {e}")
        # 在 CI/CD 環境中，/app 通常是可寫的根目錄
        screenshot_path = "/app/e2e_tests/backend_click_log_error.png"
        try:
            page.screenshot(path=screenshot_path)
            print(f"📸 已儲存錯誤截圖至 {screenshot_path}")
        except Exception as screenshot_error:
            print(f"⚠️ 無法儲存截圖: {screenshot_error}")
        raise e
