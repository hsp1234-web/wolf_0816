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
import tarfile
import sysconfig

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

class BackgroundWorker:
    """背景工作者：在獨立執行緒中執行所有耗時的安裝與啟動任務。"""
    def __init__(self, log_manager, stats_dict, project_path_str, port, mini_server_process):
        self._log_manager = log_manager
        self._stats = stats_dict
        self.project_path = Path(project_path_str)
        self.port = port
        self.mini_server_process = mini_server_process
        self.main_server_process = None
        self._stop_event = threading.Event()
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
            # JULES'S FIX: To package dependencies, we must install them to a specific location.
            # However, for Colab, the default site-packages is what we want to cache.
            # So, the original install logic is correct for the "slow path".
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

    def _extract_dependencies(self, archive_path: Path) -> bool:
        """從 .tar.gz 檔案中解壓縮依賴。"""
        self._log_manager.log("INFO", f"正在從 {archive_path.name} 解壓縮...")
        self._stats['status'] = "解壓縮依賴..."
        try:
            # In Colab, we extract to the root, as paths in tar are absolute or relative to specific points
            extract_target = Path("/")
            self._log_manager.log(f"解壓縮目標路徑: {extract_target}")
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=extract_target)
            self._log_manager.log("SUCCESS", "✅ 依賴解壓縮完成。")
            return True
        except Exception as e:
            self._log_manager.log("CRITICAL", f"解壓縮依賴時發生錯誤: {e}", exc_info=True)
            return False

    def _create_dependency_cache(self, archive_path: Path) -> bool:
        """將已安裝的依賴打包成 .tar.gz 快取檔。"""
        self._log_manager.log("INFO", "偵測到首次安裝，正在建立依賴快取...")
        self._stats['status'] = "建立依賴快取..."
        try:
            # In Colab, packages are typically installed in /usr/local/lib/pythonX.Y/site-packages
            site_packages_path = next(p for p in sys.path if 'site-packages' in p and p.startswith('/usr/local/lib'))
            site_packages = Path(site_packages_path)

            # Also include frontend dependencies, which are in the project folder
            node_modules = self.project_path / "vue-app" / "node_modules"

            paths_to_cache = []
            if site_packages.exists():
                paths_to_cache.append(site_packages)
                self._log_manager.log(f"找到 site-packages 目錄: {site_packages}")
            else:
                self._log_manager.log("WARN", f"找不到 site-packages 目錄: {site_packages}")

            if node_modules.exists():
                paths_to_cache.append(node_modules)
                self._log_manager.log(f"找到 node_modules 目錄: {node_modules}")
            else:
                self._log_manager.log("WARN", f"找不到 node_modules 目錄: {node_modules}")

            if not paths_to_cache:
                self._log_manager.log("ERROR", "找不到任何可快取的依賴目錄。")
                return False

            self._log_manager.log(f"正在建立快取檔案: {archive_path}")
            with tarfile.open(archive_path, "w:gz") as tar:
                for path in paths_to_cache:
                    # arcname should be the path as it should be on extraction
                    # For site-packages, it's an absolute path.
                    # For node_modules, it's relative to the project dir.
                    arcname = path.as_posix()
                    self._log_manager.log(f"正在將 {path} (arcname: {arcname}) 加入快取...")
                    tar.add(path, arcname=arcname)

            self._log_manager.log("SUCCESS", f"✅ 成功建立依賴快取檔案: {archive_path.name}")
            return True
        except Exception as e:
            self._log_manager.log("CRITICAL", f"建立依賴快取時發生錯誤: {e}", exc_info=True)
            return False

    def _build_frontend(self) -> bool:
        """建置 Vue.js 前端應用。"""
        self._log_manager.log("INFO", "正在建置前端應用...")
        self._stats['status'] = "建置前端..."
        vue_app_dir = self.project_path / "vue-app"
        try:
            # We assume bun is installed or part of the environment
            log_msg = "使用 bun install 安裝前端依賴..."
            self._log_manager.log("INFO", log_msg)
            self.log_queue.put({"log": f"\\033[1;36m> {log_msg}\\033[0m"})
            # In cache mode, node_modules exists, but bun install is safe to run
            subprocess.run(["bun", "install"], cwd=vue_app_dir, check=True, capture_output=True, text=True, encoding='utf-8')

            log_msg = "使用 bun run build 建置前端..."
            self._log_manager.log("INFO", log_msg)
            self.log_queue.put({"log": f"\\033[1;36m> {log_msg}\\033[0m"})
            subprocess.run(["bun", "run", "build"], cwd=vue_app_dir, check=True, capture_output=True, text=True, encoding='utf-8')

            self._log_manager.log("SUCCESS", "✅ 前端應用建置成功。")
            return True
        except FileNotFoundError:
            self._log_manager.log("CRITICAL", "找不到 'bun' 指令。請確保 Bun.js 已安裝。")
            return False
        except subprocess.CalledProcessError as e:
            self._log_manager.log("CRITICAL", f"前端建置失敗: {e.stderr}")
            return False
        except Exception as e:
            self._log_manager.log("CRITICAL", f"前端建置時發生未預期錯誤: {e}", exc_info=True)
            return False

    def _update_status_file(self, status_message: str):
        """Helper to write status updates to the temp file for the mini_server."""
        status_file = self.project_path / "temp_status.json"
        try:
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump({"message": status_message}, f)
        except IOError as e:
            self._log_manager.log("WARN", f"無法寫入狀態檔案: {e}")

    def _run(self):
        try:
            self._update_status_file("正在準備環境...")

            cache_archive = self.project_path.parent / "dependencies.tar.gz"

            if cache_archive.is_file() and not FORCE_REPO_REFRESH:
                self._log_manager.log("INFO", "✅ 發現依賴快取，從快取啟動...")
                self._update_status_file("正在解壓縮依賴...")
                if not self._extract_dependencies(cache_archive):
                    raise RuntimeError("從快取解壓縮依賴失敗。")
            else:
                self._log_manager.log("INFO", "未發現依賴快取或已啟用強制刷新，執行完整安裝...")
                self._update_status_file("正在安裝前端依賴...")
                if not self._build_frontend():
                    raise RuntimeError("前端依賴準備失敗。")

                self._update_status_file("正在安裝後端伺服器依賴...")
                if not self._install_dependencies("requirements-server.txt"):
                    raise RuntimeError("伺服器依賴安裝失敗。")

                self._update_status_file("正在安裝後端工作者依賴...")
                if not self._install_dependencies("requirements-worker.txt"):
                    raise RuntimeError("工作者依賴安裝失敗。")

                self._update_status_file("正在建立依賴快取...")
                if not self._create_dependency_cache(cache_archive):
                    self._log_manager.log("WARN", "建立依賴快取失敗，但將繼續。")

            self._update_status_file("準備啟動主應用程式...")
            self._log_manager.log("INFO", "正在終止臨時伺服器...")
            self.mini_server_process.terminate()
            try:
                self.mini_server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.mini_server_process.kill()

            self._log_manager.log("INFO", "🚀 所有依賴已備妥，正在啟動核心協調器...")
            self._stats['status'] = "啟動主程式..."

            orchestrator_script_path = self.project_path / "src" / "core" / "orchestrator.py"
            launch_command = [sys.executable, str(orchestrator_script_path), "--port", str(self.port)]
            process_env = os.environ.copy()
            process_env['PYTHONPATH'] = f"{str(self.project_path / 'src')}{os.pathsep}{process_env.get('PYTHONPATH', '')}"

            self.main_server_process = subprocess.Popen(launch_command, cwd=str(self.project_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=process_env)

            uvicorn_ready_pattern = re.compile(r"Uvicorn running on")
            for line in iter(self.main_server_process.stdout.readline, ''):
                if self._stop_event.is_set(): break
                self._log_manager.log("DEBUG", line.strip())
                if uvicorn_ready_pattern.search(line):
                    self._stats['status'] = "✅ 伺服器運行中"
                    self._log_manager.log("SUCCESS", "✅ 主應用程式已成功接管埠號並運行！")

            self.main_server_process.wait()
            if self._stats['status'] != "✅ 伺服器運行中":
                raise RuntimeError("主伺服器未能成功啟動。")

        except Exception as e:
            self._stats['status'] = f"❌ 發生致命錯誤: {e}"
            self._log_manager.log("CRITICAL", f"背景工作者執行緒出錯: {e}", exc_info=True)
            self._update_status_file(f"錯誤: {e}")
        finally:
            if self._stats['status'] != "✅ 伺服器運行中":
                self._stats['status'] = "⏹️ 已停止"

    def start(self): self._thread.start()
    def stop(self):
        self._stop_event.set()
        if self.main_server_process and self.main_server_process.poll() is None:
            self._log_manager.log("INFO", "正在終止主伺服器進程...")
            try:
                os.killpg(os.getpgid(self.main_server_process.pid), subprocess.signal.SIGTERM)
                self.main_server_process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired, AttributeError):
                try:
                    os.killpg(os.getpgid(self.main_server_process.pid), subprocess.signal.SIGKILL)
                except Exception: pass
        self._thread.join(timeout=2)


