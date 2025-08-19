# -*- coding: utf-8 -*-
#@title 🚀 全自動化 E2E 測試器
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "3.2.5" #@param {type:"string"}
#@markdown **專案資料夾名稱 (PROJECT_FOLDER_NAME)**
PROJECT_FOLDER_NAME = "WEB1" #@param {type:"string"}
#@markdown **強制刷新後端程式碼 (FORCE_REPO_REFRESH)**
#@markdown > **如果勾選，每次執行都會先刪除舊的專案資料夾，再重新下載。**
FORCE_REPO_REFRESH = True #@param {type:"boolean"}
#@markdown ---
#@markdown ### **(2) 通用設定**
#@markdown > **此處為儀表板顯示相關的常用設定。**
#@markdown ---
#@markdown **儀表板更新頻率 (秒)**
UI_REFRESH_SECONDS = 0.3 #@param {type:"number"}
#@markdown **日誌顯示行數**
LOG_DISPLAY_LINES = 10 #@param {type:"integer"}
#@markdown **最大日誌複製數量**
LOG_COPY_MAX_LINES = 1500 #@param {type:"integer"}
#@markdown **時區設定**
TIMEZONE = "Asia/Taipei" #@param {type:"string"}
#@markdown ---
#@markdown > **確認所有設定無誤後，點擊此儲存格左側的「執行」按鈕來啟動所有程序。**
#@markdown ---

# ==============================================================================
# SECTION -1: 隱藏的預設參數
# ==============================================================================
# 日誌等級可見性 (預設全部開啟)
SHOW_LOG_LEVEL_BATTLE = True
SHOW_LOG_LEVEL_SUCCESS = True
SHOW_LOG_LEVEL_INFO = True
SHOW_LOG_LEVEL_WARN = True
SHOW_LOG_LEVEL_ERROR = True
SHOW_LOG_LEVEL_CRITICAL = True
SHOW_LOG_LEVEL_DEBUG = True
# 報告與歸檔設定
LOG_ARCHIVE_ROOT_FOLDER = "paper"

# ==============================================================================
# SECTION 0: 環境準備與核心依賴導入
# ==============================================================================
import sys
import os
import shutil
import subprocess
import socket
import http.server
import socketserver
import sqlite3
import time
from datetime import datetime
import threading
from collections import deque
import re
import json
import queue
from pathlib import Path

try:
    import requests
except ImportError:
    print("正在安裝 requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "requests"])
    import requests
try:
    import pytz
except ImportError:
    print("正在安裝 pytz...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pytz"])
    import pytz

from IPython.display import clear_output, display, HTML
from google.colab import output as colab_output, userdata

# ==============================================================================
# PART 1: GIT 下載器功能
# ==============================================================================
def download_repository():
    """
    負責處理 Git 倉庫的下載與更新。
    如果成功，返回專案的路徑；如果失敗，返回 None。
    """
    project_path = Path(PROJECT_FOLDER_NAME)
    print("="*60)
    print(f"準備下載專案至 '{project_path}'...")
    print("="*60)

    # 1. 檢查是否需要強制刷新
    if FORCE_REPO_REFRESH and project_path.exists():
        print(f"⚠️ 偵測到舊的專案資料夾，正在強制刪除: {project_path}")
        try:
            shutil.rmtree(project_path)
            print("✅ 舊資料夾已成功刪除。")
        except Exception as e:
            print(f"❌ 刪除舊資料夾時發生錯誤: {e}")
            return None

    # 2. 如果資料夾已存在 (且未被強制刷新)，則直接成功返回
    if project_path.exists():
        print(f"✅ 專案資料夾 '{project_path}' 已存在，將跳過下載。")
        print("如果您需要重新下載，請勾選 'FORCE_REPO_REFRESH' 後再執行一次。")
        return str(project_path.resolve())

    # 3. 執行 Git clone
    print(f"🚀 開始從 Git 下載 (分支/標籤: {TARGET_BRANCH_OR_TAG})...")
    git_command = [
        "git", "clone",
        "--branch", TARGET_BRANCH_OR_TAG,
        "--depth", "1",
        REPOSITORY_URL,
        str(project_path)
    ]

    try:
        result = subprocess.run(
            git_command,
            check=False,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )

        if result.returncode == 0:
            print("\n" + result.stderr) # Git clone 會把進度訊息放在 stderr
            print("✅ 專案程式碼下載成功！")
            resolved_path = str(project_path.resolve())
            print(f"📦 檔案已儲存至: {resolved_path}")
            return resolved_path
        else:
            print("\n❌ Git clone 失敗！")
            print("="*10 + " 錯誤訊息 " + "="*10)
            print(result.stderr)
            print("="*30)
            print("\n請檢查以下項目：")
            print(f"1. 倉庫網址是否正確: {REPOSITORY_URL}")
            print(f"2. 分支/標籤是否存在: {TARGET_BRANCH_OR_TAG}")
            return None

    except FileNotFoundError:
        print("❌ 錯誤：系統未安裝 Git。請確認您的執行環境。")
        return None
    except Exception as e:
        print(f"❌ 下載過程中發生未預期的錯誤: {e}")
        return None


