# -*- coding: utf-8 -*-
import subprocess
import sys
import time
import logging
import threading
import os
import urllib.request
from pathlib import Path
from multiprocessing import Process, Manager

# --- 外部依賴 ---
try:
    import uvicorn
    import fastapi
    from fastapi.responses import HTMLResponse
except ImportError:
    # 如果執行環境沒有，則自動安裝
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "fastapi", "uvicorn"])
    import uvicorn
    import fastapi
    from fastapi.responses import HTMLResponse

# --- 全域設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
from db.database import initialize_database

GLOBAL_TIMEOUT = 120 # 超時時間

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('LocalTestRunner')


# --- 狀態伺服器 ---
def status_server_process(shared_status, port):
    """一個獨立的進程，運行極簡的 FastAPI 狀態伺服器。"""
    app = fastapi.FastAPI()
    loading_html = """
    <!DOCTYPE html><html><head><title>服務啟動中...</title><meta charset="utf-8"><style>body{font-family:monospace;background:#121212;color:#E0E0E0;padding:2em}#status-message{font-size:1.2em}#sub-status{margin-top:1em;color:#A0A0A0}#spinner{border:4px solid #f3f3f3;border-top:4px solid #3498db;border-radius:50%;width:20px;height:20px;animation:spin 2s linear infinite;display:inline-block;vertical-align:middle;margin-right:10px}@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}</style></head><body><h1>🐺 善狼啟動器 - 正在準備服務...</h1><p><span id="spinner"></span><span id="status-message">初始化...</span></p><pre id="sub-status"></pre><script>const statusElement=document.getElementById('status-message');const subStatusElement=document.getElementById('sub-status');async function fetchStatus(){try{const response=await fetch('/api/status');const data=await response.json();statusElement.textContent=data.message;subStatusElement.textContent=data.details;if(data.status==='ready'){document.getElementById('spinner').style.display='none';statusElement.textContent='✅ 主服務已就緒！';subStatusElement.innerHTML=`E2E 測試正在背景執行...`}else if(data.status==='failed'){document.getElementById('spinner').style.display='none';statusElement.textContent='❌ 啟動失敗。請檢查主控台日誌。'}}catch(e){statusElement.textContent='無法連接到狀態伺服器，正在重試...'}}setInterval(fetchStatus,2000);fetchStatus();</script></body></html>
    """
    @app.get("/", response_class=HTMLResponse)
    def read_root(): return loading_html
    @app.get("/api/status")
    def get_status(): return shared_status.copy()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# --- 主測試執行器 ---
