# -*- coding: utf-8 -*-
import subprocess
import sys
import re
import time
from pathlib import Path
import logging
import os

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('StartupTest')
ROOT_DIR = Path(__file__).resolve().parent
COLAB_SCRIPT_PATH = ROOT_DIR / "Colabpro.py"

# --- 超時設定 ---
# 測試安裝+啟動+驗證的總超時
E2E_TIMEOUT = 60

def install_dependencies():
    """安裝測試所需的核心依賴。"""
    log.info("--- [步驟 1/4] 安裝 E2E 測試核心依賴 ---")
    dependencies = ["playwright", "ipython", "pytz"]
    try:
        log.info(f"使用 pip 安裝: {', '.join(dependencies)}...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q"] + dependencies, check=True)
        log.info("安裝 Playwright 瀏覽器...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps"], check=True, capture_output=True, text=True)
        log.info("✅ 核心依賴安裝成功。")
        return True
    except Exception as e:
        log.error(f"❌ 核心依賴安裝失敗: {e}")
        return False

def run_and_verify():
    """
    執行 Colabpro.py 腳本，並驗證其啟動流程與核心UI功能。
    此函式包含完整的端對端測試邏輯。
    """
    log.info(f"--- [步驟 2/4] 執行啟動腳本: {COLAB_SCRIPT_PATH} (總超時: {E2E_TIMEOUT}秒) ---")
    assert COLAB_SCRIPT_PATH.exists(), f"❌ 啟動腳本不存在: {COLAB_SCRIPT_PATH}"

    url = None
    proc = None
    start_time = time.monotonic()

    try:
        env = os.environ.copy()
        env["IN_TEST_MODE"] = "1"
        proc = subprocess.Popen(
            [sys.executable, "-u", str(COLAB_SCRIPT_PATH)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
            env=env
        )
        log.info("監聽啟動日誌以捕獲 URL...")
        while time.monotonic() - start_time < E2E_TIMEOUT:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    log.error("❌ 啟動腳本提前終止，未能成功啟動伺服器。")
                    return None
                time.sleep(0.1)
                continue
            log.info(f"[Colabpro]: {line.strip()}")
            if line.strip().startswith("APP_URL:"):
                match = re.search(r"APP_URL:\s*(https?://[^\s]+)", line)
                if match:
                    url = match.group(1)
                    log.info(f"✅ 成功從契約捕獲本地伺服器 URL: {url}")
                    break
        if not url:
            log.error(f"❌ 在 {E2E_TIMEOUT} 秒內未能捕獲到 URL。啟動超時。")
            return None

        # --- Playwright 驗證 ---
        log.info(f"--- [步驟 3/4] 使用 Playwright 驗證 UI 與核心功能 ---")
        from playwright.sync_api import sync_playwright, expect

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            # 增加日誌以追蹤 Playwright 操作
            def log_playwright(msg): log.info(f"[Playwright] {msg}")

            try:
                log_playwright(f"導航至: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # 驗證 1: 等待後端上線的關鍵指標出現
                log_playwright("等待儀表板狀態變為『在線』...")
                # 使用正則表達式來匹配，更具彈性
                status_locator = page.locator("text=/狀態:.*在線/")
                expect(status_locator).to_be_visible(timeout=30000)
                log_playwright("✅ 驗證成功：儀表板顯示服務在線！")

                # 驗證 2: 執行點擊操作並驗證結果
                log_playwright("測試『複製日誌』按鈕...")
                copy_button_locator = page.get_by_role("button", name="複製日誌")
                expect(copy_button_locator).to_be_enabled(timeout=10000)
                copy_button_locator.click()

                # 驗證 3: 等待操作結果 (預期會彈出一個通知)
                log_playwright("等待『複製成功』的通知...")
                notification_locator = page.locator("div.notification-success:has-text('日誌已複製到剪貼簿！')")
                expect(notification_locator).to_be_visible(timeout=5000)
                log_playwright("✅ 驗證成功：成功複製日誌並看到通知！")

                screenshot_path = ROOT_DIR / "final_e2e_success.png"
                page.screenshot(path=str(screenshot_path))
                log.info(f"✅ 成功擷取最終驗證畫面至: {screenshot_path}")

            except Exception as e:
                log.error(f"❌ Playwright 驗證失敗: {e}")
                # 失敗時也截圖，以利除錯
                failure_screenshot_path = ROOT_DIR / "final_e2e_failure.png"
                try:
                    page.screenshot(path=str(failure_screenshot_path))
                    log.info(f"已擷取失敗畫面至: {failure_screenshot_path}")
                except Exception as screenshot_e:
                    log.error(f"擷取失敗畫面時也發生錯誤: {screenshot_e}")
                return None # 表示驗證失敗
            finally:
                browser.close()

        log.info(f"--- [步驟 4/4] 所有驗證通過 ---")
        return url
    finally:
        if proc and proc.poll() is None:
            log.info("正在終止 Colabpro.py 子程序...")
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill()
            log.info("✅ 子程序已終止。")

def main():
    log.info("====== 開始執行新架構啟動流程端對端驗證 ======")
    start_time = time.monotonic()

    if not install_dependencies():
        log.critical("====== 驗證失敗：無法安裝核心依賴 ======")
        sys.exit(1)

    try:
        final_url = run_and_verify()
        if final_url:
            elapsed = time.monotonic() - start_time
            log.info(f"✅✅✅ 驗證成功！在 {elapsed:.2f} 秒內成功啟動並驗證了應用。✅✅✅")
            print("\n[SUCCESS] The end-to-end test passed.")
            sys.exit(0)
        else:
            log.critical("❌❌❌ 驗證失敗！啟動流程未能成功完成。❌❌❌")
            print("\n[FAILURE] The end-to-end test failed.")
            sys.exit(1)
    except Exception as e:
        log.critical(f"❌ 測試過程中發生未預期的錯誤: {e}", exc_info=True)
        print("\n[FAILURE] The end-to-end test failed due to an unexpected error.")
        sys.exit(1)

if __name__ == "__main__":
    main()
