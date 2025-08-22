import subprocess
import sys
import time
from pathlib import Path
import logging
import os
import socket

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('E2E_Orchestrator')
ROOT_DIR = Path(__file__).resolve().parent
API_GATEWAY_DIR = ROOT_DIR / "services" / "api_gateway"
JS_TEST_SCRIPT = ROOT_DIR / "run_browser_test.js"
E2E_TIMEOUT = 90

def find_free_port() -> int:
    """找到一個可用的網路埠口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def run_test_flow():
    """執行完整的測試流程：啟動伺服器 -> 執行 JS 測試 -> 關閉伺服器"""
    log.info("====== 開始執行新版 E2E 測試流程 ======")
    proc = None
    exit_code = 1 # 預設為失敗

    try:
        # --- 步驟 1: 清理環境 ---
        log.info("[1/4] 清理舊的資料庫檔案以確保測試冪等性...")
        for db_file in ["queue.db", "logs.db"]:
            if (ROOT_DIR / db_file).exists():
                (ROOT_DIR / db_file).unlink()
                log.info(f"已刪除舊檔案: {db_file}")

        # --- 步驟 2: 啟動後端伺服器 ---
        port = find_free_port()
        api_gateway_url = f"http://127.0.0.1:{port}"
        log.info(f"[2/4] 將在動態埠號 {port} 上啟動 API Gateway...")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)
        env["APP_ENV"] = "test"

        command = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)]

        # 使用 Popen 以便我們可以繼續執行其他步驟
        proc = subprocess.Popen(command, cwd=API_GATEWAY_DIR, stdout=sys.stdout, stderr=sys.stderr, text=True, encoding='utf-8', env=env)

        # 等待伺服器啟動
        log.info("等待 API Gateway 啟動 (最多 20 秒)...")
        time.sleep(10) # 簡單的等待時間，可以改進為更可靠的檢查

        # 檢查伺服器是否仍在運行
        if proc.poll() is not None:
            raise RuntimeError(f"API Gateway 啟動失敗，返回碼: {proc.poll()}")
        log.info("✅ API Gateway 似乎已成功啟動！")

        # --- 步驟 3: 執行 JavaScript Playwright 測試 ---
        log.info(f"[3/4] 執行 Node.js 測試腳本: {JS_TEST_SCRIPT}")

        # 將目標 URL 作為參數傳遞給 JS 腳本
        js_test_command = ["node", str(JS_TEST_SCRIPT), api_gateway_url]

        # 使用 run 並等待其完成，捕獲返回碼
        result = subprocess.run(js_test_command, capture_output=True, text=True, encoding='utf-8')

        # 印出 JS 腳本的輸出
        print("--- JavaScript 測試腳本輸出 ---")
        print(result.stdout)
        if result.stderr:
            print("--- JavaScript 測試腳本錯誤輸出 ---")
            print(result.stderr)
        print("---------------------------------")

        exit_code = result.returncode

    except Exception as e:
        log.error(f"❌ Python 流程控制器發生錯誤: {e}", exc_info=True)
        exit_code = 1
    finally:
        # --- 步驟 4: 關閉後端伺服器 ---
        log.info("[4/4] 測試結束，正在關閉 API Gateway...")
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
                log.info("伺服器已成功終止。")
            except subprocess.TimeoutExpired:
                log.warning("伺服器終止超時，強制終止。")
                proc.kill()

    return exit_code

if __name__ == "__main__":
    final_exit_code = run_test_flow()

    if final_exit_code == 0:
        log.info("✅✅✅ E2E 測試成功！ ✅✅✅")
    else:
        log.error(f"❌❌❌ E2E 測試失敗！(返回碼: {final_exit_code}) ❌❌❌")

    sys.exit(final_exit_code)
