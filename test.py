# -*- coding: utf-8 -*-
import subprocess
import sys
import re
import time
from pathlib import Path
import logging
import types

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('StartupTest')
ROOT_DIR = Path(__file__).resolve().parent
COLAB_SCRIPT_PATH = ROOT_DIR / "Colabpro.py"

# --- 超時設定 ---
OVERALL_TIMEOUT = 120
URL_TIMEOUT = 60

def setup_mocks():
    """建立並注入一個假的 google.colab 模組以避免 ImportError。"""
    log.info("--- [Mock] 建立虛假的 google.colab 模組 ---")

    # 建立假的 output 物件
    class FakeColabOutput:
        def eval_js(self, script):
            log.info(f"--- [Mocked eval_js] 呼叫了，但什麼也沒做。腳本: {script[:70]}...")
            # 在測試環境中，我們不依賴 JS 的回傳值，
            # 而是依賴 Colabpro.py 直接 print 的 URL。
            return None

    # 建立假的模組
    google_module = types.ModuleType('google')
    google_colab_module = types.ModuleType('google.colab')
    google_colab_output_module = types.ModuleType('google.colab.output')

    # 將假的 output 物件附加到模組上
    google_colab_output_module.eval_js = FakeColabOutput().eval_js
    google_colab_module.output = google_colab_output_module
    google_module.colab = google_colab_module

    # 注入到 sys.modules 中，這樣 import 語句就能找到它們
    sys.modules['google'] = google_module
    sys.modules['google.colab'] = google_colab_module
    sys.modules['google.colab.output'] = google_colab_output_module

    log.info("✅ 虛假模組注入成功。")

def install_dependencies():
    """安裝測試所需的核心依賴。"""
    log.info("--- [1/3] 安裝測試核心依賴 ---")
    # 不再需要 google-colab，因為我們已經模擬了它
    dependencies = ["playwright", "ipython", "pytz"]
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
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
    """執行 Colabpro.py 腳本，並驗證其啟動流程。"""
    log.info(f"--- [2/3] 執行啟動腳本: {COLAB_SCRIPT_PATH} ---")
    assert COLAB_SCRIPT_PATH.exists(), f"❌ 啟動腳本不存在: {COLAB_SCRIPT_PATH}"

    url = None
    proc = None
    start_time = time.monotonic()

    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(COLAB_SCRIPT_PATH)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        log.info("監聽啟動日誌以捕獲 URL...")
        while time.monotonic() - start_time < URL_TIMEOUT:
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
            log.error(f"❌ 在 {URL_TIMEOUT} 秒內未能捕獲到 URL。啟動超時。")
            return None

        log.info(f"--- [3/3] 使用 Playwright 驗證 URL ---")
        from playwright.sync_api import sync_playwright, expect
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            log.info(f"導航至: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            expected_title = "音訊轉錄儀"
            expect(page).to_have_title(expected_title, timeout=10000)
            log.info(f"✅ 頁面標題 '{expected_title}' 驗證成功！")
            screenshot_path = ROOT_DIR / "final_startup_success.png"
            page.screenshot(path=str(screenshot_path))
            log.info(f"✅ 成功擷取螢幕截圖至: {screenshot_path}")
            browser.close()
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

    setup_mocks()

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
