# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器 (Git 下載與執行)
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "4.1.5" #@param {type:"string"}
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
        output_buffer = ["🐺 善狼一鍵啟動器 🐺", ""]
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
        output_buffer.append(f"⏱️ {int(mins):02d}分{int(secs):02d}秒 | 💻 CPU: {cpu} | 🧠 RAM: {ram} | 🔥 狀態: {self._stats.get('status', '初始化...')}")
        output_buffer.append("")
        if self._stats.get('proxy_url'):
            output_buffer.append(f"✅ 代理連結 (點擊開啟): {self._stats['proxy_url']}")
        else:
            output_buffer.append("⏳ 正在生成代理連結...")
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
        self._log_manager = log_manager; self._stats = stats_dict
        self.project_path = Path(project_path_str); self.port = port
        self.temp_server_manager = temp_server_manager; self.log_queue = log_queue
        self.server_process = None; self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _stream_process_output(self, process):
        for line in iter(process.stdout.readline, ''):
            clean_line = line.strip()
            self.log_queue.put({"log": clean_line})
            self._log_manager.log("DEBUG", clean_line)
        process.stdout.close()
        return process.wait()

    def _install_dependencies(self, requirements_file: str):
        req_path = self.project_path / requirements_file
        if not req_path.is_file():
            self._log_manager.log("WARN", f"未找到 {requirements_file}，跳過安裝。")
            return True
        self._log_manager.log("INFO", f"正在使用 uv 安裝 `{requirements_file}`...")
        self.log_queue.put({"log": f"\\033[1;36m> 開始安裝 {requirements_file}...\\033[0m"})
        self._stats['status'] = f"安裝依賴 ({requirements_file})..."
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
            command = [sys.executable, "-m", "uv", "pip", "install", "-r", str(req_path)]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', bufsize=1)
            return_code = self._stream_process_output(process)
            if return_code != 0:
                error_msg = f"依賴安裝失敗 ({requirements_file})，返回碼: {return_code}"
                self._log_manager.log("CRITICAL", error_msg)
                self.log_queue.put({"log": f"\\033[31m[ERROR] {error_msg}\\033[0m"})
                return False
            success_msg = f"✅ 成功安裝 {requirements_file}"
            self._log_manager.log("SUCCESS", success_msg)
            self.log_queue.put({"log": f"\\033[32m{success_msg}\\033[0m"})
            return True
        except Exception as e:
            error_msg = f"安裝 {requirements_file} 時發生嚴重錯誤: {e}"
            self._log_manager.log("CRITICAL", error_msg)
            self.log_queue.put({"log": f"\\033[31m[CRITICAL] {error_msg}\\033[0m"})
            return False

    def _run(self):
        try:
            if not self._install_dependencies("requirements-server.txt"): return
            if not self._install_dependencies("requirements-worker.txt"): return
            self.temp_server_manager.stop()
            time.sleep(1)
            self._log_manager.log("INFO", "🚀 所有依賴已備妥，正在啟動核心協調器...")
            self._stats['status'] = "啟動主程式..."
            orchestrator_script_path = self.project_path / "src" / "core" / "orchestrator.py"
            if not orchestrator_script_path.is_file():
                self._log_manager.log("CRITICAL", f"核心協調器未找到: {orchestrator_script_path}")
                return
            port_file_path = self.project_path / "src" / "db" / "db_manager.port"
            if port_file_path.exists():
                try: port_file_path.unlink()
                except Exception as e: self._log_manager.log("ERROR", f"清理舊埠號檔案失敗: {e}")
            launch_command = [sys.executable, str(orchestrator_script_path), "--no-mock", "--port", str(self.port)]
            process_env = os.environ.copy()
            try:
                key_from_secret = userdata.get('GOOGLE_API_KEY')
                if key_from_secret:
                    process_env['GOOGLE_API_KEY'] = key_from_secret
                    self._log_manager.log("SUCCESS", "✅ 成功從 Colab Secret 讀取 GOOGLE_API_KEY。")
            except Exception:
                self._log_manager.log("WARN", "⚠️ 無法從 Colab Secret 讀取金鑰，將嘗試從 config.json 讀取。")
            src_path_str = str((self.project_path / "src").resolve())
            process_env['PYTHONPATH'] = f"{src_path_str}{os.pathsep}{process_env.get('PYTHONPATH', '')}"
            self.server_process = subprocess.Popen(launch_command, cwd=str(self.project_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=process_env)
            self._log_manager.log("INFO", f"協調器子進程已啟動 (PID: {self.server_process.pid})，監聽日誌...")
            uvicorn_ready_pattern = re.compile(r"Uvicorn running on")
            for line in iter(self.server_process.stdout.readline, ''):
                if self._stop_event.is_set(): break
                self._log_manager.log("DEBUG", line.strip())
                if uvicorn_ready_pattern.search(line):
                    self._stats['status'] = "✅ 伺服器運行中"
                    self._log_manager.log("SUCCESS", "✅ 主應用程式已成功接管埠號並運行！")
                    self.log_queue.put({"status": "ready"})
            self.server_process.wait()
            if self._stats['status'] != "✅ 伺服器運行中":
                self._stats['status'] = "❌ 伺服器啟動失敗"
                self._log_manager.log("CRITICAL", "協調器進程在就緒前已終止。")
        except Exception as e:
            self._stats['status'] = "❌ 發生致命錯誤"; self._log_manager.log("CRITICAL", f"背景工作者執行緒出錯: {e}")
        finally:
            if self._stats['status'] != "✅ 伺服器運行中": self._stats['status'] = "⏹️ 已停止"

    def start(self): self._thread.start()
    def stop(self):
        self._stop_event.set()
        if self.server_process and self.server_process.poll() is None:
            self._log_manager.log("INFO", "正在終止伺服器進程...")
            try:
                os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGTERM)
                self.server_process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try: os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGKILL)
                except ProcessLookupError: pass
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

