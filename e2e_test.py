import subprocess
import sys
import time
from pathlib import Path
import logging
import os
import socket
import threading
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 繁體中文註解：基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('Colab模擬器')
ROOT_DIR = Path(__file__).resolve().parent
VUE_APP_DIR = ROOT_DIR / "vue-app"
BAKE_SCRIPT_PATH = ROOT_DIR / "scripts" / "bake_dependencies.sh"
DEPS_ARCHIVE_PATH = ROOT_DIR / "dependencies.tar.gz"
SCREENSHOT_PATH = ROOT_DIR / "colab_sim_screenshot.png"
SIMULATION_TIMEOUT = 100 # 依照使用者要求設定100秒超時

def execute_command(command, cwd, step_name):
    """執行一個 shell 指令並記錄日誌"""
    log.info(f"--- {step_name} ---")
    try:
        result = subprocess.run(
            command, cwd=cwd, check=True, capture_output=True,
            text=True, encoding='utf-8', timeout=180
        )
        log.info(f"✅ {step_name} 成功")
        log.debug(result.stdout)
        return True
    except subprocess.TimeoutExpired:
        log.error(f"❌ {step_name} - 指令執行超時。")
        return False
    except subprocess.CalledProcessError as e:
        log.error(f"❌ {step_name} 失敗 (返回碼: {e.returncode})")
        log.error(f"STDERR:\n{e.stderr}")
        return False

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def wait_for_server_and_get_port(server_proc, timeout=30):
    log.info("等待 run.py 回報埠號...")
    start_time = time.monotonic()
    for line in iter(server_proc.stdout.readline, ''):
        if line.strip().startswith("APP_PORT:"):
            port = int(line.strip().split(":")[1])
            log.info(f"✅ 伺服器已回報埠號: {port}")
            return port
        if time.monotonic() - start_time > timeout:
            log.error("❌ 等待埠號超時。")
            return None
    return None

def run_simulation():
    # 使用 threading.Timer 實現總超時
    kill_flag = threading.Event()
    def timeout_handler():
        log.error(f"❌❌❌ 總模擬時間超過 {SIMULATION_TIMEOUT} 秒，強制中止！ ❌❌❌")
        kill_flag.set()

    timer = threading.Timer(SIMULATION_TIMEOUT, timeout_handler)
    timer.start()

    server_proc = None
    exit_code = 1
    try:
        # 步驟 1: 清理舊的依賴包
        if DEPS_ARCHIVE_PATH.exists():
            log.info("正在清理舊的依賴包...")
            DEPS_ARCHIVE_PATH.unlink()

        # 步驟 2: 建置前端
        if not execute_command(["bun", "install"], VUE_APP_DIR, "安裝前端依賴"): raise RuntimeError("前端依賴安裝失敗")
        if not execute_command(["bun", "run", "build"], VUE_APP_DIR, "建置前端應用"): raise RuntimeError("前端建置失敗")

        # 步驟 3: 烘烤依賴包 (這是模擬的關鍵)
        if not execute_command(["bash", str(BAKE_SCRIPT_PATH)], ROOT_DIR, "執行依賴烘烤腳本"): raise RuntimeError("烘烤依賴失敗")
        if not DEPS_ARCHIVE_PATH.exists(): raise RuntimeError("烘烤腳本未成功產生依賴包")

        # 步驟 4: 像 Colabpro.py 一樣啟動伺服器
        log.info(f"--- 使用烘烤過的依賴包 '{DEPS_ARCHIVE_PATH}' 啟動伺服器 ---")
        server_command = [sys.executable, "run.py", "--deps-path", str(DEPS_ARCHIVE_PATH)]
        server_proc = subprocess.Popen(
            server_command, cwd=ROOT_DIR, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding='utf-8'
        )

        # 增加一個線程來監控和打印 stderr
        def log_stderr():
            if server_proc.stderr:
                for line in iter(server_proc.stderr.readline, ''):
                    log.error(f"[SERVER STDERR] {line.strip()}")

        stderr_thread = threading.Thread(target=log_stderr)
        stderr_thread.daemon = True
        stderr_thread.start()

        port = wait_for_server_and_get_port(server_proc)
        if not port: raise RuntimeError("無法從伺服器獲取埠號。")
        api_url = f"http://127.0.0.1:{port}"

        # 步驟 5: Playwright 驗證
        log.info(f"--- 使用 Playwright 驗證 {api_url} ---")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                response = page.goto(api_url, wait_until='domcontentloaded', timeout=20000)
                page_content = page.content()
                log.info(f"頁面狀態碼: {response.status if response else 'N/A'}")
                log.info(f"頁面內容 (前200字): {page_content[:200]}")
                page.screenshot(path=SCREENSHOT_PATH)
                log.info(f"✅ 已擷取螢幕畫面至: {SCREENSHOT_PATH}")

                if "Frontend entry point (index.html) not found." in page_content:
                    log.error("❌ 驗證失敗: 伺服器回傳了 'index.html not found' 錯誤！成功重現問題。")
                    exit_code = 1 # 保持失敗狀態
                else:
                    log.info("✅ 頁面似乎已載入，但未出現預期的錯誤訊息。請檢查截圖。")
                    exit_code = 0 # 標記為成功以便觀察

            except PlaywrightTimeoutError as e:
                log.error(f"❌ Playwright 導航超時: {e}")
                exit_code = 1
            finally:
                browser.close()

    except Exception as e:
        log.error(f"模擬流程發生錯誤: {e}", exc_info=True)
        exit_code = 1
    finally:
        if server_proc and server_proc.poll() is None:
            log.info("正在關閉伺服器...")
            server_proc.terminate()
            server_proc.wait(timeout=5)

        timer.cancel() # 確保計時器被取消
        if kill_flag.is_set():
             sys.exit(1) # 如果是因超時而退出，返回失敗碼

    return exit_code

if __name__ == "__main__":
    final_code = run_simulation()
    if final_code == 0:
        log.info("✅ 模擬器執行完畢 (未重現錯誤)。")
    else:
        log.error("❌ 模擬器執行完畢 (成功重現錯誤或發生其他問題)。")
    sys.exit(final_code)
