# -*- coding: utf-8 -*-
#@title 🐺 善狼啟動器 (Part 2: 執行)
#@markdown ---
#@markdown ### **通用設定**
#@markdown > **此處為儀表板顯示相關的常用設定。**
#@markdown ---
#@markdown **儀表板更新頻率 (秒)**
UI_REFRESH_SECONDS = 0.5 #@param {type:"number"}
#@markdown **日誌顯示行數**
LOG_DISPLAY_LINES = 10 #@param {type:"integer"}
#@markdown **最大日誌複製數量**
LOG_COPY_MAX_LINES = 500 #@param {type:"integer"}
#@markdown **時區設定**
TIMEZONE = "Asia/Taipei" #@param {type:"string"}
#@markdown ---
#@markdown > **確認設定無誤後，點擊此儲存格左側的「執行」按鈕來啟動服務。**
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
import subprocess
import socket
import http.server
import socketserver
import sqlite3
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

import os
import shutil
from pathlib import Path
import time
from datetime import datetime
import threading
from collections import deque
import re
import json
import queue
from IPython.display import clear_output, display, HTML
from google.colab import output as colab_output, userdata

# ==============================================================================
# SECTION 0.5: 狀態顯示頁面資源
# ==============================================================================

# BOOT_SCREEN_HTML 已被移至 src/static/colab_boot.html

class StatusServerRequestHandler(http.server.BaseHTTPRequestHandler):
    """一個自訂的 HTTP 請求處理器，用於提供狀態頁面和日誌串流。"""
    log_queue = None
    project_root = Path(".") # Class attribute for project root

    def do_GET(self):
        if self.path == '/':
            # 使用基於專案根目錄的絕對路徑，更穩健
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

        # 發送一條初始訊息，確認連線成功
        initial_message = {"log": "\\033[33m[SYSTEM] 成功連接至日誌串流...\\033[0m"}
        self.wfile.write(f"data: {json.dumps(initial_message)}\\n\\n".encode('utf-8'))
        self.wfile.flush()

        while True:
            try:
                log_line = self.log_queue.get(timeout=30)
                if log_line is None:  # 結束信號
                    break
                self.wfile.write(f"data: {json.dumps(log_line)}\\n\\n".encode('utf-8'))
                self.wfile.flush()
            except queue.Empty:
                # 發送註解以保持連線，防止超時
                self.wfile.write(b': heartbeat\\n\\n')
                self.wfile.flush()
            except BrokenPipeError:
                # 客戶端已斷開連線
                break
            except Exception as e:
                # 記錄伺服器端錯誤，並中斷連線
                print(f"SSE 串流發生錯誤: {e}")
                break

    def log_message(self, format, *args):
        """抑制 BaseHTTPRequestHandler 的預設日誌輸出，避免干擾。"""
        return

# ==============================================================================
# SECTION 1: 管理器類別定義 (Managers)
# ==============================================================================

