# e2e_tests/test_full_workflow.py
import pytest
import time
import sys
from playwright.sync_api import sync_playwright, Page, expect
from pathlib import Path

# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent

# 讓腳本可以導入 src 下的模組
sys.path.insert(0, str(ROOT_DIR / "src"))
from db.client import get_client as get_db_client

# 假的音訊檔案路徑
DUMMY_AUDIO_PATH = ROOT_DIR / "e2e_tests" / "fixtures" / "test.mp3"

def run_workflow_test(page: Page, target_url: str):
    """
    執行核心上傳工作流程的函式。
    """
    # 建立一個獨立的 DB client 來驗證後端
    db_client = get_db_client()

    try:
        # --- 步驟 1: 載入頁面並驗證初始狀態 ---
        print(f"導航至: {target_url}")
        page.goto(target_url, timeout=30000)

        print("驗證頁面標題...")
        expect(page).to_have_title("音訊轉錄儀", timeout=10000)
        print("✅ 頁面載入與標題驗證成功！")

        # 記錄上傳前的任務數量
        initial_tasks = db_client.get_all_tasks()
        initial_task_count = len(initial_tasks)
        print(f"上傳前的任務數量: {initial_task_count}")

        # --- 確保模型已就緒 ---
        print("--- 確保 Whisper 模型已就緒 ---")
        model_button = page.locator('//button[contains(., "模型")]')
        expect(model_button).to_be_visible(timeout=10000)

        if "下載模型" in model_button.inner_text():
            print("模型尚未就緒，正在點擊下載按鈕...")
            model_button.click()

        expect(model_button).to_have_text("✅ 模型已就緒", timeout=20000)
        print("✅ 模型已成功就緒！")

        # --- 步驟 1.2: 模擬檔案上傳 ---
        print("--- 步驟 1.2: 模擬檔案上傳 ---")
        file_input = page.locator("#file-input-trigger")
        expect(file_input).to_be_attached()
        print(f"正在設定輸入檔案: {DUMMY_AUDIO_PATH}")
        file_input.set_input_files(DUMMY_AUDIO_PATH)

        expect(page.locator("#file-list").get_by_text("test.mp3")).to_be_visible(timeout=5000)
        print("✅ 檔案 'test.mp3' 已成功顯示在待上傳列表。")

        start_button = page.locator("#start-processing-btn")
        expect(start_button).to_be_enabled(timeout=5000)
        print("正在點擊 '開始處理' 按鈕...")
        start_button.click()

        # --- 驗證後端是否收到指令 ---
        print("--- 驗證後端是否已建立新任務 ---")
        new_task_found = False
        start_wait_time = time.time()
        while time.time() - start_wait_time < 20:
            current_tasks = db_client.get_all_tasks()
            if len(current_tasks) > initial_task_count:
                new_task_found = True
                print(f"✅ 在 {time.time() - start_wait_time:.2f} 秒後，資料庫中出現了新任務！")
                break
            time.sleep(1)

        assert new_task_found, "❌ 在 20 秒內資料庫未出現新任務。"

        new_task = [t for t in current_tasks if t['task_id'] not in [it['task_id'] for it in initial_tasks]][0]
        assert new_task['task_type'] == 'transcription', f"新任務類型應為 'transcription'，但卻是 '{new_task['task_type']}'"
        assert new_task['status'] == 'pending', f"新任務狀態應為 'pending'，但卻是 '{new_task['status']}'"
        print(f"✅ 新任務 (ID: {new_task['task_id']}) 的內容驗證成功！")

        page.screenshot(path="e2e_tests/screenshots/1.2_upload_success.png")
        print("📸 已儲存上傳成功截圖。")

    except Exception as e:
        page.screenshot(path="e2e_tests/screenshots/1.2_upload_failure.png")
        print(f"❌ 測試過程中發生錯誤，已儲存失敗截圖。")
        raise

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("錯誤：請提供一個 URL 作為參數。")
        print("用法: python e2e_tests/test_full_workflow.py <URL>")
        sys.exit(1)

    server_url = sys.argv[1]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            run_workflow_test(page, server_url)
            print("\n🎉🎉🎉 端對端工作流程驗證成功！ 🎉🎉🎉")
        finally:
            browser.close()
