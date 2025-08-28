import asyncio
from playwright.async_api import async_playwright

async def main():
    """
    一個升級版的 Playwright 探測腳本，增加了瀏覽器控制台日誌的捕獲功能。
    """
    print("🚀 [Probe] 正在啟動 Playwright 探測 (含日誌捕獲)...")

    console_logs = []
    def log_console_message(msg):
        # 將日誌訊息儲存起來，以便後續分析
        log_entry = f"  - [Browser Console] {msg.type.upper()}: {msg.text}"
        console_logs.append(log_entry)
        print(log_entry) # 即時印出

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            # 註冊控制台日誌監聽器
            page.on("console", log_console_message)

            print("🌍 [Probe] 正在導航至 http://127.0.0.1:8000 ...")
            await page.goto("http://127.0.0.1:8000", timeout=30000)

            print("👀 [Probe] 正在等待儀表板標題出現...")
            await page.wait_for_selector("h2:has-text('全域儀表板')", timeout=15000)

            screenshot_path = "diagnosis_screenshot.png"
            print(f"📸 [Probe] 正在截圖並儲存至 {screenshot_path} ...")
            await page.screenshot(path=screenshot_path)

            await browser.close()
            print(f"✅ [Probe] 探測成功！已儲存螢幕截圖至 {screenshot_path}")

        except Exception as e:
            print(f"❌ [Probe] 探測失敗: {e}")
            print("\n📋 [Probe] 捕獲到的瀏覽器控制台日誌:")
            if not console_logs:
                print("  - 未捕獲到任何日誌。")
            # 即使失敗也要印出日誌
            # for log_item in console_logs:
            #     print(log_item)
            exit(1)

if __name__ == "__main__":
    asyncio.run(main())