class LogManager:
    """日誌管理器：負責記錄、過濾和儲存所有日誌訊息，並將其持久化到 SQLite 資料庫。"""
    def __init__(self, max_lines, timezone_str, log_levels_to_show, db_path):
        # 舊的記憶體部分，用於即時儀表板顯示，保持不變
        self._log_deque = deque(maxlen=max_lines)
        self.log_levels_to_show = log_levels_to_show

        # 新的資料庫部分
        self.timezone = pytz.timezone(timezone_str)
        self._db_path = db_path
        self._db_conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._lock = threading.Lock() # 鎖定資料庫和 deque 的寫入操作

        self._initialize_db()

    def _initialize_db(self):
        """初始化資料庫，清除舊表並建立新表。"""
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
        """記錄一條日誌到記憶體和資料庫。"""
        with self._lock:
            now = datetime.now(self.timezone)
            log_entry_for_display = {"timestamp": now, "level": level.upper(), "message": str(message)}
            self._log_deque.append(log_entry_for_display)

            # 寫入資料庫
            cursor = self._db_conn.cursor()
            cursor.execute(
                "INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)",
                (now.isoformat(), level.upper(), str(message))
            )
            self._db_conn.commit()

    def get_display_logs(self) -> list:
        """從記憶體中獲取用於動態顯示的日誌。"""
        with self._lock:
            all_logs = list(self._log_deque)
            return [log for log in all_logs if self.log_levels_to_show.get(f"SHOW_LOG_LEVEL_{log['level']}", False)]

    def _db_rows_to_dict_list(self, rows) -> list:
        """將資料庫查詢結果轉換為字典列表，並處理時間戳。"""
        log_list = []
        for row in rows:
            try:
                timestamp = datetime.fromisoformat(row[1])
            except ValueError:
                timestamp = datetime.now(self.timezone) # Fallback
            log_list.append({"timestamp": timestamp, "level": row[2], "message": row[3]})
        return log_list

    def get_full_history(self) -> list:
        """從資料庫獲取完整的日誌歷史。"""
        with self._lock:
            cursor = self._db_conn.cursor()
            cursor.execute("SELECT * FROM logs ORDER BY id ASC")
            rows = cursor.fetchall()
            return self._db_rows_to_dict_list(rows)

    def get_latest_logs(self, limit: int) -> list:
        """從資料庫獲取最新的 N 條日誌。"""
        with self._lock:
            cursor = self._db_conn.cursor()
            cursor.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            # 因為是 DESC 拿出來的，要反轉回來才是時間正序
            return self._db_rows_to_dict_list(reversed(rows))

    def close(self):
        """關閉資料庫連線。"""
        if self._db_conn:
            self._db_conn.close()

ANSI_COLORS = {
    "SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m",
    "CRITICAL": "\033[31m", "RESET": "\033[0m"
}

def colorize(text, level):
    return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS['RESET']}"

class DisplayManager:
    """顯示管理器：在背景執行緒中負責繪製純文字動態儀表板。"""
    def __init__(self, log_manager, stats_dict, refresh_rate):
        self._log_manager = log_manager; self._stats = stats_dict
        self._refresh_rate = refresh_rate; self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["🐺善狼下載啟動器🐺", ""]

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

        # 將代理連結移至此處
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
    """可重用地址的 TCPServer，解決 'Address already in use' 問題。"""
    allow_reuse_address = True

class TempServerManager:
    """臨時伺服器管理器：負責啟動一個臨時的 HTTP 伺服器以佔用埠號並顯示狀態。"""
    def __init__(self, port, log_manager, log_queue, project_root="."):
        self.port = port
        self._log_manager = log_manager
        self.log_queue = log_queue
        self.project_root = Path(project_root)
        self.server = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop_event = threading.Event()

    def _run(self):
        try:
            StatusServerRequestHandler.log_queue = self.log_queue
            StatusServerRequestHandler.project_root = self.project_root
            handler = StatusServerRequestHandler

            with ReusableTCPServer(("", self.port), handler) as httpd:
                self.server = httpd
                self._log_manager.log("DEBUG", f"狀態伺服器已在埠號 {self.port} 上綁定，準備啟動請求處理迴圈...")

                # 在背景執行緒中運行 serve_forever，以避免阻塞
                server_thread = threading.Thread(target=httpd.serve_forever)
                server_thread.daemon = True
                server_thread.start()
                self._log_manager.log("DEBUG", "請求處理迴圈已在背景啟動。")

                self._stop_event.wait() # 等待外部的停止信號
                self._log_manager.log("DEBUG", "狀態伺服器收到停止信號。")

        except Exception as e:
            self._log_manager.log("CRITICAL", f"!!! 狀態伺服器主執行緒發生致命錯誤: {e}")
        finally:
            if self.server:
                self._log_manager.log("DEBUG", "正在關閉伺服器...")
                self.server.shutdown()
                self.server.server_close()
            self._log_manager.log("SUCCESS", "狀態顯示伺服器已徹底關閉。")

    def start(self):
        self._thread.start()

    def stop(self):
        self._log_manager.log("INFO", "正在關閉狀態顯示伺服器...")
        # 向佇列發送結束信號
        if self.log_queue:
            self.log_queue.put(None)
        # 觸發停止事件，讓 _run 方法中的 wait() 結束
        self._stop_event.set()
        # 等待 _run 執行緒完成其清理工作 (shutdown, server_close)
        self._thread.join(timeout=5)

