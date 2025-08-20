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

def get_all_frontend_action_logs(base_url: str) -> list[dict]:
    """
    呼叫後端偵錯 API，獲取所有前端操作日誌。

    Args:
        base_url: 後端伺服器的基礎 URL。

    Returns:
        一個包含所有日誌資訊的字典列表。
    """
    try:
        # 這個偵錯端點現在會回傳一個包含 'logs' 鍵的物件
        response = requests.get(f"{base_url}/api/debug/all_frontend_action_logs", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("logs", [])
    except requests.RequestException as e:
        print(f"❌ 呼叫日誌 API 時發生錯誤: {e}")
        return []

def wait_for_new_log(base_url: str, last_log_id: int, message_contains: str = None, timeout_seconds: int = 10) -> dict:
    """
    輪詢偵錯 API，直到出現一個符合條件的新日誌。

    Args:
        base_url: 後端伺服器的基礎 URL。
        last_log_id: 上一個已知的日誌 ID。
        message_contains: (可選) 日誌訊息中必須包含的子字串。
        timeout_seconds: 等待新日誌的超時時間。

    Returns:
        新的日誌物件。

    Raises:
        TimeoutError: 如果在指定時間內沒有等到符合條件的新日誌。
    """
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        all_logs = get_all_frontend_action_logs(base_url)

        # 從新到舊尋找符合條件的日誌
        for log in reversed(all_logs):
            log_id = log.get("id", 0)
            if log_id > last_log_id:
                if message_contains is None or message_contains in log.get("message", ""):
                    print(f"✅ 在 {time.time() - start_time:.2f} 秒後成功捕獲到新日誌 (ID: {log_id})。")
                    return log

        time.sleep(0.5)

    error_message = f"❌ 等待新日誌超時（超過 {timeout_seconds} 秒）。"
    if message_contains:
        error_message += f" (篩選條件: 訊息需包含 '{message_contains}')"
    raise TimeoutError(error_message)

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
        all_logs = get_all_frontend_action_logs(target_url)
        last_log_id = max(log['id'] for log in all_logs) if all_logs else -1
        print(f"點擊前的最新日誌 ID: {last_log_id}")

        # b. 定位並點擊按鈕
        downloader_tab_button = page.get_by_role("button", name="📥 媒體下載器")
        expect(downloader_tab_button).to_be_visible(timeout=5000)
        print("正在點擊 '媒體下載器' 按鈕...")
        downloader_tab_button.click()

        # c. 等待並驗證我們關心的特定日誌
        expected_message_part = "click-event: button with class=tab-button"
        print(f"正在等待後端記錄包含 '{expected_message_part}' 的新日誌...")
        new_log = wait_for_new_log(target_url, last_log_id, message_contains=expected_message_part)

        assert "message" in new_log, "日誌中缺少 'message' 欄位"
        assert "id" in new_log, "日誌中缺少 'id' 欄位 (追蹤編號)"
        assert isinstance(new_log['id'], int), "日誌 ID (追蹤編號) 必須是整數"
        print(f"✅ 日誌驗證成功: Message='{new_log['message']}'")

        # --- 測試案例 2: 點擊 H1 標題 ---
        print("\n--- 測試案例 2: 點擊 H1 標題 ---")

        # a. 再次獲取最新日誌 ID
        all_logs = get_all_frontend_action_logs(target_url)
        last_log_id = max(log['id'] for log in all_logs) if all_logs else -1
        print(f"點擊前的最新日誌 ID: {last_log_id}")

        # b. 定位並點擊標題
        header_title = page.get_by_role("heading", name="音訊轉錄儀 (Vue)")
        expect(header_title).to_be_visible(timeout=5000)
        print("正在點擊 H1 標題...")
        header_title.click()

        # c. 等待並驗證新日誌
        expected_message_part = "click-event: h1 with tag=h1"
        print(f"正在等待後端記錄包含 '{expected_message_part}' 的新日誌...")
        new_log = wait_for_new_log(target_url, last_log_id, message_contains=expected_message_part)

        assert "message" in new_log
        assert "id" in new_log
        assert isinstance(new_log['id'], int)
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
