# test.py - Standalone E2E Verification Script
import subprocess
import sys
import os
import re
import time
import logging
from pathlib import Path
import threading
import importlib.util

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
    timeout = 120  # 增加超時以應對較慢的啟動
    start_time = time.time()

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

def main():
    log.info("====== 開始執行端到端啟動驗證 ======")

    scratch_dir = Path("jules-scratch/verification")
    scratch_dir.mkdir(parents=True, exist_ok=True)

    if not install_test_dependencies():
        log.critical("====== 驗證失敗：無法安裝測試所需依賴 ======")
        sys.exit(1)

    server_url, runner_proc = run_server_and_get_url()

    if not server_url or not runner_proc:
        log.critical("====== 驗證失敗：無法啟動伺服器 ======")
        sys.exit(1)

    is_verified = False
    try:
        log.info(f"--- [測試步驟 3/4] 使用自定義腳本驗證 URL: {server_url} ---")

        # 動態載入我們的驗證模組
        module_path = scratch_dir / "verify_simple.py"
        spec = importlib.util.spec_from_file_location("verify_simple", module_path)
        verify_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify_module)

        # 執行驗證函式
        verify_module.run_verification(server_url)

        is_verified = True
        log.info("✅ 自定義驗證腳本執行成功。")
    except Exception as e:
        log.error(f"❌ 自定義驗證腳本執行失敗: {e}", exc_info=True)
        is_verified = False
    finally:
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
