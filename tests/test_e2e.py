# 檔案: tests/test_e2e.py
# 說明: Playwright 端對端測試案例。
import pytest
from playwright.async_api import async_playwright, expect

@pytest.mark.asyncio
async def test_full_workflow():
    """
    測試從前端輸入到看到報告的完整工作流程。
    使用 USE_MOCK_FILES 來避免實際的網路請求。
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        try:
            # 步驟 1: 訪問應用程式
            await page.goto("http://localhost:8000")

            # 步驟 2: 填寫表單
            await page.fill("#youtube-url", "USE_MOCK_FILES")
            await page.fill("#api-key", "DUMMY_API_KEY_FOR_TESTING")

            # 步驟 3: 點擊按鈕開始任務
            await page.click("#btn-subtitle")

            # 步驟 4: 驗證日誌輸出
            log_output = page.locator("#log-output")

            # 等待並驗證串流日誌包含關鍵訊息
            await expect(log_output).to_contain_text("使用 Mock 檔案進行測試", timeout=10000)
            await expect(log_output).to_contain_text("正在串流 Gemini 報告生成過程", timeout=10000)

            # 這是最重要的斷言：確認後端發出了完成信號
            await expect(log_output).to_contain_text('"status": "complete"', timeout=10000)

            # 步驟 5: 驗證報告是否已抓取並渲染
            report_output = page.locator("#report-output")

            # 等待報告區域出現預期的內容
            # 注意：我們需要知道 mock 報告的內容才能進行精確斷言
            # 由於 generate_gemini_report.py 在 mock 模式下實際上不會被 gemini api 調用
            # 我們需要修改 api_server_v2.py 的 mock 邏輯，讓它直接生成一個假的報告檔案

            # 臨時性修改：目前只驗證報告區不再是初始狀態
            # 在下一步修復 api_server_v2.py 的 mock 邏輯後，我們會回來加強這個斷言
            # 這裡我們預期會看到 "這是用於測試的模擬字幕檔案" 的內容被處理
            # Gemini 腳本的 prompt 是 "請直接輸出 Markdown 格式的報告內容"
            # 由於我們沒有真的 gemini，我們需要 mock 這個輸出

            # 讓我們假設一個理想的 mock 輸出
            # 在 api_server_v2.py 中，當偵測到 USE_MOCK_FILES 時，
            # 它應該直接寫入一個假的 .md 報告檔案

            # 為了讓測試通過，我們將在下一步修改 api_server_v2.py 來實現這一點
            # 現在，我們先假設報告內容是 "Mock Report Content"

            # 斷言：等待報告區域出現我們在 api_server_v2.py 中定義的 mock 內容
            await expect(report_output).to_contain_text("Mock 報告", timeout=15000)
            await expect(report_output).to_contain_text("這是一個在 E2E 測試期間自動生成的模擬報告。", timeout=5000)

        finally:
            # 儲存最終截圖以便驗證
            await page.screenshot(path="e2e_test_screenshot.jpg")
            await browser.close()
