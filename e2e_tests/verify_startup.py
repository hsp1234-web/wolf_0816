# e2e_tests/verify_startup.py
import sys
import re
from playwright.sync_api import sync_playwright, expect

def run_verification(url: str):
    """
    使用 Playwright 導航到指定的 URL，驗證頁面標題，並儲存截圖。
    """
    print(f"🚀 開始使用 Playwright 驗證 URL: {url}")
    screenshot_path = "startup_screenshot.png"

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            print(f"📄 正在導航至頁面...")
            page.goto(url, timeout=20000)

            print("✅ 頁面載入成功。")

            # 驗證頁面標題
            expected_title_regex = re.compile("音訊轉錄儀")
            print(f"🔍 正在驗證頁面標題是否包含 '{expected_title_regex.pattern}'...")
            expect(page).to_have_title(expected_title_regex, timeout=10000)

            print("✅ 頁面標題驗證成功！")

            # 儲存截圖
            page.screenshot(path=screenshot_path)
            print(f"📸 已成功儲存截圖至: {screenshot_path}")

            browser.close()
            print("🎉 Playwright 驗證成功！")

        except Exception as e:
            print(f"❌ Playwright 驗證過程中發生錯誤: {e}")
            # 即使出錯也嘗試截圖
            try:
                page.screenshot(path=screenshot_path)
                print(f"📸 已儲存錯誤時的截圖至: {screenshot_path}")
            except Exception as se:
                print(f"⚠️ 無法儲存錯誤截圖: {se}")
            raise

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("錯誤：請提供一個 URL 作為參數。")
        print("用法: python verify_startup.py <URL>")
        sys.exit(1)

    target_url = sys.argv[1]
    run_verification(target_url)
