# e2e_tests/test_basic_flow.py
import re
import os
import time
import requests
from playwright.sync_api import Page, expect
from urllib.parse import urljoin

# --- 新增：功能按鈕和狀態 API 的設定 ---
# 定義了依賴後端 AI 功能的按鈕選擇器
FEATURE_BUTTONS = {
    "whisper": ["#confirm-settings-btn", "#start-processing-btn"],
    "ytdlp": ["#start-download-btn", "#download-audio-only-btn"],
    "gemini": ["#save-api-key-btn", "#analyze-video-btn"],
}

# 定義所有需要檢查的按鈕 ID
ALL_BUTTON_IDS = [btn for buttons in FEATURE_BUTTONS.values() for btn in buttons]

def wait_for_features_ready(base_url: str, timeout: int = 180):
    """
    輪詢後端的 /api/features/status 端點，直到所有 AI 功能都準備就緒。
    """
    print(f"⏳ 開始輪詢功能狀態，目標 URL: {base_url}，超時: {timeout} 秒")
    start_time = time.time()
    status_url = urljoin(base_url, "/api/features/status")

    while time.time() - start_time < timeout:
        try:
            response = requests.get(status_url, timeout=5)
            response.raise_for_status()
            status_data = response.json()
            print(f"🔁 取得狀態: {status_data}")

            # 檢查所有定義在 FEATURE_BUTTONS 中的功能是否都已 'ready'
            all_ready = all(
                status_data.get(feature) == "ready" for feature in FEATURE_BUTTONS.keys()
            )

            if all_ready:
                print("✅ 所有 AI 功能已準備就緒！")
                return
        except requests.RequestException as e:
            print(f"⚠️ 輪詢時發生網路錯誤: {e}")
        except Exception as e:
            print(f"⚠️ 輪詢時發生未知錯誤: {e}")

        time.sleep(2)

    raise TimeoutError(f"❌ 在 {timeout} 秒內，AI 功能未全部準備就緒。")


def test_final_e2e_flow(page: Page, live_server: str):
    """
    這是一個升級版的端對端測試，用於驗證「漸進式載入」流程：
    1.  導航到頁面。
    2.  驗證頁面標題。
    3.  **新增**: 斷言所有 AI 功能按鈕在初始時為「禁用」狀態。
    4.  **新增**: 輪詢功能狀態 API，直到所有功能都回報「就緒」。
    5.  **新增**: 斷言所有 AI 功能按鈕現在為「啟用」狀態。
    6.  執行原有的分頁切換與可見性測試。
    """
    target_url = live_server
    try:
        # 步驟 1: 導航到目標頁面
        print(f"正在導航至: {target_url}")
        page.goto(target_url, timeout=15000)

        # 步驟 2: 驗證頁面標題
        print("正在驗證頁面標題...")
        expect(page).to_have_title(re.compile("音訊轉錄儀"), timeout=10000)
        print("✅ 頁面標題 '音訊轉錄儀' 驗證成功。")

        # 步驟 3: 初始狀態驗證 - 確認按鈕為禁用
        print("🔍 正在驗證 AI 功能按鈕的初始禁用狀態...")
        # 為了看到所有按鈕，我們需要先點擊所有分頁
        page.get_by_role("button", name="📥 媒體下載器").click()
        page.get_by_role("button", name="▶️ YouTube 轉報告").click()
        page.get_by_role("button", name="📁 本機檔案轉錄").click() # 返回預設分頁

        for button_id in ALL_BUTTON_IDS:
            # start-processing-btn 的禁用狀態由檔案選擇決定，在此測試中不檢查
            if button_id == "#start-processing-btn":
                continue
            print(f"  - 正在檢查按鈕 {button_id}...")
            # 由於前端框架可能延遲應用 disabled 屬性，我們給予一個短暫的等待時間
            expect(page.locator(button_id)).to_be_disabled(timeout=2000)
        print("✅ 所有 AI 功能按鈕在初始時均為禁用狀態。")

        # 步驟 4: 等待後端功能就緒
        # 注意: 這裡我們假設 live_server fixture 已經啟動了後端
        wait_for_features_ready(target_url)

        # 步驟 5: 就緒狀態驗證 - 確認按鈕為啟用
        print("🔍 正在驗證 AI 功能按鈕在就緒後為啟用狀態...")
        # 再次點擊所有分頁以確保它們可見
        page.get_by_role("button", name="📥 媒體下載器").click()
        page.get_by_role("button", name="▶️ YouTube 轉報告").click()
        page.get_by_role("button", name="📁 本機檔案轉錄").click()

        for button_id in ALL_BUTTON_IDS:
            if button_id == "#start-processing-btn":
                continue # 同上理由
            print(f"  - 正在檢查按鈕 {button_id}...")
            expect(page.locator(button_id)).to_be_enabled(timeout=5000)
        print("✅ 所有 AI 功能按鈕在就緒後均已啟用。")

        # 步驟 6: 執行舊有的核心流程驗證
        print("🚀 開始執行原有的 UI 互動測試...")
        media_downloader_tab = page.get_by_role("button", name="📥 媒體下載器")
        print("正在點擊 '媒體下載器' 分頁...")
        expect(media_downloader_tab).to_be_visible(timeout=5000)
        media_downloader_tab.click()
        print("✅ '媒體下載器' 分頁點擊成功。")

        real_time_output_area = page.locator('.transcript-output')
        print("正在驗證 '即時轉錄輸出' 區塊是否可見...")
        expect(real_time_output_area).to_be_hidden(timeout=5000)
        print("✅ '即時轉錄輸出' 區塊已成功驗證為不可見。")

        print("🎉 端對端測試流程驗證成功！")

    except Exception as e:
        print(f"❌ 測試過程中發生錯誤: {e}")
        screenshot_path = "/app/e2e_tests/final_error.png"
        page.screenshot(path=screenshot_path)
        print(f"📸 已儲存錯誤截圖至 {screenshot_path}")
        raise e