# SECTION 2: 核心功能函式 (部分保留)
def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0)); return s.getsockname()[1]

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

# SECTION 3: 主程式執行入口
def launch_application(project_path_str: str):
    """主執行函式，採用兩階段火箭啟動。"""
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "初始化...", "proxy_url": None}
    log_manager, display_manager, background_worker = None, None, None
    mini_server_proc = None
    start_time = datetime.now(pytz.timezone(TIMEZONE))

    try:
        # 1. 初始化日誌和顯示
        db_path = Path(project_path_str) / "launcher_logs.db"
        log_levels = {name: globals()[name] for name in globals() if name.startswith("SHOW_LOG_LEVEL_")}
        log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, log_levels_to_show=log_levels, db_path=str(db_path))
        display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
        display_manager.start()
        log_manager.log("INFO", "顯示管理器已啟動。")

        # 2. 立即啟動最小化伺服器以顯示 UI
        shared_stats['status'] = "啟動臨時介面伺服器..."
        port = find_free_port()
        log_manager.log("INFO", f"找到空閒埠號: {port} 用於臨時伺服器")

        mini_server_script = str(Path(project_path_str) / "src" / "core" / "mini_server.py")
        mini_server_cmd = [sys.executable, mini_server_script, str(port)]
        mini_server_proc = subprocess.Popen(mini_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')

        log_manager.log("INFO", "等待臨時伺服器就緒...")
        time.sleep(3) # Give it a moment to start

        # 3. 獲取代理 URL
        js_get_url_script = f'''(async () => {{ const url = await google.colab.kernel.proxyPort({port}, {{'cache': false}}); return url; }})()'''
        try:
            proxy_url = colab_output.eval_js(js_get_url_script)
            shared_stats['proxy_url'] = proxy_url
            log_manager.log("SUCCESS", f"✅ 臨時介面已在: {proxy_url}")
            shared_stats['status'] = "介面準備就緒，背景準備中..."
        except Exception as e:
            log_manager.log("CRITICAL", f"無法獲取 Colab 代理連結: {e}")
            shared_stats['status'] = "❌ 獲取代理連結失敗"
            raise

        # 4. 啟動背景工作者執行完整安裝和主程式啟動
        log_manager.log("INFO", "啟動背景工作者，開始完整安裝流程...")
        # The port passed here is for the *final* orchestrator
        final_port = find_free_port()
        background_worker = BackgroundWorker(log_manager, shared_stats, project_path_str, final_port, mini_server_proc)
        background_worker.start()

        # 5. 等待背景工作者完成
        background_worker._thread.join()
        log_manager.log("INFO", "背景工作者執行緒已結束。")

    except Exception as e:
        if log_manager: log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}", exc_info=True)
        else: print(f"❌ 發生未預期的致命錯誤: {e}")
    finally:
        if background_worker: background_worker.stop()
        if mini_server_proc and mini_server_proc.poll() is None:
            mini_server_proc.terminate()
        if display_manager: display_manager.stop()

        end_time = datetime.now(pytz.timezone(TIMEZONE))
        if log_manager and display_manager:
            clear_output(wait=True)
            print("\n".join(display_manager._build_output_buffer()))
            print("\n--- ✅ 所有任務完成 ---")
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