# ==============================================================================
# PART 2: 善狼啟動器功能
# ==============================================================================

# SECTION 0.5: 狀態顯示頁面資源
class StatusServerRequestHandler(http.server.BaseHTTPRequestHandler):
    """一個自訂的 HTTP 請求處理器，用於提供狀態頁面和日誌串流。"""
    log_queue = None
    project_root = Path(".") # Class attribute for project root

    def do_GET(self):
        if self.path == '/':
            boot_page_path = self.project_root / "src" / "static" / "colab_boot.html"
            try:
                if not boot_page_path.is_file():
                    error_message = f"<h1>Error 500: Boot screen file not found.</h1><p>Expected at: {boot_page_path}</p>".encode('utf-8')
                    self.send_response(500)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(error_message)
                    return

                with open(boot_page_path, 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(f.read())
            except Exception as e:
                self.send_error(500, f"Error reading boot screen file: {e}")

        elif self.path == '/events':
            self._handle_sse_request()
        else:
            self.send_error(404, "File Not Found")

    def _handle_sse_request(self):
        """處理 Server-Sent Events (SSE) 連線。"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        initial_message = {"log": "\\033[33m[SYSTEM] 成功連接至日誌串流...\\033[0m"}
        self.wfile.write(f"data: {json.dumps(initial_message)}\\n\\n".encode('utf-8'))
        self.wfile.flush()

        while True:
            try:
                log_line = self.log_queue.get(timeout=30)
                if log_line is None: break
                self.wfile.write(f"data: {json.dumps(log_line)}\\n\\n".encode('utf-8'))
                self.wfile.flush()
            except queue.Empty:
                self.wfile.write(b': heartbeat\\n\\n')
                self.wfile.flush()
            except BrokenPipeError:
                break
            except Exception as e:
                print(f"SSE 串流發生錯誤: {e}")
                break

    def log_message(self, format, *args):
        """抑制 BaseHTTPRequestHandler 的預設日誌輸出。"""
        return

# SECTION 1: 管理器類別定義 (Managers)
class LogManager:
    """日誌管理器：負責記錄、過濾和儲存所有日誌訊息至 SQLite。"""
    def __init__(self, max_lines, timezone_str, log_levels_to_show, db_path):
        self._log_deque = deque(maxlen=max_lines)
        self.log_levels_to_show = log_levels_to_show
        self.timezone = pytz.timezone(timezone_str)
        self._db_path = db_path
        self._db_conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._initialize_db()

    def _initialize_db(self):
        with self._lock:
            cursor = self._db_conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS logs")
            cursor.execute("""
                CREATE TABLE logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL
                )
            """)
            self._db_conn.commit()

    def log(self, level: str, message: str):
        with self._lock:
            now = datetime.now(self.timezone)
            log_entry_for_display = {"timestamp": now, "level": level.upper(), "message": str(message)}
            self._log_deque.append(log_entry_for_display)
            cursor = self._db_conn.cursor()
            cursor.execute(
                "INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)",
                (now.isoformat(), level.upper(), str(message))
            )
            self._db_conn.commit()

    def get_display_logs(self) -> list:
        with self._lock:
            all_logs = list(self._log_deque)
            return [log for log in all_logs if self.log_levels_to_show.get(f"SHOW_LOG_LEVEL_{log['level']}", False)]

    def _db_rows_to_dict_list(self, rows) -> list:
        log_list = []
        for row in rows:
            try:
                timestamp = datetime.fromisoformat(row[1])
            except ValueError:
                timestamp = datetime.now(self.timezone)
            log_list.append({"timestamp": timestamp, "level": row[2], "message": row[3]})
        return log_list

    def get_full_history(self) -> list:
        with self._lock:
            cursor = self._db_conn.cursor()
            cursor.execute("SELECT * FROM logs ORDER BY id ASC")
            return self._db_rows_to_dict_list(cursor.fetchall())

    def get_latest_logs(self, limit: int) -> list:
        with self._lock:
            cursor = self._db_conn.cursor()
            cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return self._db_rows_to_dict_list(reversed(rows))

    def close(self):
        if self._db_conn: self._db_conn.close()

ANSI_COLORS = {"SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m", "RESET": "\033[0m"}
def colorize(text, level): return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS['RESET']}"

class DisplayManager:
    """顯示管理器：在背景執行緒中負責繪製純文字動態儀表板。"""
    def __init__(self, log_manager, stats_dict, refresh_rate):
        self._log_manager = log_manager; self._stats = stats_dict
        self._refresh_rate = refresh_rate; self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["🚀 全自動化 E2E 測試器 🚀", ""]
        logs_to_display = self._log_manager.get_display_logs()
        for log in logs_to_display:
            ts, level = log['timestamp'].strftime('%H:%M:%S'), log['level']
            output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {log['message']}")
        try:
            import psutil
            cpu, ram = f"{psutil.cpu_percent():5.1f}%", f"{psutil.virtual_memory().percent:5.1f}%"
        except ImportError: cpu, ram = "   N/A ", "   N/A "
        elapsed = time.monotonic() - self._stats.get("start_time_monotonic", time.monotonic())
        mins, secs = divmod(elapsed, 60)
        output_buffer.append("")
        output_buffer.append(f"⏱️ 執行時間: {int(mins):02d}分{int(secs):02d}秒 | 💻 CPU: {cpu} | 🧠 RAM: {ram}")
        output_buffer.append(f"🔥 測試狀態: {self._stats.get('status', '初始化...')}")
        return output_buffer

    def _run(self):
        while not self._stop_event.is_set():
            try:
                clear_output(wait=True); print("\n".join(self._build_output_buffer()), flush=True)
                time.sleep(self._refresh_rate)
            except Exception as e: print(f"\nDisplayManager 執行緒發生錯誤: {e}"); time.sleep(5)

    def start(self): self._thread.start()
    def stop(self): self._stop_event.set(); self._thread.join(timeout=2)

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

class TempServerManager:
    """臨時伺服器管理器：啟動臨時 HTTP 伺服器以佔用埠號並顯示狀態。"""
    def __init__(self, port, log_manager, log_queue, project_root="."):
        self.port = port; self._log_manager = log_manager; self.log_queue = log_queue
        self.project_root = Path(project_root); self.server = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop_event = threading.Event()

    def _run(self):
        try:
            StatusServerRequestHandler.log_queue = self.log_queue
            StatusServerRequestHandler.project_root = self.project_root
            with ReusableTCPServer(("", self.port), StatusServerRequestHandler) as httpd:
                self.server = httpd
                self._log_manager.log("DEBUG", f"狀態伺服器已在埠號 {self.port} 上綁定...")
                server_thread = threading.Thread(target=httpd.serve_forever); server_thread.daemon = True; server_thread.start()
                self._stop_event.wait()
        except Exception as e:
            self._log_manager.log("CRITICAL", f"!!! 狀態伺服器主執行緒發生致命錯誤: {e}")
        finally:
            if self.server: self.server.shutdown(); self.server.server_close()
            self._log_manager.log("SUCCESS", "狀態顯示伺服器已徹底關閉。")

    def start(self): self._thread.start()
    def stop(self):
        self._log_manager.log("INFO", "正在關閉狀態顯示伺服器...")
        if self.log_queue: self.log_queue.put(None)
        self._stop_event.set(); self._thread.join(timeout=5)

class BackgroundWorker:
    """背景工作者：在獨立執行緒中執行所有耗時的安裝與啟動任務。"""
    def __init__(self, log_manager, stats_dict, project_path_str, port, temp_server_manager, log_queue):
        self._log_manager = log_manager
        self._stats = stats_dict
        self.project_path = Path(project_path_str)
        self.port = port
        self.temp_server_manager = temp_server_manager
        self.log_queue = log_queue
        self.main_process = None
        self.sub_processes = []
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _stream_process_output(self, process, log_level="DEBUG"):
        """讀取子程序的輸出並串流至日誌。"""
        for line in iter(process.stdout.readline, ''):
            clean_line = line.strip()
            self.log_queue.put({"log": clean_line})
            self._log_manager.log(log_level, clean_line)
        process.stdout.close()
        return process.wait()

    def _run_command(self, command, cwd=None, env=None, log_level="DEBUG"):
        """執行一個指令並串流其輸出。"""
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1,
            cwd=cwd,
            env=env
        )
        return_code = self._stream_process_output(process, log_level)
        return return_code == 0

    def _install_dependencies(self, requirements_files: list, extra_packages: list = None):
        """安裝所有指定的依賴。"""
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
        except Exception as e:
            self._log_manager.log("CRITICAL", f"安裝 'uv' 失敗: {e}")
            return False

        for file in requirements_files:
            req_path = self.project_path / file
            if req_path.is_file():
                self._log_manager.log("INFO", f"正在使用 uv 安裝 `{file}`...")
                self._stats['status'] = f"安裝依賴 ({file})..."
                if not self._run_command([sys.executable, "-m", "uv", "pip", "install", "-r", str(req_path)]):
                    self._log_manager.log("CRITICAL", f"安裝 {file} 失敗。")
                    return False
                self._log_manager.log("SUCCESS", f"✅ 成功安裝 {file}")

        if extra_packages:
            self._log_manager.log("INFO", f"正在使用 uv 安裝額外套件: {', '.join(extra_packages)}...")
            self._stats['status'] = f"安裝額外套件..."
            if not self._run_command([sys.executable, "-m", "uv", "pip", "install"] + extra_packages):
                self._log_manager.log("CRITICAL", f"安裝額外套件失敗。")
                return False
            self._log_manager.log("SUCCESS", f"✅ 成功安裝額外套件。")
        return True

    def _stream_pytest_report(self, report_path: Path):
        """監控並解析 pytest-reportlog 的 JSONL 輸出。"""
        self._log_manager.log("INFO", f"實時測試日誌監控已啟動，等待 {report_path}...")
        while not report_path.exists() and not self._stop_event.is_set():
            time.sleep(0.5)
        if self._stop_event.is_set(): return
        with open(report_path, 'r', encoding='utf-8') as f:
            while not self._stop_event.is_set():
                line = f.readline()
                if not line:
                    time.sleep(0.2)
                    if self.main_process and self.main_process.poll() is not None:
                        break
                    continue
                try:
                    report = json.loads(line)
                    if report.get("when") == "call":
                        nodeid = report.get("nodeid", "Unknown Test")
                        outcome = report.get("outcome", "Unknown")
                        if outcome == "passed":
                            self._log_manager.log("SUCCESS", f"[測試通過] {nodeid}")
                        elif outcome == "failed":
                            self._log_manager.log("ERROR", f"[測試失敗] {nodeid}")
                            long_repr = report.get('longrepr', {}).get('reprcrash', {}).get('message', '')
                            if long_repr: self._log_manager.log("DEBUG", f"錯誤詳情: {long_repr}")
                        elif outcome == "skipped":
                            self._log_manager.log("WARN", f"[測試跳過] {nodeid}")
                except (json.JSONDecodeError, KeyError) as e:
                    self._log_manager.log("WARN", f"解析測試報告行時出錯: {e} - 行內容: {line[:100]}...")
        self._log_manager.log("INFO", "實時測試日誌監控已結束。")

    def _run(self):
        try:
            sys.path.insert(0, str(self.project_path / "src"))

            # 步驟 1: 安裝所有依賴
            self._log_manager.log("INFO", "步驟 1/5: 安裝所有依賴...")
            all_reqs = ["requirements-server.txt", "requirements-worker.txt"]
            test_pkgs = ["pytest", "pytest-reportlog"]
            if not self._install_dependencies(all_reqs, extra_packages=test_pkgs):
                self._stats['status'] = "❌ 依賴安裝失敗"
                return
            self._log_manager.log("SUCCESS", "✅ 所有依賴安裝完成。")

            # 步驟 2: 建置前端
            self._log_manager.log("INFO", "步驟 2/5: 建置前端...")
            self._stats['status'] = "建置前端 (bun)..."
            if not self._run_command(["bun", "install"], cwd=self.project_path / "vue-app", log_level="INFO"):
                 self._stats['status'] = "❌ 前端依賴安裝失敗"
                 return
            if not self._run_command(["bun", "run", "build"], cwd=self.project_path / "vue-app", log_level="INFO"):
                 self._stats['status'] = "❌ 前端建置失敗"
                 return
            self._log_manager.log("SUCCESS", "✅ 前端建置完成。")

            # 步驟 3: 啟動完整服務 (非模擬)
            self._log_manager.log("INFO", "步驟 3/5: 啟動完整應用程式服務...")
            self._stats['status'] = "啟動應用程式服務..."
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_path / "src") + os.pathsep + env.get("PYTHONPATH", "")

            # 啟動 Orchestrator 來管理所有服務
            orchestrator_cmd = [sys.executable, str(self.project_path / "src" / "core" / "orchestrator.py"), "--no-mock", "--port", str(self.port)]
            self.main_process = subprocess.Popen(orchestrator_cmd, cwd=str(self.project_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=env)

            # 等待服務就緒
            uvicorn_ready_pattern = re.compile(r"Uvicorn running on")
            service_ready = False
            for line in iter(self.main_process.stdout.readline, ''):
                self._log_manager.log("DEBUG", line.strip())
                if uvicorn_ready_pattern.search(line):
                    self._stats['status'] = "✅ 服務運行中"
                    self._log_manager.log("SUCCESS", "✅ 主應用程式已成功啟動！")
                    service_ready = True
                    break

            if not service_ready:
                self._log_manager.log("CRITICAL", "主應用程式啟動失敗，未偵測到 Uvicorn 運行信號。")
                self._stats['status'] = "❌ 服務啟動失敗"
                return

            # 步驟 4: 執行 Pytest
            self._log_manager.log("INFO", "步驟 4/5: 執行 E2E 測試...")
            self._stats['status'] = "▶️ 執行 E2E 測試..."
            report_path = self.project_path / "report.jsonl"
            if report_path.exists(): report_path.unlink()
            report_thread = threading.Thread(target=self._stream_pytest_report, args=(report_path,), daemon=True)
            report_thread.start()

            pytest_env = os.environ.copy()
            pytest_env["API_URL"] = f"http://127.0.0.1:{self.port}"
            pytest_cmd = [sys.executable, "-m", "pytest", str(self.project_path / "e2e_tests"), f"--report-log={report_path}"]
            pytest_proc = subprocess.Popen(pytest_cmd, cwd=self.project_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', env=pytest_env)
            self._stream_process_output(pytest_proc, log_level="INFO")

            # 步驟 5: 處理測試結果
            self._log_manager.log("INFO", "步驟 5/5: 處理測試結果...")
            self._stop_event.set()
            report_thread.join(timeout=2)

            if pytest_proc.returncode == 0:
                self._stats['status'] = "✅ 測試通過"
                self._log_manager.log("SUCCESS", "🎉 所有 E2E 測試已通過！")
            else:
                self._stats['status'] = "❌ 測試失敗"
                self._log_manager.log("ERROR", f"Pytest 測試運行失敗，退出碼: {pytest_proc.returncode}")

        except Exception as e:
            self._stats['status'] = "❌ 發生致命錯誤"
            self._log_manager.log("CRITICAL", f"背景工作者執行緒出錯: {e}")
        finally:
            if self._stats['status'] not in ["✅ 測試通過", "❌ 測試失敗"]:
                 self._stats['status'] = "⏹️ 已停止"

    def start(self): self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self.main_process and self.main_process.poll() is None:
            self._log_manager.log("INFO", "正在終止主進程...")
            try:
                os.killpg(os.getpgid(self.main_process.pid), subprocess.signal.SIGTERM)
                self.main_process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired, AttributeError):
                try:
                    os.killpg(os.getpgid(self.main_process.pid), subprocess.signal.SIGKILL)
                except Exception: pass
        self._thread.join(timeout=2)

# SECTION 2: 核心功能函式
def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0)); return s.getsockname()[1]

def archive_reports(log_manager, start_time, end_time, status):
    print("\n\n" + "="*60 + "\n--- 任務結束，開始執行自動歸檔 ---\n" + "="*60)
    try:
        root_folder = Path(LOG_ARCHIVE_ROOT_FOLDER); root_folder.mkdir(exist_ok=True)
        ts_folder_name = start_time.strftime('%Y-%m-%dT%H-%M-%S%z')
        report_dir = root_folder / ts_folder_name; report_dir.mkdir(exist_ok=True)
        log_history = log_manager.get_full_history()
        detailed_log_content = f"# 詳細日誌\n\n```\n" + "\n".join([f"[{log['timestamp'].isoformat()}] [{log['level']}] {log['message']}" for log in log_history]) + "\n```"
        (report_dir / "詳細日誌.md").write_text(detailed_log_content, encoding='utf-8')
        duration = end_time - start_time
        perf_report_content = f"# 效能報告\n\n- **任務狀態**: {status}\n- **開始時間**: `{start_time.isoformat()}`\n- **結束時間**: `{end_time.isoformat()}`\n- **總耗時**: `{str(duration)}`\n"
        (report_dir / "效能報告.md").write_text(perf_report_content.strip(), encoding='utf-8')
        (report_dir / "綜合報告.md").write_text(f"# 綜合報告\n\n{perf_report_content}\n{detailed_log_content}", encoding='utf-8')
        print(f"✅ 報告已成功歸檔至: {report_dir}")
    except Exception as e: print(f"❌ 歸檔報告時發生錯誤: {e}")

def _run_quiet_command(name, command):
    """執行一個系統指令並只在失敗時顯示輸出。"""
    try:
        print(f"正在檢查並安裝 {name}...")
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        print(f"✅ {name} 已就緒。")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 安裝 {name} 時發生錯誤。")
        print(f"返回碼: {e.returncode}")
        print("--- STDOUT ---\n" + e.stdout)
        print("--- STDERR ---\n" + e.stderr)
        return False
    except FileNotFoundError:
        print(f"❌ 錯誤：指令 '{command[0]}' 未找到。請確保您的 Colab 環境已安裝 npm。")
        return False
    except Exception as e:
        print(f"❌ 安裝 {name} 時發生未預期的錯誤: {e}")
        return False

def install_system_deps():
    """安裝所有必要的系統級和前端依賴。"""
    print("="*60)
    print("🚀 開始準備核心測試環境...")
    print("="*60)

    # 1. 安裝 FFmpeg
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        _run_quiet_command("FFmpeg", ["apt-get", "update", "-qq"])
        _run_quiet_command("FFmpeg", ["apt-get", "install", "-y", "-qq", "ffmpeg"])
    else:
        print("✅ FFmpeg 已安裝。")

    # 2. 安裝 Bun
    if subprocess.run(["which", "bun"], capture_output=True).returncode != 0:
        if not _run_quiet_command("Bun", ["npm", "install", "-g", "bun"]):
            # 如果失敗，記錄一個更嚴重的錯誤
            print("‼️ Bun 安裝失敗，後續的前端建置步驟可能會失敗。")
    else:
        print("✅ Bun 已安裝。")

    # 3. 安裝 Playwright 瀏覽器
    print("正在安裝 Playwright 所需的瀏覽器核心...")
    if not _run_quiet_command("Playwright Browsers", [sys.executable, "-m", "playwright", "install"]):
         print("‼️ Playwright 瀏覽器安裝失敗，E2E 測試將無法運行。")

    print("-" * 60)
    print("✅ 核心測試環境準備完畢。")
    print("-" * 60)

def create_log_viewer_html(log_manager):
    """產生一個包含頂部和底部複製按鈕的可收合日誌檢視器 HTML。"""
    try:
        latest_logs = log_manager.get_latest_logs(LOG_COPY_MAX_LINES)
        log_strings_for_html = []
        for log in latest_logs:
            log_line = f"[{log['timestamp'].isoformat()}] [{log['level']}] {log['message']}"
            log_strings_for_html.append(log_line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

        logs_for_html_display = "\n".join(log_strings_for_html)
        num_logs = len(latest_logs)
        unique_log_id = f"log-area-{int(time.time() * 1000)}"

        # 為按鈕定義 onclick JavaScript 邏輯
        onclick_js = f'''(async () => {{
            try {{
                const textToCopy = document.getElementById("{unique_log_id}").innerText;
                await navigator.clipboard.writeText(textToCopy);
                this.innerText="✅ 已複製!";
            }} catch (err) {{
                this.innerText="❌ 複製失敗";
            }} finally {{
                setTimeout(() => {{ this.innerText="📋 複製這 {num_logs} 條日誌"; }}, 2000);
            }}
        }})()'''.replace("\n", " ")

        # 定義按鈕 HTML 模板
        top_button_html = f'''<button onclick='{onclick_js}' style="padding: 6px 12px; margin-bottom: 12px; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #fff;">
            📋 複製這 {num_logs} 條日誌
        </button>'''
        bottom_button_html = f'''<button onclick='{onclick_js}' style="padding: 6px 12px; margin-top: 12px; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #fff;">
            📋 複製這 {num_logs} 條日誌
        </button>'''

        return f'''
        <details style="margin-top: 15px; margin-bottom: 15px; border: 1px solid #e0e0e0; padding: 12px; border-radius: 8px; background-color: #f9f9f9;">
            <summary style="cursor: pointer; font-weight: bold; color: #333;">
                點此展開/收合最近 {num_logs} 條詳細日誌
            </summary>
            <div style="margin-top: 12px;">
                {top_button_html}
                <pre id="{unique_log_id}" style="background-color: #fff; padding: 12px; border: 1px solid #e0e0e0; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; font-size: 13px; color: #444;"><code>{logs_for_html_display}</code></pre>
                {bottom_button_html}
            </div>
        </details>
        '''
    except Exception as e:
        return f"<p>❌ 產生最終日誌報告時發生錯誤: {e}</p>"


# SECTION 3: 主程式執行入口
def launch_application(project_path_str: str):
    """主執行函式，採用兩階段啟動。"""
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "初始化..."}
    log_manager, display_manager, temp_server_manager, background_worker = None, None, None, None
    start_time = datetime.now(pytz.timezone(TIMEZONE))

    try:
        log_queue = queue.Queue()
        db_path = Path(project_path_str) / "launcher_logs.db"
        log_levels = {name: globals()[name] for name in globals() if name.startswith("SHOW_LOG_LEVEL_")}
        log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, log_levels_to_show=log_levels, db_path=str(db_path))
        display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)

        display_manager.start()
        log_manager.log("INFO", "顯示管理器已啟動。")

        port = find_free_port()
        log_manager.log("INFO", f"為測試伺服器保留埠號: {port}")

        # TempServer is not strictly needed anymore as we don't need a placeholder page,
        # but we can keep it for future use or simple status display during setup.
        temp_server_manager = TempServerManager(port=port, log_manager=log_manager, log_queue=log_queue, project_root=project_path_str)
        temp_server_manager.start()

        log_manager.log("INFO", "啟動背景工作者，開始全自動化測試流程...")
        background_worker = BackgroundWorker(log_manager=log_manager, stats_dict=shared_stats, project_path_str=project_path_str, port=port, temp_server_manager=temp_server_manager, log_queue=log_queue)
        background_worker.start()

        background_worker._thread.join()
        log_manager.log("INFO", "背景工作者執行緒已結束。")

    except KeyboardInterrupt:
        if log_manager: log_manager.log("WARN", "🛑 偵測到使用者手動中斷...")
    except Exception as e:
        if log_manager: log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}")
        else: print(f"❌ 發生未預期的致命錯誤: {e}")
    finally:
        if background_worker: background_worker.stop()
        if temp_server_manager and temp_server_manager._thread.is_alive(): temp_server_manager.stop()
        if display_manager and display_manager._thread.is_alive(): display_manager.stop()

        end_time = datetime.now(pytz.timezone(TIMEZONE))
        if log_manager and display_manager:
            clear_output(wait=True)

            # 顯示最終狀態
            print("\n".join(display_manager._build_output_buffer()))
            print("\n--- ✅ 所有任務完成，系統已安全關閉 ---")

            # 歸檔
            archive_reports(log_manager, start_time, end_time, shared_stats.get('status', '未知'))

            # 顯示單一的、包含雙按鈕的日誌檢視器
            display(HTML(create_log_viewer_html(log_manager)))

        if log_manager: log_manager.close()


if __name__ == "__main__":
    # 步驟 1: 下載
    project_path = download_repository()
    time.sleep(2) # 等待一下讓輸出顯示完全

    # 步驟 2: 如果下載成功，則啟動應用
    if project_path and Path(project_path).exists():
        clear_output(wait=True)
        print("✅ 專案已準備就緒，開始啟動程序...")
        install_system_deps()
        launch_application(project_path_str=project_path)
    else:
        print("\n" + "="*60)
        print("❌ 錯誤：專案準備失敗，無法繼續啟動程序。")
        print("請檢查上方的 Git 下載日誌以了解詳細原因。")
        print("="*60)