def install_system_deps():
    print("檢查並安裝系統級依賴 FFmpeg...")
    try:
        if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
            print("未偵測到 FFmpeg，開始安裝...")
            subprocess.run(["apt-get", "update", "-qq"], check=True)
            subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"], check=True)
            print("✅ FFmpeg 安裝完成。")
        else:
            print("✅ FFmpeg 已安裝。")
    except Exception as e:
        print(f"❌ 安裝 FFmpeg 時發生錯誤: {e}")

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
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "初始化...", "proxy_url": None}
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

        shared_stats['status'] = "尋找可用埠號..."
        port = find_free_port()
        log_manager.log("INFO", f"找到空閒埠號: {port}")
        temp_server_manager = TempServerManager(port=port, log_manager=log_manager, log_queue=log_queue, project_root=project_path_str)
        temp_server_manager.start()
        shared_stats['status'] = "建立狀態伺服器..."

        time.sleep(1)
        max_retries, retry_delay, js_timeout_ms, py_timeout_sec = 20, 1, 7000, 10
        js_get_url_script = f'''
        (async () => {{
            const proxyPromise = google.colab.kernel.proxyPort({port}, {{'cache': false}});
            const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error(`proxyPort call timed out after {js_timeout_ms}ms`)), {js_timeout_ms}));
            try {{ const url = await Promise.race([proxyPromise, timeoutPromise]); return {{'url': url, 'error': null}}; }}
            catch (e) {{ return {{'url': null, 'error': e.toString()}}; }}
        }})()
        '''

        log_manager.log("INFO", "啟動背景工作者，開始並行安裝依賴...")
        background_worker = BackgroundWorker(log_manager=log_manager, stats_dict=shared_stats, project_path_str=project_path_str, port=port, temp_server_manager=temp_server_manager, log_queue=log_queue)
        background_worker.start()

        for attempt in range(max_retries):
            shared_stats['status'] = f"正在嘗試取得代理連結... (第 {attempt + 1}/{max_retries} 次)"
            result_queue = queue.Queue()
            def _eval_js_in_thread(q, script):
                try: q.put({'result': colab_output.eval_js(script), 'error': None})
                except Exception as e: q.put({'result': None, 'error': e})
            eval_thread = threading.Thread(target=_eval_js_in_thread, args=(result_queue, js_get_url_script)); eval_thread.daemon = True; eval_thread.start()
            try:
                output = result_queue.get(timeout=py_timeout_sec)
                if output.get('error'):
                    error_msg = str(output['error']); shared_stats['status'] = f"嘗試失敗 ({error_msg[:50]}...)，1秒後重試。"
                    log_manager.log("WARN", f"獲取代理連結的背景執行緒發生錯誤: {error_msg}")
                else:
                    result = output.get('result')
                    if result and result.get('error'):
                        error_msg = str(result['error']); shared_stats['status'] = f"JS錯誤 ({error_msg[:50]}...)，1秒後重試。"
                        log_manager.log("WARN", f"獲取代理連結時發生 JS 錯誤: {error_msg}")
                    elif result and result.get('url') and result['url'].strip().startswith('http'):
                        candidate_url = result['url'].strip()
                        shared_stats['proxy_url'] = candidate_url; shared_stats['status'] = "✅ 成功取得代理連結！"
                        log_manager.log("SUCCESS", f"成功取得並驗證代理連結: {candidate_url}")
                        break
                    else:
                        shared_stats['status'] = "收到無效的回傳值，1秒後重試。"; log_manager.log("WARN", f"收到無效的代理回傳值: '{str(result)[:100]}...'")
            except queue.Empty:
                shared_stats['status'] = f"操作超時 ({py_timeout_sec}秒)，1秒後重試。"; log_manager.log("WARN", f"獲取代理連結操作超時 ({py_timeout_sec}秒)。")
            except Exception as e:
                error_msg = str(e); shared_stats['status'] = f"發生未預期錯誤 ({error_msg[:50]}...)，1秒後重試。"
                log_manager.log("ERROR", f"獲取代理連結迴圈發生未預期錯誤: {e}")
            time.sleep(retry_delay)

        if not shared_stats.get('proxy_url'):
            shared_stats['status'] = "❌ 取得代理連結失敗"; log_manager.log("CRITICAL", "無法取得代理連結，但背景安裝任務仍在繼續。")

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
