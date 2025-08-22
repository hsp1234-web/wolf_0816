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
        # --- 步驟 1: 安裝 E2E 測試執行器的依賴 (Playwright) ---
        log.info("[1/8] 安裝 E2E 測試節點依賴 (Playwright)...")
        try:
            subprocess.run(["bun", "install"], cwd=ROOT_DIR, check=True, capture_output=True, text=True, encoding='utf-8')
            log.info("✅ Playwright 依賴安裝成功。")
        except FileNotFoundError:
            log.error("❌ 'bun' 命令未找到。請確保 Bun 已安裝。")
            raise
        except subprocess.CalledProcessError as e:
            log.error(f"❌ Playwright 依賴安裝失敗: {e.stderr}")
            raise

        # --- 步驟 2: 下載 Playwright 瀏覽器 ---
        log.info("[2/8] 下載 Playwright 所需的瀏覽器...")
        try:
            # 使用 npx 來確保我們執行的是專案本地安裝的 Playwright 版本
            subprocess.run(["npx", "playwright", "install", "--with-deps"], cwd=ROOT_DIR, check=True, capture_output=True, text=True, encoding='utf-8')
            log.info("✅ Playwright 瀏覽器下載成功。")
        except subprocess.CalledProcessError as e:
            log.error(f"❌ Playwright 瀏覽器下載失敗: {e.stderr}")
            raise

        # --- 步驟 3: 安裝後端依賴 ---
        log.info("[3/8] 安裝後端 Python 依賴...")
        requirements_path = API_GATEWAY_DIR / "requirements.txt"
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements_path)], check=True, capture_output=True, text=True, encoding='utf-8')
            log.info("✅ 後端依賴安裝成功。")
        except subprocess.CalledProcessError as e:
            log.error(f"❌ 後端依賴安裝失敗，返回碼: {e.returncode}")
            log.error(f"stdout:\n{e.stdout}")
            log.error(f"stderr:\n{e.stderr}")
            raise

        # --- 步驟 4: 清理環境 ---
        log.info("[4/8] 清理舊的資料庫檔案以確保測試冪等性...")
        for db_file in ["queue.db", "logs.db"]:
            if (ROOT_DIR / db_file).exists():
                (ROOT_DIR / db_file).unlink()
                log.info(f"已刪除舊檔案: {db_file}")

        # --- 步驟 5: 建置前端應用程式 ---
        log.info("[5/8] 準備建置前端 Vue 應用程式...")
        vue_app_dir = ROOT_DIR / "vue-app"
        try:
            log.info("正在安裝前端依賴 (bun install)...")
            subprocess.run(["bun", "install"], cwd=vue_app_dir, check=True, capture_output=True, text=True, encoding='utf-8')
            log.info("✅ 前端依賴安裝成功。")

            log.info("正在建置前端應用 (bun run build)...")
            build_result = subprocess.run(["bun", "run", "build"], cwd=vue_app_dir, check=True, capture_output=True, text=True, encoding='utf-8')
            log.info("✅ 前端應用建置成功。")
            log.debug(f"Vite build output:\n{build_result.stdout}")

        except FileNotFoundError:
            log.error("❌ 建置失敗：找不到 'bun' 命令。請確定 Bun 已安裝並在系統路徑中。")
            raise
        except subprocess.CalledProcessError as e:
            log.error(f"❌ 前端建置失敗，返回碼: {e.returncode}")
            log.error(f"stdout:\n{e.stdout}")
            log.error(f"stderr:\n{e.stderr}")
            raise

        # --- 步驟 6: 啟動後端伺服器 ---
        port = find_free_port()
        api_gateway_url = f"http://127.0.0.1:{port}"
        log.info(f"[6/8] 將在動態埠號 {port} 上啟動 API Gateway...")

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

        # --- 步驟 7: 執行 JavaScript Playwright 測試 ---
        log.info(f"[7/8] 執行 Node.js 測試腳本: {JS_TEST_SCRIPT}")

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
        # --- 步驟 8: 關閉後端伺服器 ---
        log.info("[8/8] 測試結束，正在關閉 API Gateway...")
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
