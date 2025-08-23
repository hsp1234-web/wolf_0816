import subprocess
import sys
import time
from pathlib import Path
import logging
import os
import socket
import shutil

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('App_Orchestrator')
ROOT_DIR = Path(__file__).resolve().parent
API_GATEWAY_DIR = ROOT_DIR / "services" / "api_gateway"
DB_MANAGER_DIR = ROOT_DIR / "src" / "db"
DB_MANAGER_SCRIPT = DB_MANAGER_DIR / "manager.py"
DB_MANAGER_READY_FILE = DB_MANAGER_DIR / "db_manager.ready"

def find_free_port() -> int:
    """找到一個可用的網路埠口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def ensure_bun_installed():
    """檢查 bun 是否已安裝，如果沒有，則自動安裝。"""
    try:
        subprocess.run(["bun", "--version"], check=True, capture_output=True)
        log.info("✅ Bun 已安裝。")
    except (subprocess.CalledProcessError, FileNotFoundError):
        log.warning("⚠️ Bun 未安裝，正在嘗試自動安裝...")
        try:
            # 使用官方指令碼進行安裝
            install_command = "curl -fsSL https://bun.sh/install | bash"
            # run with shell=True is needed to handle the pipe `|`
            subprocess.run(install_command, shell=True, check=True, capture_output=True, text=True)

            # 重要：安裝後，bun 的執行檔位於 ~/.bun/bin。需要將其加入到 PATH。
            # Colab 和其他標準 Linux 環境會自動處理 .bashrc or .profile，
            # 但為了在此次執行的剩餘部分中立即生效，我們手動加入。
            bun_path = str(Path.home() / ".bun" / "bin")
            os.environ["PATH"] = f"{bun_path}{os.pathsep}{os.environ['PATH']}"

            log.info("✅ Bun 已成功安裝。")
            # 再次驗證
            subprocess.run(["bun", "--version"], check=True, capture_output=True)
        except Exception as e:
            log.error(f"❌ 自動安裝 Bun 失敗: {e}")
            log.error("請手動訪問 https://bun.sh 來安裝 Bun，然後重新執行此腳本。")
            raise

def ensure_uv_installed():
    """檢查 uv 是否已安裝，如果沒有，則自動安裝。"""
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
        log.info("✅ uv 已安裝。")
    except (subprocess.CalledProcessError, FileNotFoundError):
        log.warning("⚠️ uv 未安裝，正在嘗試自動安裝...")
        try:
            # 使用官方指令碼進行安裝
            install_command = "curl -LsSf https://astral.sh/uv/install.sh | sh"
            subprocess.run(install_command, shell=True, check=True, capture_output=True, text=True)

            # 安裝指令碼會將 uv 加入到 ~/.cargo/bin，我們將其手動加入到 PATH
            uv_path = str(Path.home() / ".cargo" / "bin")
            os.environ["PATH"] = f"{uv_path}{os.pathsep}{os.environ['PATH']}"

            log.info("✅ uv 已成功安裝。")
            # 再次驗證
            subprocess.run(["uv", "--version"], check=True, capture_output=True)
        except Exception as e:
            log.error(f"❌ 自動安裝 uv 失敗: {e}")
            log.error("請手動訪問 https://astral.sh/uv 來安裝 uv，然後重新執行此腳本。")
            raise

def run_app_flow():
    """執行完整的應用程式啟動流程"""
    log.info("====== 開始執行應用程式啟動流程 ======")
    db_proc = None
    api_proc = None
    processes_to_manage = []

    try:
        # --- 步驟 1: 確保 Bun 已安裝 ---
        ensure_bun_installed()

        # --- 步驟 2: 安裝後端依賴 ---
        log.info("[1/5] 安裝後端 Python 依賴...")
        ensure_uv_installed() # 確保 uv 已安裝
        server_requirements_path = API_GATEWAY_DIR / "requirements.txt"
        worker_requirements_path = ROOT_DIR / "requirements-worker.txt"
        try:
            log.info("正在使用 uv 安裝伺服器依賴...")
            subprocess.run(["uv", "pip", "install", "-r", str(server_requirements_path)], check=True)
            log.info("✅ 伺服器依賴安裝成功。")

            log.info("正在使用 uv 安裝工作程序依賴...")
            subprocess.run(["uv", "pip", "install", "-r", str(worker_requirements_path)], check=True)
            log.info("✅ 工作程序依賴安裝成功。")

        except subprocess.CalledProcessError as e:
            log.error(f"❌ 使用 uv 進行後端依賴安裝失敗: {e}")
            raise

        # --- 步驟 3: 清理環境 ---
        log.info("[2/5] 清理舊的資料庫與信號檔案...")
        # 清理 db_manager 的信號檔案，避免使用到舊的
        for signal_file in [DB_MANAGER_READY_FILE, DB_MANAGER_DIR / "db_manager.port"]:
             if signal_file.exists():
                signal_file.unlink()
                log.info(f"已刪除舊的信號檔案: {signal_file.name}")
        for db_file in ["queue.db", "logs.db"]:
            if (ROOT_DIR / db_file).exists():
                (ROOT_DIR / db_file).unlink()
                log.info(f"已刪除舊的資料庫檔案: {db_file}")

        # --- 步驟 4: 建置前端應用程式 ---
        log.info("[3/6] 準備建置前端 Vue 應用程式...")
        vue_app_dir = ROOT_DIR / "vue-app"
        dist_dir = vue_app_dir / "dist"

        log.info("正在清理舊的前端建置（若存在）...")
        if dist_dir.exists():
            try:
                shutil.rmtree(dist_dir)
                log.info(f"✅ 已成功刪除舊的 '{dist_dir}' 目錄。")
            except OSError as e:
                log.error(f"❌ 刪除舊的 dist 目錄失敗: {e}")
                raise

        try:
            log.info("開始全新前端建置流程...")
            log.info("正在安裝前端依賴 (bun install)...")
            # JULES'S NOTE: 使用 capture_output=True 來避免在主控台印出過多 bun 的日誌
            subprocess.run(["bun", "install"], cwd=vue_app_dir, check=True, capture_output=True, text=True, encoding='utf-8')
            log.info("✅ 前端依賴安裝成功。")
            log.info("正在建置前端應用 (bun run build)...")
            subprocess.run(["bun", "run", "build"], cwd=vue_app_dir, check=True, capture_output=True, text=True, encoding='utf-8')
            log.info("✅ 前端應用建置成功。")
        except Exception as e:
            log.error(f"❌ 前端建置過程中發生錯誤: {e}")
            # 如果 bun 的輸出包含有用資訊，將其印出
            if hasattr(e, 'stdout') and e.stdout: log.error(f"BUN STDOUT: {e.stdout}")
            if hasattr(e, 'stderr') and e.stderr: log.error(f"BUN STDERR: {e.stderr}")
            raise


        # --- 步驟 5: 依序啟動後端服務 ---
        log.info("[4/6] 啟動核心後端服務...")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)

        # 5.1: 啟動 DB Manager
        log.info("正在啟動 DB Manager 服務...")
        db_command = [sys.executable, str(DB_MANAGER_SCRIPT)]
        db_proc = subprocess.Popen(db_command, env=env, text=True, encoding='utf-8')
        processes_to_manage.append(db_proc)

        # 5.2: 等待 DB Manager 就緒
        log.info("等待 DB Manager 初始化...")
        wait_start_time = time.monotonic()
        while time.monotonic() - wait_start_time < 20: # 最多等待 20 秒
            if DB_MANAGER_READY_FILE.exists():
                log.info("✅ DB Manager 已就緒！")
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("DB Manager 未能在 20 秒內就緒，啟動失敗。")

        # 5.3: 啟動 API Gateway
        log.info("[5/6] 啟動 API Gateway...")
        port = find_free_port()

        # 將埠號設定到環境變數中，以便 Huey consumer 可以存取
        env["API_PORT"] = str(port)

        api_command = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)]
        api_proc = subprocess.Popen(api_command, cwd=API_GATEWAY_DIR, env=env, text=True, encoding='utf-8')
        processes_to_manage.append(api_proc)

        # 5.4: 等待 API Gateway 就緒
        log.info("等待 API Gateway 上線...")
        api_ready = False
        wait_start_time = time.monotonic()
        while time.monotonic() - wait_start_time < 30: # 最多等待 30 秒
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    log.info("✅ API Gateway 已上線！")
                    api_ready = True
                    break
            except (socket.timeout, ConnectionRefusedError):
                time.sleep(0.5)

        if not api_ready:
            raise RuntimeError("API Gateway 未能在 30 秒內上線，啟動失敗。")

        # 5.5: 啟動 Huey Consumer (背景工作處理器)
        log.info("[6/6] 啟動 Huey 背景工作消費者...")
        huey_command = [
            sys.executable,
            str(ROOT_DIR / "huey_consumer.py"),
            "huey_consumer.huey",
            "--workers", "4",          # 使用 4 個執行緒
            "--worker-type", "thread" # 使用執行緒模式
        ]
        log.info("正在將 Huey Consumer 的 stderr 重新導向到 stdout 以便於除錯...")
        huey_proc = subprocess.Popen(huey_command, env=env, text=True, encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        processes_to_manage.append(huey_proc)


        # For Colabpro to get the URL, we print it out.
        print(f"APP_URL: http://127.0.0.1:{port}", flush=True)

        log.info("✅ 所有服務似乎已成功啟動！")
        log.info("應用程式已進入持續運行模式。按 Ctrl+C 來關閉。")

        # 等待任一服務結束
        while all(p.poll() is None for p in processes_to_manage):
            time.sleep(1)
        log.warning("偵測到其中一個核心服務已終止，將關閉整個應用程式。")


    except KeyboardInterrupt:
        log.info("收到使用者中斷指令，正在關閉...")
    except Exception as e:
        log.error(f"❌ Python 流程控制器發生錯誤: {e}", exc_info=True)
    finally:
        log.info("正在終止所有背景服務...")
        for proc in reversed(processes_to_manage):
            if proc and proc.poll() is None:
                log.info(f"正在終止程序 (PID: {proc.pid})...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log.warning(f"程序 (PID: {proc.pid}) 終止超時，強制終止。")
                    proc.kill()
        log.info("✅ 所有服務已關閉。")

if __name__ == "__main__":
    run_app_flow()
