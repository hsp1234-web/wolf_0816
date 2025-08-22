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
OVERALL_TIMEOUT = 120
URL_TIMEOUT = 60

def install_dependencies():
    """安裝測試所需的核心依賴。"""
    log.info("--- [1/3] 安裝測試核心依賴 ---")
    # 不再需要 google-colab，因為 Colabpro.py 會自我模擬
    dependencies = ["playwright", "ipython", "pytz"]
    try:
        # 使用 pip 安裝，因為 uv 在此環境中解析 google-colab 有問題
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
        # 設定環境變數，通知 Colabpro.py 進入測試模式
        env = os.environ.copy()
        env["IN_TEST_MODE"] = "1"

        proc = subprocess.Popen(
            [sys.executable, "-u", str(COLAB_SCRIPT_PATH)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
            env=env # 傳遞修改後的環境變數
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

        # 增加一個健壯的埠號檢查迴圈，以取代固定的 sleep，從而更可靠地處理競爭條件
        port = int(url.split(":")[-1].split("/")[0])
        host = "127.0.0.1"
        log.info(f"伺服器 URL 已捕獲。正在於 {host}:{port} 輪詢，等待服務啟動...")

        import socket
        start_poll_time = time.monotonic()
        port_ready = False
        while time.monotonic() - start_poll_time < 15: # 最多等待 15 秒
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                try:
                    s.connect((host, port))
                    port_ready = True
                    log.info(f"✅ 埠號 {port} 已開啟！服務已就緒。")
                    break
                except (socket.timeout, ConnectionRefusedError):
                    log.info(f"埠號 {port} 尚未開啟，重試中...")
                    time.sleep(1)

        if not port_ready:
            log.error(f"❌ 在 15 秒內，埠號 {port} 未能開啟。伺服器啟動失敗。")
            # 為了除錯，我們嘗試讀取程序的剩餘輸出
            proc.terminate()
            stdout, _ = proc.communicate(timeout=5)
            log.error(f"伺服器剩餘輸出:\n{stdout}")
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