class BackgroundWorker:
    """背景工作者：在獨立執行緒中執行所有耗時的安裝與啟動任務。"""
    def __init__(self, log_manager, stats_dict, project_path_str, port, temp_server_manager, log_queue):
        self._log_manager = log_manager
        self._stats = stats_dict
        self.project_path = Path(project_path_str)
        self.port = port
        self.temp_server_manager = temp_server_manager
        self.log_queue = log_queue
        self.server_process = None
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _stream_process_output(self, process):
        """即時讀取並透過佇列串流子程序的輸出。"""
        for line in iter(process.stdout.readline, ''):
            clean_line = line.strip()
            # 將日誌同時發送到網頁前端和 Colab 主控台
            self.log_queue.put({"log": clean_line})
            self._log_manager.log("DEBUG", clean_line)
        process.stdout.close()
        return_code = process.wait()
        return return_code

    def _install_dependencies(self, requirements_file: str, installer: str = "uv"):
        req_path = self.project_path / requirements_file
        if not req_path.is_file():
            self._log_manager.log("WARN", f"未找到 {requirements_file}，跳過安裝。")
            return True

        self._log_manager.log("INFO", f"正在使用 {installer} 安裝 `{requirements_file}`...")
        self.log_queue.put({"log": f"\\033[1;36m> 開始安裝 {requirements_file}...\\033[0m"})
        self._stats['status'] = f"安裝依賴 ({requirements_file})..."

        try:
            # 確保 uv 已安裝
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
            # 使用 uv 安裝，移除 -q 以便擷取日誌
            command = [sys.executable, "-m", "uv", "pip", "install", "-r", str(req_path)]

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1  # Line-buffered
            )

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
            # 步驟 1: 安裝所有依賴
            if not self._install_dependencies("requirements-server.txt"): return
            if not self._install_dependencies("requirements-worker.txt"): return

            # 步驟 2: 關閉臨時伺服器
            self.temp_server_manager.stop()
            time.sleep(1) # 給予作業系統一點時間來釋放埠號

            # 步驟 3: 啟動核心協調器
            self._log_manager.log("INFO", "🚀 所有依賴已備妥，正在啟動核心協調器...")
            self._stats['status'] = "啟動主程式..."
            orchestrator_script_path = self.project_path / "src" / "core" / "orchestrator.py"
            if not orchestrator_script_path.is_file():
                self._log_manager.log("CRITICAL", f"核心協調器未找到: {orchestrator_script_path}")
                return

            # 清理舊的埠號檔案，以防萬一
            port_file_path = self.project_path / "src" / "db" / "db_manager.port"
            if port_file_path.exists():
                try: port_file_path.unlink()
                except Exception as e: self._log_manager.log("ERROR", f"清理舊埠號檔案失敗: {e}")

            launch_command = [sys.executable, str(orchestrator_script_path), "--no-mock", "--port", str(self.port)]

            process_env = os.environ.copy()
            # 處理 GOOGLE_API_KEY
            try:
                key_from_secret = userdata.get('GOOGLE_API_KEY')
                if key_from_secret:
                    process_env['GOOGLE_API_KEY'] = key_from_secret
                    self._log_manager.log("SUCCESS", "✅ 成功從 Colab Secret 讀取 GOOGLE_API_KEY。")
            except Exception:
                self._log_manager.log("WARN", "⚠️ 無法從 Colab Secret 讀取金鑰，將嘗試從 config.json 讀取。")

            # 設定 PYTHONPATH
            src_path_str = str((self.project_path / "src").resolve())
            process_env['PYTHONPATH'] = f"{src_path_str}{os.pathsep}{process_env.get('PYTHONPATH', '')}"

            self.server_process = subprocess.Popen(
                launch_command, cwd=str(self.project_path), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                preexec_fn=os.setsid, env=process_env
            )
            self._log_manager.log("INFO", f"協調器子進程已啟動 (PID: {self.server_process.pid})，監聽日誌...")

            uvicorn_ready_pattern = re.compile(r"Uvicorn running on")
            for line in iter(self.server_process.stdout.readline, ''):
                if self._stop_event.is_set(): break
                self._log_manager.log("DEBUG", line.strip())
                if uvicorn_ready_pattern.search(line):
                    self._stats['status'] = "✅ 伺服器運行中"
                    self._log_manager.log("SUCCESS", "✅ 主應用程式已成功接管埠號並運行！")

            self.server_process.wait()
            if self._stats['status'] != "✅ 伺服器運行中":
                self._stats['status'] = "❌ 伺服器啟動失敗"
                self._log_manager.log("CRITICAL", "協調器進程在就緒前已終止。")

        except Exception as e:
            self._stats['status'] = "❌ 發生致命錯誤"; self._log_manager.log("CRITICAL", f"背景工作者執行緒出錯: {e}")
        finally:
            if self._stats['status'] != "✅ 伺服器運行中":
                self._stats['status'] = "⏹️ 已停止"


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

