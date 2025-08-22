# -*- coding: utf-8 -*-
import subprocess
import sys
import re
import time
from pathlib import Path
import logging
import os

import socket

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('E2E_Test')
ROOT_DIR = Path(__file__).resolve().parent
API_GATEWAY_DIR = ROOT_DIR / "services" / "api_gateway"

# --- 超時設定 ---
E2E_TIMEOUT = 60

def find_free_port() -> int:
    """動態尋找一個可用的埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def install_dependencies():
    """安裝測試所需的核心依賴。"""
    log.info("--- [步驟 1/3] 安裝 E2E 測試核心依賴 ---")
    # 步驟 1: 安裝 API Gateway 的依賴，以確保測試執行環境擁有 uvicorn 等核心套件
    gateway_reqs = API_GATEWAY_DIR / "requirements.txt"
    test_deps = ["playwright", "pytz"] # requests 等會被 gateway 的依賴包含
    try:
        log.info(f"正在從 {gateway_reqs} 安裝 API Gateway 的依賴...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(gateway_reqs)], check=True)
        log.info(f"正在安裝測試專用的額外依賴: {', '.join(test_deps)}...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q"] + test_deps, check=True)
        log.info("安裝 Playwright 瀏覽器...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps"], check=True, capture_output=True, text=True)
        log.info("✅ 核心依賴安裝成功。")
        return True
    except Exception as e:
        log.error(f"❌ 核心依賴安裝失敗: {e}")
        return False

def run_and_verify():
    """
    直接啟動 API Gateway，並驗證其啟動流程與核心UI功能。
    """
    log.info(f"--- [步驟 2/3] 啟動 API Gateway (總超時: {E2E_TIMEOUT}秒) ---")

    proc = None
    start_time = time.monotonic()

    try:
        # 動態尋找可用埠號
        port = find_free_port()
        api_gateway_url = f"http://127.0.0.1:{port}"
        log.info(f"將在動態埠號 {port} 上啟動 API Gateway...")

        # 在新架構中，我們直接測試核心服務 api_gateway
        # 它會負責初始化資料庫和啟動背景工作者
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)

        command = [
            sys.executable, "-m", "uvicorn",
            "main:app",
            "--host", "0.0.0.0",
            "--port", str(port)
        ]

        proc = subprocess.Popen(
            command,
            cwd=API_GATEWAY_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
            env=env
        )

        # 監聽 API Gateway 的啟動日誌
        log.info("監聽 API Gateway 啟動日誌...")
        gateway_ready = False
        while time.monotonic() - start_time < 20: # 給 20 秒啟動時間
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    log.error("❌ API Gateway 啟動失敗，程序提前終止。")
                    return None
                time.sleep(0.2)
                continue

            log.info(f"[API_Gateway]: {line.strip()}")
            if "Uvicorn running on" in line:
                log.info("✅ API Gateway 已成功啟動！")
                gateway_ready = True
                break

        if not gateway_ready:
            log.error("❌ 在 20 秒內 API Gateway 未能啟動。")
            return None

        # --- Playwright 驗證 ---
        log.info(f"--- [步驟 3/3] 使用 Playwright 驗證 UI 與核心功能 ---")
        from playwright.sync_api import sync_playwright, expect

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            def log_playwright(msg): log.info(f"[Playwright] {msg}")

            try:
                log_playwright(f"導航至: {api_gateway_url}")
                page.goto(api_gateway_url, wait_until="domcontentloaded", timeout=20000)

                # 驗證 1: 等待後端上線的關鍵指標出現
                log_playwright("等待儀表板狀態變為『準備就緒』...")
                # 根據 Dashboard.vue 的原始碼，我們鎖定 #status-text 元素
                status_locator = page.locator("#status-text")
                expect(status_locator).to_have_text("準備就緒", timeout=30000)
                log_playwright("✅ 驗證成功：儀表板顯示服務準備就緒！")

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
                failure_screenshot_path = ROOT_DIR / "final_e2e_failure.png"
                try:
                    page.screenshot(path=str(failure_screenshot_path))
                    log.info(f"已擷取失敗畫面至: {failure_screenshot_path}")
                except Exception as screenshot_e:
                    log.error(f"擷取失敗畫面時也發生錯誤: {screenshot_e}")
                return False
            finally:
                browser.close()

        return True
    finally:
        if proc and proc.poll() is None:
            log.info("正在清理，終止 API Gateway 子程序...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
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
