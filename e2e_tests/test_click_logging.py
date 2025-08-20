# -*- coding: utf-8 -*-
"""
端對端測試：驗證全域點擊日誌記錄功能

此測試案例旨在驗證對 Vue.js 應用程式中的任何元素進行點擊時，
是否都能觸發一個控制台日誌事件。
"""

import re
import time
from playwright.sync_api import Page, expect

def test_global_click_logging(page: Page, live_server: str):
    """
    驗證核心流程：
    1. 準備一個列表來收集控制台日誌。
    2. 監聽頁面的 'console' 事件，並將訊息儲存起來。
    3. 導航至應用程式 URL。
    4. 點擊頁面上的特定元素（例如，一個按鈕和一個標題）。
    5. 檢查儲存的日誌列表，確認包含了對應的點擊日誌。
    """
    target_url = live_server

    # 步驟 1 & 2: 準備日誌列表並開始監聽
    console_logs = []
    page.on("console", lambda msg: console_logs.append(msg.text))
    print(f"已設定控制台日誌監聽器。")

    try:
        # 步驟 3: 導航到目標頁面
        print(f"正在導航至: {target_url}")
        page.goto(target_url, timeout=20000)

        # 驗證頁面已載入
        expect(page).to_have_title(re.compile("音訊轉錄儀"), timeout=10000)
        print("✅ 頁面標題驗證成功。")

        # --- 測試點擊 1: 分頁按鈕 ---
        print("\n--- 測試案例 1: 點擊分頁按鈕 ---")
        downloader_tab_button = page.get_by_role("button", name="📥 媒體下載器")
        expect(downloader_tab_button).to_be_visible(timeout=5000)

        print("正在點擊 '媒體下載器' 分頁按鈕...")
        downloader_tab_button.click()

        # 等待日誌出現（使用輪詢機制）
        print("正在等待點擊日誌...")
        log_found = False
        for _ in range(10): # 等待最多 5 秒
            # 預期的日誌訊息格式: "Logging action: click-event: button with class=tab-button"
            # 我們使用部分匹配來增加測試的穩健性
            if any("click-event: button with class=tab-button" in log for log in console_logs):
                log_found = True
                print("✅ 成功捕獲到分頁按鈕的點擊日誌！")
                break
            time.sleep(0.5)

        assert log_found, "❌ 失敗：未在預期時間內捕獲到分頁按鈕的點擊日誌。"

        # --- 測試點擊 2: 標題元素 ---
        print("\n--- 測試案例 2: 點擊 H1 標題 ---")
        # 清空日誌以進行下一次獨立驗證
        console_logs.clear()

        header_title = page.get_by_role("heading", name="音訊轉錄儀 (Vue)")
        expect(header_title).to_be_visible(timeout=5000)

        print("正在點擊 H1 標題...")
        header_title.click()

        print("正在等待點擊日誌...")
        log_found = False
        for _ in range(10):
            # 修正：H1 標籤沒有 class，日誌應回退到使用 tag 作為識別碼
            if any("click-event: h1 with tag=h1" in log for log in console_logs):
                log_found = True
                print("✅ 成功捕獲到 H1 標題的點擊日誌！")
                break
            time.sleep(0.5)

        assert log_found, "❌ 失敗：未在預期時間內捕獲到 H1 標題的點擊日誌。"

        print("\n🎉 全域點擊日誌功能驗證成功！")

    except Exception as e:
        print(f"❌ 測試過程中發生錯誤: {e}")
        screenshot_path = "/app/e2e_tests/click_log_error.png"
        page.screenshot(path=screenshot_path)
        print(f"📸 已儲存錯誤截圖至 {screenshot_path}")
        raise e
