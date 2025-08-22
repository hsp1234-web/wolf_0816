import subprocess
import sys
import time
from pathlib import Path
import logging
import os
import socket

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('App_Orchestrator')
ROOT_DIR = Path(__file__).resolve().parent
API_GATEWAY_DIR = ROOT_DIR / "services" / "api_gateway"

def find_free_port() -> int:
    """找到一個可用的網路埠口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def run_app_flow():
    """執行完整的應用程式啟動流程"""
    log.info("====== 開始執行應用程式啟動流程 ======")
    proc = None

    try:
        # --- 步驟 1: 安裝後端依賴 ---
        log.info("[1/4] 安裝後端 Python 依賴...")
        requirements_path = API_GATEWAY_DIR / "requirements.txt"
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements_path)], check=True, capture_output=True, text=True, encoding='utf-8')
            log.info("✅ 後端依賴安裝成功。")
        except subprocess.CalledProcessError as e:
            log.error(f"❌ 後端依賴安裝失敗，返回碼: {e.returncode}")
            log.error(f"stdout:\n{e.stdout}")
            log.error(f"stderr:\n{e.stderr}")
            raise

        # --- 步驟 2: 清理環境 ---
        log.info("[2/4] 清理舊的資料庫檔案...")
        for db_file in ["queue.db", "logs.db"]:
            if (ROOT_DIR / db_file).exists():
                (ROOT_DIR / db_file).unlink()
                log.info(f"已刪除舊檔案: {db_file}")

        # --- 步驟 3: 建置前端應用程式 ---
        log.info("[3/4] 準備建置前端 Vue 應用程式...")
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

        # --- 步驟 4: 啟動後端伺服器 ---
        port = find_free_port()
        log.info(f"[4/4] 將在動態埠號 {port} 上啟動 API Gateway...")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)
        # For Colabpro to get the URL, we print it out.
        print(f"APP_URL: http://127.0.0.1:{port}", flush=True)

        command = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)]

        # 使用 Popen 以便我們可以繼續執行其他步驟
        proc = subprocess.Popen(command, cwd=API_GATEWAY_DIR, stdout=sys.stdout, stderr=sys.stderr, text=True, encoding='utf-8', env=env)

        log.info("✅ API Gateway 似乎已成功啟動！")
        log.info("應用程式已進入持續運行模式。按 Ctrl+C 來關閉。")
        proc.wait() # 等待伺服器程序結束

    except KeyboardInterrupt:
        log.info("收到使用者中斷指令，正在關閉...")
    except Exception as e:
        log.error(f"❌ Python 流程控制器發生錯誤: {e}", exc_info=True)
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
                log.info("伺服器已成功終止。")
            except subprocess.TimeoutExpired:
                log.warning("伺服器終止超時，強制終止。")
                proc.kill()

if __name__ == "__main__":
    run_app_flow()
