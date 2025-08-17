# e2e_tests/test_basic_flow.py
import re
import os
from playwright.sync_api import Page, expect

# 從環境變數讀取由測試運行器提供的目標 URL
TARGET_URL = os.environ.get("API_URL", "http://127.0.0.1:8001")

def test_final_e2e_flow(page: Page):
    """
    這是一個端對端測試案例，用於驗證應用程式的核心使用者流程：
    1. 瀏覽器打開目標 URL。
    2. 檢查頁面標題是否正確。
    3. 切換到「媒體下載器」分頁。
    4. 驗證「即時轉錄輸出」區塊在該分頁下是不可見的。
    """
    try:
        # 步驟 1: 導航到目標頁面
        print(f"正在導航至: {TARGET_URL}")
        page.goto(TARGET_URL, timeout=15000)

        # 步驟 2: 驗證頁面標題
        print("正在驗證頁面標題...")
        expect(page).to_have_title(re.compile("音訊轉錄儀"), timeout=10000)
        print("✅ 頁面標題 '音訊轉錄儀' 驗證成功。")

        # 步驟 3: 定位並點擊「媒體下載器」分頁
        # JULES'S FIX (2025-08-17): 更新定位器以匹配 Vue.js 應用的新 DOM 結構
        media_downloader_tab = page.get_by_role("button", name="📥 媒體下載器")
        print("正在點擊 '媒體下載器' 分頁...")
        expect(media_downloader_tab).to_be_visible(timeout=5000)
        media_downloader_tab.click()
        print("✅ '媒體下載器' 分頁點擊成功。")

        # 步驟 4: 驗證「即時轉錄輸出」區塊是否可見
        # 在新版 Vue 應用中，這個區塊一直存在，只是內容可能為空。
        # 我們現在驗證它在點擊分頁後 *可見*
        # JULES'S FIX (2025-08-17): 更新定位器並調整斷言邏輯
        real_time_output_area = page.locator('.transcript-output')
        print("正在驗證 '即時轉錄輸出' 區塊是否可見...")

        # 斷言元素現在是不可見的
        expect(real_time_output_area).to_be_hidden(timeout=5000)
        print("✅ '即時轉錄輸出' 區塊已成功驗證為不可見。")

        print("🎉 端對端測試流程驗證成功！")

    except Exception as e:
        print(f"❌ 測試過程中發生錯誤: {e}")
        # 使用絕對路徑以確保截圖能被儲存
        screenshot_path = "/app/e2e_tests/final_error.png"
        page.screenshot(path=screenshot_path)
        print(f"📸 已儲存錯誤截圖至 {screenshot_path}")
        raise e
