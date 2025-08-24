import subprocess
import sys
import time
from pathlib import Path
import logging
import os
import socket
import threading

# --- 繁體中文註解：基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('統一E2E測試')
ROOT_DIR = Path(__file__).resolve().parent
API_GATEWAY_DIR = ROOT_DIR / "services" / "api_gateway"
VUE_APP_DIR = ROOT_DIR / "vue-app"
SCREENSHOT_PATH = ROOT_DIR / "debug_screenshot.png"
E2E_TIMEOUT = 120 # 總體超時時間

def execute_command(command, cwd, step_name):
    """執行一個 shell 指令並記錄日誌"""
    log.info(f"--- 開始步驟: {step_name} ---")
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=180 # 為每個指令設定180秒超時
        )
        log.info(f"✅ 步驟成功: {step_name}")
        log.debug(result.stdout)
        return True
    except FileNotFoundError:
        log.error(f"❌ 步驟失敗: {step_name} - 找不到指令 '{command[0]}'。請確保它已安裝並在系統路徑中。")
        return False
    except subprocess.TimeoutExpired:
        log.error(f"❌ 步驟失敗: {step_name} - 指令執行超時。")
        return False
    except subprocess.CalledProcessError as e:
        log.error(f"❌ 步驟失敗: {step_name} (返回碼: {e.returncode})")
        log.error(f"STDOUT:\n{e.stdout}")
        log.error(f"STDERR:\n{e.stderr}")
        return False

def find_free_port() -> int:
    """找到一個可用的網路埠口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def wait_for_server(port: int, timeout: int = 30) -> bool:
    """等待直到指定的埠口可以連線"""
    log.info(f"正在等待伺服器在埠號 {port} 上啟動...")
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                log.info(f"✅ 伺服器已在埠號 {port} 上就緒！")
                return True
        except (socket.timeout, ConnectionRefusedError):
            time.sleep(0.5)
    log.error(f"❌ 伺服器在 {timeout} 秒內未能啟動。")
    return False

def run_playwright_test(url: str):
    """使用 Playwright (Python) 執行瀏覽器測試"""
    log.info("--- 開始步驟: 執行 Playwright 瀏覽器測試 ---")
    from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            target_url = f"{url}/ui"
            log.info(f"導航至: {target_url}")
            page.goto(target_url, wait_until='domcontentloaded', timeout=20000)

            log.info(f"正在擷取螢幕畫面至: {SCREENSHOT_PATH}")
            page.screenshot(path=SCREENSHOT_PATH)
            log.info("✅ 螢幕畫面已擷取。")

            log.info("等待 Vue app 初始化 (等待 window.vue_app)...")
            page.wait_for_function('() => window.vue_app', timeout=15000)
            log.info("✅ 驗證成功: Vue app 已在瀏覽器中初始化！")

            # 增加一個簡單的畫面內容驗證
            log.info("正在驗證頁面標題...")
            expect(page).to_have_title("音訊轉錄儀")
            log.info("✅ 驗證成功: 頁面標題符合預期。")

            browser.close()
            log.info("✅ Playwright 測試成功！")
            return True
        except PlaywrightTimeoutError as e:
            log.error(f"❌ Playwright 測試超時: {e}")
            log.error(f"請檢查螢幕截圖 {SCREENSHOT_PATH} 以了解頁面當前的狀態。")
            return False
        except Exception as e:
            log.error(f"❌ Playwright 測試期間發生未預期錯誤: {e}", exc_info=True)
            if 'page' in locals():
                page.screenshot(path=SCREENSHOT_PATH)
                log.error(f"已儲存錯誤時的螢幕截圖至 {SCREENSHOT_PATH}。")
            return False

def main():
    """主測試流程控制器"""
    log.info("====== 開始執行統一的 E2E 測試腳本 ======")

    # 步驟 1: 準備環境
    if not execute_command(["bun", "install"], ROOT_DIR, "安裝 Playwright 節點依賴"): return 1
    if not execute_command(["npx", "playwright", "install", "--with-deps"], ROOT_DIR, "下載 Playwright 瀏覽器"): return 1
    if not execute_command([sys.executable, "-m", "pip", "install", "-r", str(API_GATEWAY_DIR / "requirements.txt")], API_GATEWAY_DIR, "安裝後端 Python 依賴"): return 1

    # 步驟 2: 清理舊檔案
    log.info("--- 開始步驟: 清理環境 ---")
    for db_file in ["queue.db", "logs.db"]:
        if (ROOT_DIR / db_file).exists():
            (ROOT_DIR / db_file).unlink()
            log.info(f"已刪除舊檔案: {db_file}")

    # 步驟 3: 建置前端
    if not execute_command(["bun", "install"], VUE_APP_DIR, "安裝前端依賴"): return 1
    if not execute_command(["bun", "run", "build"], VUE_APP_DIR, "建置前端應用"): return 1

    # 步驟 4: 啟動伺服器
    server_proc = None
    exit_code = 1
    try:
        port = find_free_port()
        api_url = f"http://127.0.0.1:{port}"
        log.info(f"--- 開始步驟: 啟動後端伺服器 (埠號: {port}) ---")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)

        server_command = [sys.executable, "-m", "uvicorn", "services.api_gateway.main:app", "--host", "0.0.0.0", "--port", str(port), "--log-level", "warning"]

        server_proc = subprocess.Popen(server_command, cwd=ROOT_DIR, stdout=sys.stdout, stderr=sys.stderr, text=True, encoding='utf-8', env=env)

        if not wait_for_server(port):
            raise RuntimeError("伺服器健康檢查失敗。")

        # 步驟 5: 執行 Playwright 測試
        if run_playwright_test(api_url):
            exit_code = 0 # 測試成功
        else:
            exit_code = 1 # 測試失敗

    except Exception as e:
        log.error(f"❌ 測試流程控制器發生錯誤: {e}", exc_info=True)
        exit_code = 1
    finally:
        log.info("--- 開始步驟: 關閉後端伺服器 ---")
        if server_proc and server_proc.poll() is None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
                log.info("伺服器已成功終止。")
            except subprocess.TimeoutExpired:
                log.warning("伺服器終止超時，正在強制終止。")
                server_proc.kill()

    if exit_code == 0:
        log.info("✅✅✅ E2E 測試全部通過！ ✅✅✅")
    else:
        log.error("❌❌❌ E2E 測試失敗！ ❌❌❌")

    return exit_code

if __name__ == "__main__":
    sys.exit(main())
