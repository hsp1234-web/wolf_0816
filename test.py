# test.py - Standalone E2E Verification Script
import subprocess
import sys
import os
import re
import time
import logging
from pathlib import Path
import threading

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('StandaloneTest')
ROOT_DIR = Path(__file__).resolve().parent

def install_test_dependencies():
    """安裝此測試腳本本身需要的依賴，主要是 playwright。"""
    log.info("--- [測試步驟 1/4] 安裝測試依賴 (playwright) ---")
    try:
        log.info("確保 'uv' 已安裝...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)

        log.info("使用 uv 安裝 playwright...")
        # 我們需要 playwright 來執行瀏覽器操作
        subprocess.run([sys.executable, "-m", "uv", "pip", "install", "-q", "playwright"], check=True, capture_output=True)

        log.info("安裝 Playwright 瀏覽器...")
        subprocess.run([sys.executable, "-m", "playwright", "install"], check=True, capture_output=True)

        log.info("✅ 測試依賴安裝成功。")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ 安裝測試依賴失敗: {e.stderr}")
        return False
    except Exception as e:
        log.error(f"❌ 安裝測試依賴時發生未預期錯誤: {e}")
        return False

def run_server_and_get_url():
    """
    執行模組化啟動器，並從其輸出中捕捉最終的伺服器 URL。
    """
    log.info("--- [測試步驟 2/4] 執行 runner.py 以啟動伺服器 ---")
    runner_script_path = ROOT_DIR / "runner" / "main_runner.py"

    if not runner_script_path.exists():
        log.error(f"❌ 找不到啟動器腳本: {runner_script_path}")
        return None, None

    log.info(f"執行啟動命令: {sys.executable} {runner_script_path}")
    runner_proc = subprocess.Popen(
        [sys.executable, str(runner_script_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8'
    )

    url_pattern = re.compile(r"FINAL_URL:\s*(https?://[^\s]+)")
    server_url = None
    timeout = 120  # 給予更長的超時時間
    start_time = time.time()

    # 使用執行緒非阻塞地讀取 stderr
    stderr_lines = []
    def log_stderr():
        for line in iter(runner_proc.stderr.readline, ''):
            log.warning(f"[Runner stderr]: {line.strip()}")
            stderr_lines.append(line)

    stderr_thread = threading.Thread(target=log_stderr)
    stderr_thread.daemon = True
    stderr_thread.start()

    for line in iter(runner_proc.stdout.readline, ''):
        log.info(f"[Runner stdout]: {line.strip()}")
        match = url_pattern.search(line)
        if match:
            server_url = match.group(1)
            log.info(f"✅ 從啟動器成功解析到 URL: {server_url}")
            break
        if time.time() - start_time > timeout:
            log.error(f"❌ 啟動器未能在 {timeout} 秒內輸出 FINAL_URL。")
            break

    if not server_url:
        log.error("❌ 未能獲取伺服器 URL。")
        runner_proc.kill()
        return None, None

    return server_url, runner_proc

def verify_url_with_playwright(url: str):
    """
    使用 Playwright 開啟給定的 URL 並驗證頁面內容。
    """
    log.info(f"--- [測試步驟 3/4] 使用 Playwright 驗證 URL: {url} ---")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            log.info(f"正在導航至 {url}...")
            page.goto(url, timeout=30000)

            # 驗證標題
            expected_title = "音訊轉錄儀"
            log.info(f"正在驗證頁面標題是否為 '{expected_title}'...")
            if expected_title not in page.title():
                log.error(f"❌ 標題驗證失敗！預期: '{expected_title}', 實際: '{page.title()}'")
                page.screenshot(path="test_failure_screenshot.png")
                log.error("📸 已儲存失敗截圖至 test_failure_screenshot.png")
                return False
            log.info("✅ 頁面標題驗證成功。")

            # 驗證關鍵元素
            header_text = "音訊轉錄儀 (Vue)"
            log.info(f"正在驗證是否存在標題元素 '{header_text}'...")
            header_element = page.get_by_role("heading", name=header_text)

            header_element.wait_for(state="visible", timeout=10000)
            if not header_element.is_visible():
                 log.error(f"❌ 關鍵元素 '{header_text}' 驗證失敗！元素不存在或不可見。")
                 page.screenshot(path="test_failure_screenshot.png")
                 log.error("📸 已儲存失敗截圖至 test_failure_screenshot.png")
                 return False
            log.info("✅ 關鍵介面元素驗證成功。")

            browser.close()
            return True
        except Exception as e:
            log.error(f"❌ Playwright 驗證過程中發生錯誤: {e}", exc_info=True)
            if 'page' in locals():
                page.screenshot(path="test_failure_screenshot.png")
                log.error("📸 已儲存失敗截圖至 test_failure_screenshot.png")
            return False

def main():
    log.info("====== 開始執行端到端啟動驗證 ======")

    if not install_test_dependencies():
        log.critical("====== 驗證失敗：無法安裝測試所需依賴 ======")
        sys.exit(1)

    server_url, runner_proc = run_server_and_get_url()

    if not server_url or not runner_proc:
        log.critical("====== 驗證失敗：無法啟動伺服器 ======")
        sys.exit(1)

    # 伺服器已啟動，現在用 Playwright 驗證
    is_verified = False
    try:
        is_verified = verify_url_with_playwright(server_url)
    finally:
        # 無論驗證是否成功，都確保關閉伺服器
        log.info("--- [測試步驟 4/4] 清理並關閉伺服器 ---")
        if runner_proc.poll() is None:
            runner_proc.terminate()
            try:
                runner_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                runner_proc.kill()
        log.info("✅ 伺服器進程已關閉。")

    if is_verified:
        log.info("✅✅✅ 驗證成功！啟動流程看起來運作正常。✅✅✅")
        print("\n[SUCCESS] The end-to-end test passed.")
        sys.exit(0)
    else:
        log.critical("❌❌❌ 驗證失敗！啟動流程存在問題。❌❌❌")
        print("\n[FAILURE] The end-to-end test failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
