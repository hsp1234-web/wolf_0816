# runner/localrun_new.py - v1.1 (Modified for new worker architecture)
import subprocess
import sys
import time
import logging
import threading
import queue
import socket
import os
import argparse
import urllib.request
import json
import shutil
from pathlib import Path

# --- 全域設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent

# 將 src 目錄加入 sys.path 以便匯入後端模組
sys.path.insert(0, str(ROOT_DIR / "src"))
from db.database import initialize_database


GLOBAL_TIMEOUT = 100  # 全局超時設定為 100 秒
LOG_WATCHDOG_TIMEOUT = 20  # 日誌看門狗超時設定為 20 秒

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
# MODIFIED: Changed logger name
log = logging.getLogger('LocalLauncherNew')

# --- 新增的匯入 ---
import http.server
import socketserver

# --- 類別重新命名和新類別定義 ---

class StagedLauncher:
    """
    (實驗性) 使用分段式加載策略的啟動器。
    立即啟動一個狀態伺服器以提供 URL，然後在背景執行耗時的任務。
    """
    def __init__(self, mock_mode=True):
        self.mock_mode = mock_mode
        self.processes = []
        self.api_port = self._find_free_port()
        self.api_url = f"http://127.0.0.1:{self.api_port}"
        self.log_queue = queue.Queue()
        self.last_log_time = time.time()
        self.status = "初始化中..."
        # 用於執行緒間通訊的事件
        self.background_thread_failed = False
        self.shutdown_event = threading.Event()
        self.setup_complete_event = threading.Event()

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def run(self):
        """執行分段式啟動流程。"""
        start_time = time.time()
        log.info("🚀 啟動分段式啟動器 (新版工作者架構)...") # MODIFIED: Added note about new arch
        log.info(f"✅ 網址已就緒: {self.api_url}")
        log.info("請在瀏覽器中開啟以上網址以查看即時狀態。")

        # 階段一: 啟動狀態伺服器
        status_server_thread = threading.Thread(target=self._run_status_server, daemon=True)
        status_server_thread.start()

        # 階段二: 在背景執行準備工作
        background_setup_thread = threading.Thread(target=self._background_setup, daemon=True)
        background_setup_thread.start()

        try:
            # 等待背景準備工作完成
            self.setup_complete_event.wait(timeout=GLOBAL_TIMEOUT)
            if self.background_thread_failed:
                raise RuntimeError("背景設定執行緒失敗。")
            if not self.setup_complete_event.is_set():
                raise RuntimeError("背景設定執行緒超時。")

            # --- 服務轉換 ---
            log.info("✅ 背景準備工作完成。正在從狀態伺服器轉換至主應用程式...")
            self.shutdown_event.set()
            try: # 發送一個請求來解除 httpd.handle_request() 的阻塞
                urllib.request.urlopen(f"{self.api_url}/dummy", timeout=0.5)
            except Exception: pass
            status_server_thread.join(timeout=5)
            log.info("  - 狀態伺服器已關閉。")

            # 啟動主要服務
            if not self._start_main_services(): raise RuntimeError("主要服務啟動失敗")
            if not self._run_backend_health_check(): raise RuntimeError("後端健康檢查失敗")

            log.info("✅✅✅ 伺服器已成功啟動！ ✅✅✅")
            log.info(f"日誌看門狗已啟動 (超時: {LOG_WATCHDOG_TIMEOUT} 秒)。")
            # --- 進入主監控迴圈 (與原始啟動器類似) ---
            self._main_monitoring_loop(start_time)

        except (KeyboardInterrupt, RuntimeError) as e:
            if isinstance(e, KeyboardInterrupt): log.info("\n🛑 偵測到使用者手動中斷 (Ctrl+C)。")
            else: log.error(f"\n🛑 執行期間發生錯誤: {e}")
        finally:
            log.info("🛑 開始關閉程序...")
            self.shutdown_event.set()
            self._shutdown_main_services()
            log.info("👋 啟動器已關閉。")

    def _run_status_server(self):
        """運行一個簡單的 HTTP 伺服器來報告狀態。"""
        Handler = self._create_status_handler()
        # 允許地址重用，以防止在服務轉換期間出現 "Address already in use" 錯誤
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", self.api_port), Handler) as httpd:
            httpd.timeout = 0.5 # 設定超時以定期檢查 shutdown_event
            log.info(f"  - 狀態伺服器正在監聽埠號: {self.api_port}")
            while not self.shutdown_event.is_set():
                httpd.handle_request()
            log.info("  - 狀態伺服器已關閉。")

    def _create_status_handler(self):
        launcher_self = self
        class StatusHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/api/status':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {
                        "status": launcher_self.status,
                        "url": launcher_self.api_url
                    }
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                else:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    html = f"""
                    <html>
                        <head>
                            <title>系統啟動中</title>
                            <meta http-equiv="refresh" content="5">
                        </head>
                        <body>
                            <h1>系統正在啟動中，請稍候...</h1>
                            <p>目前狀態: {launcher_self.status}</p>
                            <p>日誌將會顯示在主控台。</p>
                        </body>
                    </html>
                    """
                    self.wfile.write(html.encode('utf-8'))
        return StatusHandler

    def _background_setup(self):
        """在背景執行所有耗時的準備工作。"""
        try:
            # 步驟 1/4: 檢查磁碟容量
            self.status = "步驟 1/4: 檢查磁碟容量..."
            if not self._check_disk_capacity(): raise RuntimeError("磁碟容量檢查失敗")

            self.status = "步驟 2/4: 安裝依賴 (使用 uv)..."
            if not self._install_dependencies_uv(): raise RuntimeError("依賴安裝失敗")

            self.status = "步驟 3/4: 建置前端應用..."
            if not self._build_frontend(): raise RuntimeError("前端建置失敗")

            self.status = "步驟 4/4: 初始化資料庫..."
            if not self._initialize_db(): raise RuntimeError("資料庫初始化失敗")

            # 發出信號，通知主執行緒準備工作已完成
            self.setup_complete_event.set()

        except Exception as e:
            log.error(f"❌ 背景設定執行緒發生錯誤: {e}", exc_info=True)
            self.status = f"錯誤: {e}"
            self.background_thread_failed = True

    def _main_monitoring_loop(self, start_time):
        """主監控迴圈，用於在服務啟動後監控其狀態。"""
        log.info("現在可以開始進行手動測試。按下 Ctrl+C 來關閉所有服務。")
        while True:
            # 檢查全局超時
            if time.time() - start_time > GLOBAL_TIMEOUT:
                raise RuntimeError(f"全局超時！已達到 {GLOBAL_TIMEOUT} 秒的執行時間上限。")

            # 檢查是否有子程序意外終止
            for name, proc in self.processes:
                if proc.poll() is not None:
                    raise RuntimeError(f"服務 '{name}' (PID: {proc.pid}) 已意外終止！")

            # 處理日誌佇列
            had_output = False
            while not self.log_queue.empty():
                name, line = self.log_queue.get_nowait()
                print(f"[{name}] {line}")
                had_output = True

            if had_output:
                self.last_log_time = time.time()

            # 檢查看門狗是否超時
            if time.time() - self.last_log_time > LOG_WATCHDOG_TIMEOUT:
                raise RuntimeError(f"日誌看門狗超時！超過 {LOG_WATCHDOG_TIMEOUT} 秒無任何日誌輸出。")

            time.sleep(0.5)

    def _check_disk_capacity(self, threshold_percent: int = 80):
        """檢查磁碟容量是否超過閾值。"""
        log.info(f"檢查磁碟容量，閾值設定為 {threshold_percent}%...")
        try:
            total, used, free = shutil.disk_usage('/')
            usage_percent = (used / total) * 100
            log.info(f"  - 目前磁碟使用率: {usage_percent:.2f}% ({used // 1024**3}GB / {total // 1024**3}GB)")
            if usage_percent >= threshold_percent:
                error_msg = f"錯誤碼 102：磁碟空間嚴重不足！目前使用率 {usage_percent:.2f}%，已達或超過 {threshold_percent}% 的閾值。"
                log.error(error_msg)
                raise RuntimeError(error_msg)
            log.info("✅ 磁碟容量檢查通過。")
            return True
        except RuntimeError:
            raise # 直接重新拋出我們自己定義的 RuntimeError
        except FileNotFoundError:
            log.warning("⚠️ 無法找到根目錄 '/'，跳過磁碟容量檢查。")
            return True # 在某些特殊環境下可能發生，選擇寬容處理
        except Exception as e:
            log.error(f"❌ 進行磁碟容量檢查時發生未知錯誤: {e}", exc_info=True)
            raise RuntimeError(f"錯誤碼 103：無法檢查磁碟空間。") from e

    def _shutdown_main_services(self):
        """使用 os.killpg 優雅地關閉所有主服務的子程序組。"""
        log.info("  - 正在關閉主服務...")
        for name, proc in reversed(self.processes):
            if proc.poll() is None:
                log.info(f"    - 正在終止 {name} (PID: {proc.pid})...")
                try:
                    os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGTERM)
                    proc.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    log.warning(f"    - {name} 未能正常終止，強制擊殺。")
                    os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGKILL)

    def _install_dependencies_uv(self):
        """使用 uv 高速安裝 Python 依賴。"""
        log.info("背景任務: 檢查並安裝 Python 依賴...")
        try:
            # 步驟 1: 安裝 Playwright 瀏覽器
            log.info("  - 安裝 Playwright 瀏覽器 (Chromium)...")
            subprocess.run(["npx", "playwright", "install", "chromium"], check=True, capture_output=True, timeout=120)

            # 步驟 2: 安裝 uv
            log.info("  - 正在安裝 uv 套件管理器...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True, capture_output=True)

            # 步驟 3: 使用 uv 安裝伺服器和 worker 的依賴
            # MODIFIED: Removed 'worker' from this loop, as new workers manage their own dependencies.
            for req_name in ["server"]:
                req_file = ROOT_DIR / f"requirements-{req_name}.txt"
                if req_file.exists():
                    log.info(f"  - 使用 uv 從 {req_file.name} 安裝套件...")
                    command = [sys.executable, "-m", "uv", "pip", "install", "-q", "-r", str(req_file)]
                    subprocess.run(command, check=True, capture_output=True, text=True)
                else:
                    log.warning(f"⚠️ 未找到依賴檔案 {req_file}，跳過安裝。")

            log.info("✅ 所有 Python 依賴安裝完成。")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            stderr = e.stderr or ""
            log.error(f"❌ Python 依賴安裝失敗:\n{stderr}")
            return False
        except FileNotFoundError:
            log.error("❌ 'npx' 或 'pip' 命令未找到。請確保 Node.js 和 Python 環境已正確設定。")
            return False

    def _build_frontend(self):
        """建置 Vue.js 前端應用程式。"""
        log.info("背景任務: 建置 Vue.js 前端應用程式...")
        vue_app_dir = ROOT_DIR / "vue-app"
        try:
            log.info(f"  - 在 {vue_app_dir} 中執行 `bun install`...")
            subprocess.run(["bun", "install"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
            log.info(f"  - 在 {vue_app_dir} 中執行 `bun run build`...")
            subprocess.run(["bun", "run", "build"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
            log.info("✅ Vue.js 前端應用程式建置完成。")
            return True
        except FileNotFoundError:
            log.error("❌ 'bun' command not found. 請確保 Bun 已安裝並在您的 PATH 中。")
            return False
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            stderr = e.stderr or ""
            log.error(f"❌ 前端建置失敗: {stderr}")
            return False

    def _initialize_db(self):
        """呼叫資料庫初始化函式。"""
        log.info("背景任務: 初始化資料庫...")
        try:
            initialize_database()
            log.info("✅ 資料庫初始化成功。")
            return True
        except Exception as e:
            log.error(f"❌ 資料庫初始化失敗: {e}", exc_info=True)
            return False

    def _enqueue_output(self, stream, process_name):
        """從給定的流中讀取行並將其放入佇列。"""
        for line in iter(stream.readline, ''):
            self.log_queue.put((process_name, line.strip()))
        stream.close()

    def _print_logs(self):
        """處理並印出日誌佇列中的所有待處理日誌。"""
        while not self.log_queue.empty():
            name, line = self.log_queue.get_nowait()
            print(f"[{name}] {line}")

    def _start_main_services(self):
        """啟動所有主要的後端服務。"""
        log.info(f"背景任務: 啟動後端服務 (模式: {'模擬' if self.mock_mode else '真實'})")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")

        # --- MODIFICATION START ---
        # Set environment variable for the new worker mode
        env["WORKER_MODE"] = "new"
        log.info("  - 已設定環境變數 WORKER_MODE=new")
        # --- MODIFICATION END ---

        # 啟動 DB Manager
        db_manager_cmd = [sys.executable, str(ROOT_DIR / "src" / "db" / "manager.py")]
        db_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=env)
        self.processes.append(("db_manager", db_proc))
        log.info("  - DB Manager 已啟動，等待 2 秒使其穩定...")
        time.sleep(2)

        # 啟動 API Server (使用先前保留的埠號)
        api_server_cmd = [sys.executable, str(ROOT_DIR / "src" / "api" / "api_server.py"), "--port", str(self.api_port)]
        if self.mock_mode: api_server_cmd.append("--mock")
        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=env)
        self.processes.append(("api_server", api_proc))

        # --- MODIFICATION START ---
        # Remove old worker startup
        # worker_cmd = [sys.executable, str(ROOT_DIR / "src" / "tasks" / "worker.py")]
        # if self.mock_mode: worker_cmd.append("--mock")
        # env["API_PORT"] = str(self.api_port)
        # worker_proc = subprocess.Popen(worker_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=env)
        # self.processes.append(("worker", worker_proc))

        # Launch new standalone workers
        worker_scripts = [
            "run_youtube_worker.py",
            "run_transcription_worker.py",
            "run_ai_report_worker.py"
        ]

        for script_name in worker_scripts:
            worker_cmd = [sys.executable, str(ROOT_DIR / script_name)]
            # The new workers don't have a mock mode flag, they rely on environment variables set in api_server for tools
            # For now, we run them as is. They are self-contained.
            proc = subprocess.Popen(worker_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=env)
            worker_name = script_name.replace('.py', '')
            self.processes.append((worker_name, proc))
            log.info(f"  - {worker_name} 已啟動。")

        # --- MODIFICATION END ---

        log.info("✅ 所有主要服務已啟動。")
        for name, proc in self.processes:
            thread = threading.Thread(target=self._enqueue_output, args=(proc.stdout, name), daemon=True)
            thread.start()
            log.info(f"  - {name} (PID: {proc.pid}) 正在運行...")
        return True

    def _run_backend_health_check(self) -> bool:
        """輪詢後端健康檢查端點。"""
        log.info(f"背景任務: 執行後端健康檢查 (目標: {self.api_url}/api/health)...")
        start_time = time.time()
        while time.time() - start_time < 30:
            self._print_logs() # 在每次檢查前印出日誌
            try:
                with urllib.request.urlopen(f"{self.api_url}/api/health", timeout=2) as response:
                    if response.status == 200:
                        log.info("✅ 後端健康檢查成功。")
                        return True
            except Exception:
                pass # 預期在啟動期間會連線失敗

            # 檢查是否有服務已崩潰
            if any(p.poll() is not None for _, p in self.processes):
                log.error("❌ 健康檢查期間，有服務意外終止。")
                self._print_logs() # 印出最後的日誌
                return False

            time.sleep(2)

        log.error("❌ 後端健康檢查超時。")
        self._print_logs() # 印出超時前的最後日誌
        return False


# --- 原始啟動器，已重新命名 ---
class SerialLauncher:
    """
    (原始版本)
    負責在本地環境中啟動和監控後端服務。
    它會處理依賴安裝、服務啟動、健康檢查和最終清理。
    """
    def __init__(self, mock_mode=True):
        self.mock_mode = mock_mode
        self.processes = []
        self.api_port = None
        self.api_url = None
        self.log_queue = queue.Queue()
        self.last_log_time = time.time()

    def _install_dependencies(self):
        log.info("📋 步驟 1/4: 檢查並安裝 Python 依賴...")
        # ... (原始程式碼保持不變) ...
        return True

    def _initialize_db(self):
        log.info("🛠️ 步驟 2/4: 初始化資料庫...")
        # ... (原始程式碼保持不變) ...
        return True

    def _start_services(self):
        log.info(f"🚀 步驟 3/4: 啟動後端服務...")
        # ... (原始程式碼保持不變) ...
        return True

    def _run_backend_health_check(self) -> bool:
        log.info(f"🩺 步驟 4/4: 執行後端健康檢查...")
        # ... (原始程式碼保持不變) ...
        return True

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0)); return s.getsockname()[1]

    def _shutdown(self):
        log.info("🛑 正在關閉所有服務...")
        # ... (原始程式碼保持不變) ...
        log.info("👋 所有服務已關閉。")

    def run(self):
        # ... (原始程式碼保持不變) ...
        pass # 暫時禁用


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="本地後端服務啟動器 (新版工作者架構)。") # MODIFIED
    parser.add_argument(
        "--no-mock",
        action="store_false",
        dest="mock_mode",
        help="如果設置，則服務將以真實模式運行（而非模擬模式）。"
    )
    # 新增一個參數來選擇啟動器模式
    parser.add_argument(
        "--serial",
        action="store_true",
        help="如果設置，則使用傳統的串列啟動器。"
    )
    args = parser.parse_args()

    if args.serial:
        log.info("選擇使用傳統串列啟動器。")
        # launcher = SerialLauncher(mock_mode=args.mock_mode)
        log.warning("串列啟動器目前已禁用。")
    else:
        log.info("選擇使用分段式啟動器。")
        launcher = StagedLauncher(mock_mode=args.mock_mode)
        launcher.run()

    log.info("🎉 啟動器正常退出。")
    sys.exit(0)