class LocalTestRunner:
    def __init__(self):
        self.manager = Manager()
        self.shared_status = self.manager.dict({
            "status": "initializing", "message": "測試執行器初始化...", "details": ""
        })
        self.processes = []
        self.exit_code = 0
        self.main_server_url = None

    def _update_status(self, status, message, details=""):
        log.info(f"STATUS: [{status}] {message}")
        self.shared_status.update({"status": status, "message": message, "details": details})

    def _run_e2e_tests(self):
        """執行 Playwright E2E 測試。"""
        if self.main_server_url is None:
            log.error("主伺服器 URL 未設定，無法執行 E2E 測試。")
            return False

        self._update_status("running_e2e_tests", "主服務已就緒，正在執行 E2E 測試...")
        try:
            env = os.environ.copy()
            env["API_URL"] = self.main_server_url
            # JULES: 增加 -sv 參數以獲取詳細的即時輸出，並移除 capture_output=True
            pytest_cmd = [sys.executable, "-m", "pytest", "-sv", str(ROOT_DIR / "e2e_tests")]
            # JULES: 增加超時時間到 180 秒，以防測試僅僅是運行緩慢
            log.info(f"執行測試指令: {' '.join(pytest_cmd)}")
            result = subprocess.run(pytest_cmd, text=True, encoding='utf-8', env=env, timeout=180)

            if result.returncode != 0:
                log.error(f"❌ E2E 測試失敗! 返回碼: {result.returncode}")
                log.error("--- Pytest stdout ---\n" + result.stdout)
                log.error("--- Pytest stderr ---\n" + result.stderr)
                self.exit_code = 1
                return False
            else:
                log.info("✅ 所有 E2E 測試通過！")
                return True
        except Exception as e:
            log.error(f"❌ 執行 E2E 測試時發生錯誤: {e}", exc_info=True)
            self.exit_code = 1
            return False

    def _background_worker(self):
        """在背景執行所有耗時的安裝和啟動任務。"""
        try:
            # 1. 安裝依賴 (uv)
            self._update_status("installing_deps", "安裝 Python 依賴 (uv)...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True, capture_output=True)
            req_file = ROOT_DIR / "requirements-server.txt"
            subprocess.run([sys.executable, "-m", "uv", "pip", "install", "-q", "-r", str(req_file)], check=True, capture_output=True, text=True)

            # 2. 建置前端
            self._update_status("building_frontend", "安裝/建置前端 (bun)...")
            vue_app_dir = ROOT_DIR / "vue-app"
            subprocess.run(["bun", "install"], cwd=vue_app_dir, check=True, capture_output=True, text=True)
            subprocess.run(["bun", "run", "build"], cwd=vue_app_dir, check=True, capture_output=True, text=True)

            # 3. 初始化資料庫
            self._update_status("initializing_db", "初始化資料庫...")
            initialize_database()

            # 4. 啟動主服務
            self._update_status("starting_main_server", "啟動主應用程式伺服器...")
            main_server_port = self._find_free_port()
            self.main_server_url = f"http://127.0.0.1:{main_server_port}"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")
            env["API_MODE"] = "mock"
            db_manager_cmd = [sys.executable, str(ROOT_DIR / "src" / "db" / "manager.py")]
            db_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
            self.processes.append(("db_manager", db_proc))
            time.sleep(2)
            api_server_cmd = [sys.executable, str(ROOT_DIR / "src" / "api" / "api_server.py"), "--port", str(main_server_port)]
            api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, preexec_fn=os.setsid)
            self.processes.append(("api_server", api_proc))

            # 5. 健康檢查
            self._update_status("health_checking", f"等待主伺服器就緒...")
            if not self._run_health_check(self.main_server_url, is_main_server=True):
                raise RuntimeError("主伺服器健康檢查失敗。")

            self._update_status("ready", "主服務已就緒！")
            log.info(f"✅✅✅ 主應用程式已在 {self.main_server_url} 就緒！✅✅✅")

        except Exception as e:
            log.error(f"❌ 背景工作執行緒發生錯誤: {e}", exc_info=True)
            self._update_status("failed", f"背景任務執行失敗: {e}")

    def _run_health_check(self, url, is_main_server=False):
        start_time = time.time()
        endpoint = f"{url}/api/health" if is_main_server else url
        while time.time() - start_time < 45:
            try:
                with urllib.request.urlopen(endpoint, timeout=2) as response:
                    if response.status == 200: return True
            except Exception: pass
            time.sleep(1)
        return False

    def _find_free_port(self) -> int:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0)); return s.getsockname()[1]

    def _shutdown(self):
        log.info("🛑 正在關閉所有服務...")
        for name, proc in reversed(self.processes):
            is_alive = proc.is_alive() if isinstance(proc, Process) else proc.poll() is None
            if is_alive:
                try:
                    pid = proc.pid
                    if isinstance(proc, Process):
                        proc.terminate(); proc.join(timeout=5)
                    else: # Popen
                        os.killpg(os.getpgid(pid), subprocess.signal.SIGTERM); proc.wait(timeout=5)
                except Exception:
                    if isinstance(proc, Process): proc.kill()
                    else:
                        try: os.killpg(os.getpgid(pid), subprocess.signal.SIGKILL)
                        except Exception: pass
        log.info("👋 所有服務已關閉。")

    def run(self):
        overall_start_time = time.monotonic()
        try:
            # 1. 立即啟動狀態伺服器
            status_port = self._find_free_port()
            status_url = f"http://127.0.0.1:{status_port}"
            status_server_proc = Process(target=status_server_process, args=(self.shared_status, status_port), daemon=True)
            status_server_proc.start()
            self.processes.append(("status_server", status_server_proc))
            time.sleep(3)
            if not self._run_health_check(f"{status_url}/api/status"):
                 raise RuntimeError("狀態伺服器啟動失敗！")

            log.info(f"🎉 狀態伺服器已在 {status_url} 上線 (耗時: {time.monotonic() - overall_start_time:.2f} 秒)")

            # 2. 在背景執行主服務啟動流程
            worker_thread = threading.Thread(target=self._background_worker, daemon=True)
            worker_thread.start()

            # 3. 等待主服務就緒
            start_wait_time = time.monotonic()
            while self.shared_status.get('status') not in ['ready', 'failed']:
                if time.monotonic() - start_wait_time > GLOBAL_TIMEOUT:
                    raise TimeoutError("等待背景任務就緒超時！")
                time.sleep(1)

            if self.shared_status.get('status') == 'failed':
                 raise RuntimeError(f"背景任務失敗: {self.shared_status.get('details')}")

            # 4. 主服務就緒後，執行 E2E 測試
            if not self._run_e2e_tests():
                self.exit_code = 1

        except Exception as e:
            log.error(f"主執行緒發生錯誤: {e}", exc_info=True)
            self.exit_code = 1
        finally:
            self._shutdown()
            log.info(f"測試流程結束，退出碼: {self.exit_code}")
            sys.exit(self.exit_code)

if __name__ == "__main__":
    runner = LocalTestRunner()
    runner.run()
