import subprocess
import sys
import time
import logging
import threading
import queue
import socket
import os
import urllib.request
from pathlib import Path

# --- 全域設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
from db.database import initialize_database

GLOBAL_TIMEOUT = 100

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('LocalTestRunner')

class TestRunner:
    """
    負責在本地模擬環境中啟動伺服器、執行 E2E 測試，並確保在超時內完成。
    """
    def __init__(self):
        self.processes = []
        self.api_port = None
        self.api_url = None
        self.log_queue = queue.Queue()
        self.exit_code = 0

    def _install_dependencies(self):
        """安裝測試所需的依賴。"""
        log.info("📋 步驟 1/6: 安裝測試依賴...")
        try:
            log.info("  - 安裝 Playwright 瀏覽器 (chromium)...")
            subprocess.run(["npx", "playwright", "install", "chromium"], check=True, capture_output=True, timeout=120)

            req_file = ROOT_DIR / "requirements-server.txt"
            log.info(f"  - 從 {req_file} 安裝 Python 套件...")
            command = [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)]
            subprocess.run(command, check=True, capture_output=True, text=True)

            log.info("✅ 依賴安裝完成。")
            return True
        except subprocess.CalledProcessError as e:
            log.error(f"❌ 依賴安裝失敗:\n{e.stderr}")
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            log.error(f"❌ 依賴安裝失敗: {e}")
            return False

    def _build_frontend(self):
        """根據 AGENTS.md 的要求，建置 Vue.js 前端應用程式。"""
        log.info("🏗️ 步驟 2/6: 建置 Vue.js 前端應用程式...")
        vue_app_dir = ROOT_DIR / "vue-app"
        if not vue_app_dir.is_dir():
            log.warning(f"Vue 應用程式目錄不存在於 {vue_app_dir}，跳過建置。")
            return True
        try:
            log.info(f"  - 在 {vue_app_dir} 中執行 `bun install`...")
            subprocess.run(["bun", "install"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
            log.info(f"  - 在 {vue_app_dir} 中執行 `bun run build`...")
            subprocess.run(["bun", "run", "build"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
            log.info("✅ Vue.js 前端應用程式建置完成。")
            return True
        except FileNotFoundError:
            log.error("❌ 'bun' command not found. Please ensure Bun is installed and in your PATH.")
            return False
        except subprocess.CalledProcessError as e:
            log.error(f"❌ 前端建置失敗。返回碼: {e.returncode}\n--- STDOUT ---\n{e.stdout}\n--- STDERR ---\n{e.stderr}")
            return False
        except subprocess.TimeoutExpired as e:
            log.error(f"❌ 前端建置超時: {e}")
            return False

    def _initialize_db(self):
        log.info("🛠️ 步驟 3/6: 初始化資料庫...")
        try:
            initialize_database()
            log.info("✅ 資料庫初始化成功。")
            return True
        except Exception as e:
            log.error(f"❌ 資料庫初始化失敗: {e}", exc_info=True)
            return False

    def _enqueue_output(self, stream, process_name):
        for line in iter(stream.readline, ''):
            self.log_queue.put((process_name, line.strip()))
        stream.close()

    def _start_services(self):
        """啟動 DB 管理器和 API 伺服器。"""
        log.info("🚀 步驟 4/6: 啟動後端服務 (強制模擬模式)...")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")
        env["API_MODE"] = "mock"

        # --- 啟動 DB Manager ---
        db_manager_cmd = [sys.executable, str(ROOT_DIR / "src" / "db" / "manager.py")]
        db_proc = subprocess.Popen(
            db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', preexec_fn=os.setsid, env=env
        )
        self.processes.append(("db_manager", db_proc))
        log.info(f"  - DB Manager (PID: {db_proc.pid}) 啟動中...")
        time.sleep(2) # 等待 DB Manager 建立 port 檔案

        # --- 啟動 API Server ---
        self.api_port = self._find_free_port()
        self.api_url = f"http://127.0.0.1:{self.api_port}"
        log.info(f"  - 為 API 伺服器指派埠號: {self.api_port}")

        api_server_cmd = [
            sys.executable, str(ROOT_DIR / "src" / "api" / "api_server.py"),
            "--port", str(self.api_port)
        ]

        api_proc = subprocess.Popen(
            api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', preexec_fn=os.setsid, env=env
        )
        self.processes.append(("api_server", api_proc))
        log.info(f"  - API Server (PID: {api_proc.pid}) 啟動中...")

        for name, proc in self.processes:
            thread = threading.Thread(target=self._enqueue_output, args=(proc.stdout, name), daemon=True)
            thread.start()
        return True

    def _run_health_check(self) -> bool:
        log.info(f"🩺 步驟 5/6: 執行後端健康檢查 (目標: {self.api_url}/api/health)...")
        start_time = time.time()
        health_check_timeout = 30

        while time.time() - start_time < health_check_timeout:
            self._print_logs()
            try:
                with urllib.request.urlopen(f"{self.api_url}/api/health", timeout=2) as response:
                    if response.status == 200:
                        log.info("✅ 後端健康檢查成功。")
                        return True
            except Exception:
                pass

            for name, proc in self.processes:
                if proc.poll() is not None:
                    log.error(f"❌ 健康檢查期間，服務 '{name}' 意外終止。")
                    return False
            time.sleep(1)

        log.error("❌ 後端健康檢查超時。")
        return False

    def _run_tests(self):
        log.info("🧪 步驟 6/6: 執行 Playwright E2E 測試...")
        env = os.environ.copy()
        env["API_URL"] = self.api_url

        test_dir = ROOT_DIR / "e2e_tests"
        pytest_cmd = [sys.executable, "-m", "pytest", str(test_dir)]

        try:
            result = subprocess.run(
                pytest_cmd, capture_output=True, text=True, encoding='utf-8', env=env, timeout=60
            )
            print("--- Pytest stdout ---")
            print(result.stdout)
            print("--- Pytest stderr ---")
            print(result.stderr)

            if result.returncode == 0:
                log.info("✅ 所有 E2E 測試通過！")
                self.exit_code = 0
            else:
                log.error(f"❌ E2E 測試失敗，返回碼: {result.returncode}")
                self.exit_code = 1

        except subprocess.TimeoutExpired:
            log.error("❌ Pytest 執行超時！")
            self.exit_code = 1
        except Exception as e:
            log.error(f"❌ 執行測試時發生嚴重錯誤: {e}", exc_info=True)
            self.exit_code = 1

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def _shutdown(self):
        log.info("🛑 正在關閉所有服務...")
        for name, proc in reversed(self.processes):
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGTERM)
                    proc.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired, AttributeError):
                    try:
                        os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGKILL)
                    except Exception:
                        pass
        log.info("👋 所有服務已關閉。")

    def _print_logs(self):
        while not self.log_queue.empty():
            name, line = self.log_queue.get_nowait()
            print(f"[{name}] {line}")

    def run(self):
        start_time = time.time()
        try:
            if not self._install_dependencies(): self.exit_code = 1; return
            if not self._build_frontend(): self.exit_code = 1; return
            if not self._initialize_db(): self.exit_code = 1; return
            if not self._start_services(): self.exit_code = 1; return
            if not self._run_health_check(): self.exit_code = 1; return
            self._run_tests()
        except Exception as e:
            log.error(f"\n🛑 執行期間發生錯誤: {e}", exc_info=True)
            self.exit_code = 1
        finally:
            self._print_logs()
            self._shutdown()
            if time.time() - start_time > GLOBAL_TIMEOUT:
                log.error(f"🔥🔥🔥 全局超時！已達到 {GLOBAL_TIMEOUT} 秒的執行時間上限。")
                self.exit_code = 1
            log.info(f"測試流程結束，退出碼: {self.exit_code}")
            sys.exit(self.exit_code)

if __name__ == "__main__":
    if not (ROOT_DIR / "runner").exists():
        log.error(f"請在專案根目錄下執行此腳本，當前目錄: {Path.cwd()}")
        sys.exit(1)
    runner = TestRunner()
    runner.run()
