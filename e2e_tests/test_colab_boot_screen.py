# e2e_tests/test_colab_boot_screen.py
from playwright.sync_api import Page, expect
import pytest

# 標記此測試需要真實的瀏覽器環境
@pytest.mark.usefixtures("page")
def test_colab_boot_screen_loads(page: Page, colab_boot_server: str):
    """
    測試 Colab 開機畫面是否能正確載入並顯示預期內容。
    這個測試會使用 `colab_boot_server` fixture 來啟動一個
    只包含開機畫面的臨時伺服器。
    """
    target_url = colab_boot_server
    screenshot_path = "e2e_tests/colab_boot_screen_test.png"

    try:
        print(f"正在導航至 Colab 開機畫面: {target_url}")
        page.goto(target_url, timeout=10000)

        # 1. 驗證頁面標題
        print("正在驗證頁面標題...")
        expected_title = "善狼啟動器 - 正在初始化..."
        expect(page).to_have_title(expected_title, timeout=5000)
        print(f"✅ 頁面標題 '{expected_title}' 驗證成功。")

        # 2. 驗證主要標題文字是否可見
        print("正在驗證主要標題...")
        header = page.get_by_role("heading", name="🐺 善狼啟動器 - 正在準備環境...")
        expect(header).to_be_visible()
        print("✅ 主要標題驗證成功。")

        # 3. 驗證日誌容器存在
        print("正在驗證日誌容器...")
        log_container = page.locator("#log-container")
        expect(log_container).to_be_visible()
        print("✅ 日誌容器驗證成功。")

        # 4. 成功時也截圖，以供檢視
        print(f"測試成功，正在儲存截圖至 {screenshot_path}")
        page.screenshot(path=screenshot_path)

    except Exception as e:
        print(f"❌ 測試 Colab 開機畫面時發生錯誤: {e}")
        page.screenshot(path=screenshot_path)
        print(f"📸 已儲存錯誤截圖至 {screenshot_path}")
        raise e
