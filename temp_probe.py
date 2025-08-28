import asyncio
from playwright.async_api import async_playwright

async def main():
    """
    一個最終的、增強的 Playwright 探測腳本，用於：
    1. 驗證主儀表板是否渲染。
    2. 驗證硬體監控數據是否顯示。
    3. 驗證自檢按鈕是否有效。
    """
    print("🚀 [Probe] 正在啟動最終的 Playwright 探測...")

    console_logs = []
    def log_console_message(msg):
        log_entry = f"  - [Browser Console] {msg.type.upper()}: {msg.text}"
        console_logs.append(log_entry)
        print(log_entry)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            page.on("console", log_console_message)

            print("🌍 [Probe] 正在導航至 http://127.0.0.1:8000 ...")
            await page.goto("http://127.0.0.1:8000", timeout=30000)

            print("👀 [Probe] 正在等待儀表板標題出現...")
            await page.wait_for_selector("h2:has-text('全域儀表板')", timeout=15000)
            print("✅ [Probe] 儀表板標題已出現。")

            print("👀 [Probe] 正在等待 CPU/RAM 數據出現...")
            # 等待 CPU 數據欄位不再是 '--'
            await page.wait_for_function("""
                () => {
                    const cpuLabel = document.querySelector('#cpu-label');
                    return cpuLabel && cpuLabel.textContent.trim() !== '--';
                }
            """, timeout=15000)
            print("✅ [Probe] CPU/RAM 數據已成功載入。")

            print("🖱️ [Probe] 正在點擊「執行通訊測試」按鈕...")
            await page.click("button[data-testid='health-check-button']")

            print("👀 [Probe] 正在等待健康檢查報告出現...")
            await page.wait_for_selector("div:has-text('全方位健康檢查報告')", timeout=10000)
            print("✅ [Probe] 健康檢查報告已成功顯示。")

            screenshot_path = "final_diagnosis_screenshot.png"
            print(f"📸 [Probe] 正在截圖並儲存至 {screenshot_path} ...")
            await page.screenshot(path=screenshot_path)

            await browser.close()
            print(f"🎉 [Probe] 所有驗證成功！已儲存最終螢幕截圖至 {screenshot_path}")

        except Exception as e:
            print(f"❌ [Probe] 探測失敗: {e}")
            print("\n📋 [Probe] 捕獲到的瀏覽器控制台日誌:")
            if not console_logs:
                print("  - 未捕獲到任何日誌。")
            exit(1)

if __name__ == "__main__":
    asyncio.run(main())