# ==============================================================================
# SECTION 2: 核心功能函式
# ==============================================================================

def find_free_port() -> int:
    """尋找一個空閒的 TCP 埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def archive_reports(log_manager, start_time, end_time, status):
    # (此函式內容未變，保持原樣)
    print("\n\n" + "="*60 + "\n--- 任務結束，開始執行自動歸檔 ---\n" + "="*60)
    try:
        root_folder = Path(LOG_ARCHIVE_ROOT_FOLDER)
        root_folder.mkdir(exist_ok=True)
        ts_folder_name = start_time.strftime('%Y-%m-%dT%H-%M-%S%z')
        report_dir = root_folder / ts_folder_name
        report_dir.mkdir(exist_ok=True)
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
    # (此函式內容未變，保持原樣)
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

# ==============================================================================
# SECTION 3: 主程式執行入口 (全新設計)
# ==============================================================================

def main(project_path_str: str):
    """主執行函式，採用兩階段啟動，實現秒級回應。"""
    # 根據使用者需求，在啟動時強制清理一次儲存格輸出，確保環境乾淨。
    clear_output(wait=True)
    install_system_deps()
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "初始化...", "proxy_url": None}
    log_manager, display_manager, temp_server_manager, background_worker = None, None, None, None
    start_time = datetime.now(pytz.timezone(TIMEZONE))

    try:
        # 步驟 0: 建立通訊佇列
        log_queue = queue.Queue()

        # 步驟 1: 初始化日誌和顯示管理器
        db_path = Path(project_path_str) / "launcher_logs.db"
        log_levels = {name: globals()[name] for name in globals() if name.startswith("SHOW_LOG_LEVEL_")}
        log_manager = LogManager(
            max_lines=LOG_DISPLAY_LINES,
            timezone_str=TIMEZONE,
            log_levels_to_show=log_levels,
            db_path=str(db_path)
        )
        display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
        display_manager.start()
        log_manager.log("INFO", "顯示管理器已啟動。")

        # 步驟 2: 尋找空閒埠號並啟動狀態伺服器
        shared_stats['status'] = "尋找可用埠號..."
        port = find_free_port()
        log_manager.log("INFO", f"找到空閒埠號: {port}")
        temp_server_manager = TempServerManager(
            port=port,
            log_manager=log_manager,
            log_queue=log_queue,
            project_root=project_path_str
        )
        temp_server_manager.start()
        shared_stats['status'] = "建立狀態伺服器..."

        # 步驟 3: (關鍵) 立即取得代理連結
        time.sleep(1) # 等待狀態伺服器线程完全啟動
        max_retries, retry_delay = 20, 1

        # --- JULES' FINAL FIX (2025-08-17) ---
        # 實作 JS 層級的 Promise.race 超時機制，以主動處理 proxyPort 的掛起問題。
        # 同時縮短 Python 層級的超時，作為最終的安全網。
        js_timeout_ms = 8000
        py_timeout_sec = 10

        js_get_url_script = f'''
        (async () => {{
            const proxyPromise = google.colab.kernel.proxyPort({port}, {{'cache': false}});
            const timeoutPromise = new Promise((_, reject) =>
                setTimeout(() => reject(new Error(`proxyPort call timed out after {js_timeout_ms}ms`)), {js_timeout_ms})
            );

            try {{
                const url = await Promise.race([proxyPromise, timeoutPromise]);
                return {{'url': url, 'error': null}};
            }} catch (e) {{
                return {{'url': null, 'error': e.toString()}};
            }}
        }})()
        '''

        # -- 開始具備超時保護的代理連結獲取迴圈 --
        for attempt in range(max_retries):
            log_manager.log("INFO", f"正在嘗試取得代理連結... (第 {attempt + 1}/{max_retries} 次)")

            # 在獨立執行緒中執行耗時的 JS，以防主執行緒被卡死
            result_queue = queue.Queue()
            def _eval_js_in_thread(q, script):
                try:
                    # 這個函式在獨立執行緒中運行
                    q.put({'result': colab_output.eval_js(script), 'error': None})
                except Exception as e:
                    q.put({'result': None, 'error': e})

            eval_thread = threading.Thread(target=_eval_js_in_thread, args=(result_queue, js_get_url_script))
            eval_thread.daemon = True
            eval_thread.start()

            try:
                # 等待 JS 執行結果，使用新的、較短的 Python 超時
                output = result_queue.get(timeout={py_timeout_sec})

                # 檢查執行緒中是否發生錯誤
                if output.get('error'):
                    # 直接處理從執行緒傳來的錯誤，而不是重新拋出，以確保迴圈繼續。
                    log_manager.log("ERROR", f"獲取代理連結的背景執行緒發生錯誤: {output['error']}")
                    time.sleep(retry_delay)
                    continue # 強制繼續下一次重試

                result = output.get('result')

                # -- JS 成功返回，開始執行探測邏輯 --
                if result and result.get('error'):
                    log_manager.log("WARN", f"獲取代理連結時發生 JS 錯誤: {result['error']}")
                elif result and result.get('url') and result['url'].strip().startswith('http'):
                    candidate_url = result['url'].strip()
                    # 根據使用者需求 (2025-08-17)，移除主動連結探測。
                    # Colab 的 proxyPort API 返回的連結在某些情況下，即使功能正常，
                    # 在啟動初期探測也會收到 404。為提高相容性和啟動速度，
                    # 我們直接信任 API 返回的第一個 URL。
                    log_manager.log("INFO", f"取得候選 URL: {candidate_url}，根據設定跳過主動探測。")
                    shared_stats['proxy_url'] = candidate_url
                    log_manager.log("SUCCESS", "✅ 成功取得代理連結！")
                    break # 成功，跳出迴圈
                else:
                    log_manager.log("WARN", f"收到無效的代理回傳值: '{str(result)[:100]}...'")

            except queue.Empty:
                log_manager.log("WARN", "操作超時 (15秒)，`eval_js` 可能已卡住。正在強制繼續，進行下一次重試...")
            except Exception as e:
                # 為了確保絕對不會有例外導致迴圈中止，捕捉所有可能的錯誤
                log_manager.log("ERROR", f"獲取代理連結迴圈發生未預期錯誤: {e}")
                # 即使發生未知錯誤，也繼續重試
                pass

            time.sleep(retry_delay)

        if not shared_stats.get('proxy_url'):
            shared_stats['status'] = "❌ 取得代理連結失敗"
            log_manager.log("CRITICAL", "無法取得代理連結，啟動中止。")
            return

        # 步驟 4: 啟動背景工作者執行緒，處理所有耗時任務
        log_manager.log("INFO", "啟動背景工作者，開始安裝依賴...")
        background_worker = BackgroundWorker(
            log_manager=log_manager,
            stats_dict=shared_stats,
            project_path_str=project_path_str,
            port=port,
            temp_server_manager=temp_server_manager,
            log_queue=log_queue
        )
        background_worker.start()

        # 步驟 5: 主執行緒等待背景工作者完成
        background_worker._thread.join()
        log_manager.log("INFO", "背景工作者執行緒已結束。")

    except KeyboardInterrupt:
        if log_manager: log_manager.log("WARN", "🛑 偵測到使用者手動中斷...")
    except Exception as e:
        if log_manager: log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}")
        else: print(f"❌ 發生未預期的致命錯誤: {e}")
    finally:
        # 步驟 6: 清理所有資源
        if background_worker: background_worker.stop()
        if temp_server_manager and temp_server_manager._thread.is_alive(): temp_server_manager.stop()
        if display_manager and display_manager._thread.is_alive(): display_manager.stop()

        end_time = datetime.now(pytz.timezone(TIMEZONE))
        if log_manager and display_manager:
            clear_output(); print("\n".join(display_manager._build_output_buffer()))
            print("\n--- ✅ 所有任務完成，系統已安全關閉 ---")

            # 步驟 A: 歸檔完整日誌並顯示路徑
            archive_reports(log_manager, start_time, end_time, shared_stats.get('status', '未知'))

            # 步驟 B: 準備並顯示可收合的最新日誌
            try:
                latest_logs = log_manager.get_latest_logs(LOG_COPY_MAX_LINES)

                # 準備日誌內容以供顯示
                log_strings_for_html = []
                for log in latest_logs:
                    log_line = f"[{log['timestamp'].isoformat()}] [{log['level']}] {log['message']}"
                    # 為了 HTML 顯示，逸出特殊字元
                    log_strings_for_html.append(
                        log_line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    )

                logs_for_html_display = "\n".join(log_strings_for_html)
                num_logs = len(latest_logs)

                # 為日誌區塊產生一個唯一的 ID
                unique_log_id = f"log-area-{int(time.time() * 1000)}"

                # 產生採用 ID 選取器的 HTML，這是最穩健的方式
                collapsible_html = f'''
                <details style="margin-top: 15px; border: 1px solid #e0e0e0; padding: 12px; border-radius: 8px; background-color: #f9f9f9;">
                    <summary style="cursor: pointer; font-weight: bold; color: #333;">
                        點此展開/收合最近 {num_logs} 條詳細日誌
                    </summary>
                    <div style="margin-top: 12px;">
                        <button
                            onclick='(async () => {{
                                try {{
                                    const textToCopy = document.getElementById("{unique_log_id}").innerText;
                                    await navigator.clipboard.writeText(textToCopy);
                                    this.innerText="✅ 已複製!";
                                }} catch (err) {{
                                    this.innerText="❌ 複製失敗";
                                }} finally {{
                                    setTimeout(() => {{ this.innerText="📋 複製這 {num_logs} 條日誌"; }}, 2000);
                                }}
                            }})()'
                            style="padding: 6px 12px; margin-bottom: 12px; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #fff;">
                            📋 複製這 {num_logs} 條日誌
                        </button>
                        <pre id="{unique_log_id}" style="background-color: #fff; padding: 12px; border: 1px solid #e0e0e0; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; font-size: 13px; color: #444;"><code>{logs_for_html_display}</code></pre>
                    </div>
                </details>
                '''
                display(HTML(collapsible_html))

            except Exception as e:
                print(f"❌ 顯示最終日誌報告時發生錯誤: {e}")

        # 最後關閉資料庫連線
        if log_manager:
            log_manager.close()

if __name__ == "__main__":
    if 'PROJECT_PATH_FROM_DOWNLOADER' in globals() and Path(globals()['PROJECT_PATH_FROM_DOWNLOADER']).exists():
        print("✅ 找到由下載器準備的專案資料夾，準備啟動...")
        main(project_path_str=globals()['PROJECT_PATH_FROM_DOWNLOADER'])
    else:
        print("❌ 錯誤：找不到專案資料夾。")
        print("請確認您已成功執行第一個「🐺 善狼下載器」儲存格，並且沒有出現任何錯誤。")
