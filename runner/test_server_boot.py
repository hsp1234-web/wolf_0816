# runner/test_server_boot.py
import subprocess
import sys
import time
import logging
import os
import urllib.request
import shutil
import socket
from pathlib import Path

# --- 全域設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
from db.database import initialize_database

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('ServerBootTest')

def clear_pycache():
    """遞迴地尋找並移除專案中所有的 __pycache__ 目錄。"""
    log.info("🧹 開始清理 Python 位元組碼快取 (__pycache__)...")
    count = 0
    for path in ROOT_DIR.rglob('__pycache__'):
        if path.is_dir():
            log.info(f"  - 正在移除: {path}")
            shutil.rmtree(path)
            count += 1
    if count > 0:
        log.info(f"✅ 成功移除了 {count} 個 __pycache__ 目錄。")
    else:
        log.info("✅ 未找到任何 __pycache__ 目錄，無需清理。")

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def run_health_check(url, timeout=30) -> bool:
    log.info(f"🩺 執行健康檢查 (目標: {url})...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    log.info("✅ 健康檢查成功。")
                    return True
        except Exception as e:
            log.debug(f"健康檢查重試... ({e})")
        time.sleep(1)
    log.error("❌ 健康檢查超時。")
    return False

def main():
    processes = []
    exit_code = 0
    try:
        # 1. 清理快取
        clear_pycache()

        # 1.5. 安裝依賴
        log.info("📦 安裝伺服器依賴...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True, capture_output=True)
            req_file = ROOT_DIR / "requirements-server.txt"
            subprocess.run([sys.executable, "-m", "uv", "pip", "install", "-q", "-r", str(req_file)], check=True, capture_output=True, text=True)
            log.info("✅ 依賴安裝完成。")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            stderr = e.stderr or ""
            log.error(f"❌ 依賴安裝失敗:\n{stderr}")
            raise RuntimeError("依賴安裝失敗") from e

        # 1.7. 建置前端
        log.info("🏗️  建置前端應用...")
        try:
            vue_app_dir = ROOT_DIR / "vue-app"
            log.info(f"  - 在 {vue_app_dir} 中執行 `bun install`...")
            subprocess.run(["bun", "install"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
            log.info(f"  - 在 {vue_app_dir} 中執行 `bun run build`...")
            subprocess.run(["bun", "run", "build"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
            log.info("✅ 前端建置完成。")
        except FileNotFoundError:
            log.error("❌ 'bun' command not found. 請確保 Bun 已安裝並在您的 PATH 中。")
            raise RuntimeError("'bun' command not found.")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            stderr = e.stderr or ""
            log.error(f"❌ 前端建置失敗:\n{stderr}")
            raise RuntimeError("前端建置失敗") from e

        # 2. 初始化資料庫
        log.info("🛠️ 初始化資料庫...")
        initialize_database()
        log.info("✅ 資料庫初始化完成。")

        # 3. 啟動 DB Manager
        log.info("🚀 啟動 DB Manager...")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")
        db_manager_cmd = [sys.executable, str(ROOT_DIR / "src" / "db" / "manager.py")]
        db_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid, env=env)
        processes.append(("db_manager", db_proc))
        log.info("  - DB Manager 已啟動，等待 2 秒使其穩定...")
        time.sleep(2)

        # 4. 啟動 API Server
        log.info("🚀 啟動 API Server...")
        api_port = find_free_port()
        api_url = f"http://127.0.0.1:{api_port}"
        api_server_cmd = [sys.executable, str(ROOT_DIR / "src" / "api" / "api_server.py"), "--port", str(api_port), "--mock"]
        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=env)
        processes.append(("api_server", api_proc))
        log.info(f"  - API Server 正在埠號 {api_port} 上啟動...")

        # 5. 執行健康檢查
        health_check_url = f"{api_url}/api/health"
        if run_health_check(health_check_url):
            log.info("🎉✅✅✅ 伺服器成功啟動並通過健康檢查！✅✅✅🎉")
            exit_code = 0
        else:
            log.error("❌❌❌ 伺服器啟動失敗！❌❌❌")
            # 印出 API Server 的日誌以供偵錯
            log.error("--- API Server 輸出 ---")
            api_proc.terminate() # 確保子程序終止
            for line in api_proc.stdout:
                log.error(line.strip())
            log.error("-----------------------")
            exit_code = 1

    except Exception as e:
        log.error(f"偵錯腳本執行期間發生未預期的錯誤: {e}", exc_info=True)
        exit_code = 1
    finally:
        log.info("🛑 正在關閉所有服務...")
        for name, proc in reversed(processes):
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGTERM)
                    proc.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGKILL)
        log.info("👋 偵錯腳本執行完畢。")
        sys.exit(exit_code)

if __name__ == "__main__":
    main()
