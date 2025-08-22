# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器6(模組化執行器)
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "525" #@param {type:"string"}
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
LOG_DISPLAY_LINES = 15 #@param {type:"integer"}
#@markdown **最大日誌複製數量**
LOG_COPY_MAX_LINES = 1500 #@param {type:"integer"}
#@markdown **時區設定**
TIMEZONE = "Asia/Taipei" #@param {type:"string"}
#@markdown **自動清理畫面 (ENABLE_CLEAR_OUTPUT)**
#@markdown > **勾選後，儀表板會自動刷新，介面較為清爽。取消勾選則會保留所有日誌，方便除錯。**
ENABLE_CLEAR_OUTPUT = True #@param {type:"boolean"}
#@markdown ---
#@markdown > **確認所有設定無誤後，點擊此儲存格左側的「執行」按鈕來啟動所有程序。**
#@markdown ---

# ======================================================================================
# ==                                  開發者日誌                                  ==
# ======================================================================================
#
# 版本: 2.0 (架構: 極速兩階段啟動)
# 日期: 2025-08-22T02:54:48+08:00
#
# 🔴 **禁止直接執行**: 本檔案 (Colabpro.py) 被設計為一個程式庫 (library)，
#    由 Colab Notebook 環境導入並呼叫。請勿透過 `python Colabpro.py` 直接執行。
#
# 🟡 **限制修改範圍**:
#    - **允許修改**: 僅限於核心啟動邏輯，即 `launch_application` 或類似功能的內部實作。
#    - **禁止修改**: 絕對不要更動任何與使用者介面 (ipywidgets)、參數輸入、
#      UI 顯示設計，以及最終 HTML 報告產生與複製按鈕相關的程式碼。
#
# 本次變更已將核心啟動邏輯重構為「兩階段啟動模式」，以實現快速載入。
#
# ======================================================================================

# ==============================================================================
# SECTION 0: 環境準備與核心依賴導入
# ==============================================================================
import sys
import os
import shutil
import subprocess
import sqlite3
import time
from datetime import datetime
import threading
from collections import deque
import re
from pathlib import Path
import html
import queue
import traceback

try:
    import pytz
except ImportError:
    print("正在安裝 pytz...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pytz"])
    import pytz

from IPython.display import clear_output, display, HTML
from google.colab import output as colab_output

# ==============================================================================
# PART 1: GIT 下載器功能
# ==============================================================================
def download_repository(log_manager):
    """
    負責處理 Git 倉庫的下載與更新。
    """
    project_path = Path(PROJECT_FOLDER_NAME)
    log_manager.log("INFO", f"準備下載專案至 '{PROJECT_FOLDER_NAME}'...")
    log_manager.log("INFO", f"  - 倉庫 (Repository): {REPOSITORY_URL}")
    log_manager.log("INFO", f"  - 分支 (Branch/Tag): {TARGET_BRANCH_OR_TAG}")

    if FORCE_REPO_REFRESH and project_path.exists():
        log_manager.log("WARN", f"偵測到舊的專案資料夾，正在強制刪除: {project_path}")
        try:
            shutil.rmtree(project_path)
            log_manager.log("SUCCESS", "✅ 舊資料夾已成功刪除。")
        except Exception as e:
            log_manager.log("CRITICAL", f"❌ 刪除舊資料夾時發生錯誤: {e}")
            return None

    if project_path.exists():
        log_manager.log("SUCCESS", f"✅ 專案資料夾 '{project_path}' 已存在，將跳過下載。")
        return str(project_path.resolve())

    log_manager.log("INFO", f"🚀 開始從 Git 下載...")
    git_command = ["git", "clone", "--branch", TARGET_BRANCH_OR_TAG, "--depth", "1", REPOSITORY_URL, str(project_path)]
    try:
        result = subprocess.run(git_command, check=False, capture_output=True, text=True, encoding='utf-8')
        if result.returncode == 0:
            log_manager.log("SUCCESS", "✅ 專案程式碼下載成功！")
            return str(project_path.resolve())
        else:
            stderr = result.stderr.lower()
            if "could not find remote branch" in stderr or "couldn't find remote ref" in stderr:
                log_manager.log("CRITICAL", f"❌ Git clone 失敗：在倉庫中找不到名為 '{TARGET_BRANCH_OR_TAG}' 的分支。")
                log_manager.log("CRITICAL", "請檢查您的分支名稱是否正確。")
            else:
                log_manager.log("CRITICAL", "❌ Git clone 失敗！")
                log_manager.log("ERROR", result.stderr)
            return None
    except Exception as e:
        log_manager.log("CRITICAL", f"❌ 下載過程中發生未預期的錯誤: {e}")
        return None

# ==============================================================================
# PART 2: UI 與日誌管理器
# ==============================================================================
class LogManager:
    def __init__(self, max_lines, timezone_str, db_path):
        self._log_deque = deque(maxlen=max_lines)
        self.timezone = pytz.timezone(timezone_str)
        self._db_path = db_path
        self._db_conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._initialize_db()
    def _initialize_db(self):
        with self._lock:
            cursor = self._db_conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS logs")
            cursor.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL)")
            self._db_conn.commit()
    def log(self, level: str, message: str):
        with self._lock:
            now = datetime.now(self.timezone)
            log_entry_for_display = {"timestamp": now, "level": level.upper(), "message": str(message)}
            self._log_deque.append(log_entry_for_display)
            cursor = self._db_conn.cursor()
            cursor.execute("INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)", (now.isoformat(), level.upper(), str(message)))
            self._db_conn.commit()
    def get_display_logs(self) -> list:
        with self._lock: return list(self._log_deque)
    def get_full_history(self, limit: int) -> list[str]:
        with self._lock:
            cursor = self._db_conn.cursor()
            cursor.execute("SELECT timestamp, level, message FROM logs ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [f"[{row[0]}] [{row[1]}] {row[2]}" for row in reversed(rows)]
    def close(self):
        if self._db_conn: self._db_conn.close()

ANSI_COLORS = {"SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m", "RESET": "\033[0m", "INFO": "\033[34m", "DEBUG": "\033[90m", "RUNNER": "\033[90m"}
def colorize(text, level): return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS.get('RESET', '')}"

class DisplayManager:
    def __init__(self, log_manager, stats_dict, refresh_rate):
        self._log_manager = log_manager; self._stats = stats_dict; self._refresh_rate = refresh_rate
        self._stop_event = threading.Event(); self._thread = threading.Thread(target=self._run, daemon=True)
    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["🐺 善狼一鍵啟動器 (v6.2 - 路徑修復) 🐺", ""]
        for log in self._log_manager.get_display_logs():
            ts, level, message = log['timestamp'].strftime('%H:%M:%S'), log['level'], log['message']
            match = re.match(r".*? - (INFO|WARN|ERROR|CRITICAL|SUCCESS|DEBUG) - (.*)", message)
            if match: level, message = match.groups()
            output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {message}")
        try:
            import psutil
            cpu, ram = f"{psutil.cpu_percent():5.1f}%", f"{psutil.virtual_memory().percent:5.1f}%"
        except ImportError: cpu, ram = " N/A ", " N/A "
        elapsed = time.monotonic() - self._stats.get("start_time_monotonic", time.monotonic())
        mins, secs = divmod(elapsed, 60)
        output_buffer.extend(["", f"⏱️ {int(mins):02d}分{int(secs):02d}秒 | 💻 CPU: {cpu} | 🧠 RAM: {ram} | 🔥 狀態: {self._stats.get('status', '初始化...')}", ""])
        output_buffer.append(f"✅ 應用程式連結 (點擊開啟): {self._stats['proxy_url']}" if self._stats.get('proxy_url') else "⏳ 正在啟動服務並生成連結...")
        return output_buffer
    def _run(self):
        while not self._stop_event.is_set():
            try:
                if ENABLE_CLEAR_OUTPUT:
                    clear_output(wait=True)
                print("\n".join(self._build_output_buffer()), flush=True)
                time.sleep(self._refresh_rate)
            except Exception as e: print(f"\nDisplayManager 執行緒發生錯誤: {e}")
    def start(self): self._thread.start()
    def stop(self): self._stop_event.set(); self._thread.join(timeout=1)

# ==============================================================================
# PART 3: 新版啟動器邏輯 (架構 v2.0 - 極速兩階段啟動)
# ==============================================================================
import socket

def _find_free_port() -> int:
    """尋找一個空閒的 TCP 埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def _run_subprocess(command, log_manager, cwd=None, env=None):
    """執行子程序並記錄其輸出。"""
    log_manager.log("DEBUG", f"執行指令: {' '.join(command)}")
    try:
        # 使用 Popen 以便我們可以處理長時間運行的進程
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1
        )
        # 僅讀取並記錄輸出，不等待完成
        for line in iter(process.stdout.readline, ''):
            if line:
                log_manager.log("RUNNER", line.strip())

        # 等待程序結束並獲取返回碼
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)

        log_manager.log("SUCCESS", f"✅ 指令 {' '.join(command[:2])}... 成功完成。")

    except FileNotFoundError:
        log_manager.log("CRITICAL", f"❌ 指令找不到: {command[0]}。請確保相關程式已安裝並在 PATH 中。")
        raise
    except subprocess.CalledProcessError as e:
        log_manager.log("CRITICAL", f"❌ 子程序執行失敗: {' '.join(command[:2])}... 返回碼: {e.returncode}")
        # 因為輸出已經被即時記錄，這裡不再重複打印
        raise
    except Exception as e:
        log_manager.log("CRITICAL", f"❌ 執行子程序時發生未預期錯誤: {e}")
        raise

def setup_venv_and_install_deps(venv_name: str, requirements_path: Path, project_path: Path, log_manager) -> Path:
    """
    建立一個獨立的虛擬環境並安裝指定的依賴。
    返回該虛擬環境的 Python 解譯器路徑。
    """
    log_manager.log("INFO", f"--- 為 '{venv_name}' 設定虛擬環境 ---")
    venv_dir = project_path / "venvs" # 將 venv 放在專案目錄下
    venv_path = venv_dir / venv_name

    # 確保 uv 已安裝
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
    except subprocess.CalledProcessError:
        log_manager.log("CRITICAL", "❌ 安裝 'uv' 失敗。")
        raise

    log_manager.log("INFO", f"建立虛擬環境於: {venv_path}")
    _run_subprocess([sys.executable, "-m", "uv", "venv", str(venv_path)], log_manager)

    python_executable = venv_path / "Scripts" / "python.exe" if sys.platform == "win32" else venv_path / "bin" / "python"

    log_manager.log("INFO", f"在 '{venv_name}' 環境中安裝依賴: {requirements_path}")
    if not requirements_path.exists():
        log_manager.log("CRITICAL", f"❌ 找不到依賴檔案: {requirements_path}")
        raise FileNotFoundError(f"找不到依賴檔案: {requirements_path}")

    _run_subprocess([
        sys.executable, "-m", "uv", "pip", "install",
        "-r", str(requirements_path),
        "--python", str(python_executable)
    ], log_manager)

    log_manager.log("SUCCESS", f"✅ '{venv_name}' 環境設定完成。")
    return python_executable

def build_frontend(project_path: Path, log_manager):
    """建置 Vue.js 前端應用。"""
    log_manager.log("INFO", "--- 檢查並建置前端 ---")
    vue_app_dir = project_path / "vue-app"
    dist_dir = vue_app_dir / "dist"

    if dist_dir.exists() and any(dist_dir.iterdir()):
        log_manager.log("SUCCESS", "✅ 前端 'dist' 目錄已存在，跳過建置。")
        return True

    log_manager.log("INFO", "前端 'dist' 目錄不存在或為空，開始建置...")
    if not (vue_app_dir / "package.json").exists():
        log_manager.log("CRITICAL", "❌ 'vue-app/package.json' 不存在，無法建置。")
        return False

    try:
        log_manager.log("INFO", "執行 'npm install'...")
        _run_subprocess(["npm", "install"], log_manager, cwd=vue_app_dir)
        log_manager.log("INFO", "執行 'npm run build'...")
        _run_subprocess(["npm", "run", "build"], log_manager, cwd=vue_app_dir)
        log_manager.log("SUCCESS", "✅ 前端建置成功！")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        # 錯誤已在 _run_subprocess 中記錄
        return False

def launch_application(project_path_str: str, log_manager: LogManager):
    """新版主執行函式，實現極速兩階段啟動。"""
    project_path = Path(project_path_str)
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "啟動中...", "proxy_url": None}
    display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
    display_manager.start()

    server_proc = None
    try:
        # --- 第一階段：極速啟動前端 ---
        shared_stats['status'] = "建置前端..."
        if not build_frontend(project_path, log_manager):
            raise RuntimeError("前端建置失敗，無法繼續。")

        shared_stats['status'] = "設定網頁伺服器..."
        server_reqs = project_path / "services" / "static_web_server" / "requirements.txt"
        server_python = setup_venv_and_install_deps("static_web_server", server_reqs, project_path, log_manager)

        port = _find_free_port()
        shared_stats['status'] = f"啟動網頁伺服器於埠號 {port}..."

        server_script_path = project_path / "services" / "static_web_server" / "main.py"
        command = [
            str(server_python), "-m", "uvicorn", "main:app",
            "--host", "0.0.0.0", "--port", str(port), "--log-level", "warning"
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(server_script_path.parent)
        env["STATIC_DIRECTORY"] = str(project_path / "vue-app" / "dist")

        server_proc = subprocess.Popen(command, cwd=server_script_path.parent, env=env)
        log_manager.log("SUCCESS", f"✅ 靜態網頁伺服器已啟動 (PID: {server_proc.pid})。")

        # 為了讓測試腳本可以捕獲，輸出本地 URL
        # 這是測試的"契約"
        print(f"APP_URL: http://127.0.0.1:{port}", flush=True)

        # 等待伺服器啟動
        time.sleep(5)

        # --- 開始獲取 Colab 代理連結 ---
        max_retries, retry_delay, js_timeout_ms, py_timeout_sec = 20, 1, 7000, 10
        js_get_url_script = f'''(async () => {{ const proxyPromise = google.colab.kernel.proxyPort({port}, {{'cache': false}}); const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error(`proxyPort call timed out after {js_timeout_ms}ms`)), {js_timeout_ms})); try {{ const url = await Promise.race([proxyPromise, timeoutPromise]); return {{'url': url, 'error': null}}; }} catch (e) {{ return {{'url': null, 'error': e.toString()}}; }} }})()'''

        for attempt in range(max_retries):
            shared_stats['status'] = f"正在嘗試取得代理連結... (第 {attempt + 1}/{max_retries} 次)"
            # ... (此處的 Colab JS 互動邏輯保持不變)
            result_queue = queue.Queue()
            def _eval_js_in_thread(q, script):
                try: q.put({'result': colab_output.eval_js(script), 'error': None})
                except Exception as e: q.put({'result': None, 'error': e, 'traceback': traceback.format_exc()})

            eval_thread = threading.Thread(target=_eval_js_in_thread, args=(result_queue, js_get_url_script))
            eval_thread.daemon = True
            eval_thread.start()

            try:
                output = result_queue.get(timeout=py_timeout_sec)
                # ... (處理回傳值的邏輯也保持不變)
                if output.get('error'):
                    log_manager.log("WARN", f"獲取代理連結的背景執行緒發生錯誤: {output['error']}")
                else:
                    result = output.get('result')
                    if result and result.get('url'):
                        shared_stats['proxy_url'] = result['url'].strip()
                        shared_stats['status'] = "✅ 應用程式已就緒"
                        log_manager.log("SUCCESS", f"成功取得代理連結: {shared_stats['proxy_url']}")
                        break
                    else:
                        log_manager.log("WARN", f"獲取代理連結時發生 JS 錯誤: {result.get('error', '未知錯誤')}")
            except queue.Empty:
                log_manager.log("WARN", f"獲取代理連結操作超時 ({py_timeout_sec}秒)。")

            time.sleep(retry_delay)

        if not shared_stats.get('proxy_url'):
            shared_stats['status'] = "❌ 取得代理連結失敗"
            log_manager.log("CRITICAL", "無法取得 Colab 代理連結。")
            raise RuntimeError("無法取得 Colab 代理連結。")

        # --- 應用程式持續運行 ---
        log_manager.log("INFO", "應用程式已進入持續運行模式。後端依賴正在背景安裝中...")
        log_manager.log("INFO", "使用 Colab 的「中斷執行」按鈕來停止所有服務。")
        while server_proc.poll() is None:
            time.sleep(5)
        log_manager.log("WARN", "後端伺服器程序已終止。")

    except KeyboardInterrupt:
        log_manager.log("WARN", "🛑 偵測到使用者手動中斷...")
    except Exception as e:
        log_manager.log("CRITICAL", f"❌ launch_application 發生未預期的致命錯誤: {e}", exc_info=True)
        shared_stats['status'] = f"❌ 致命錯誤: {e}"
    finally:
        if server_proc and server_proc.poll() is None:
            log_manager.log("INFO", "正在終止網頁伺服器...")
            server_proc.terminate()
        display_manager.stop()
        print("\n".join(display_manager._build_output_buffer()))
        print("\n--- 🏁 啟動程序結束 ---")
        display(HTML(create_log_viewer_html(log_manager)))
        log_manager.close()

def create_log_viewer_html(log_manager):
    """產生一個包含頂部和底部複製按鈕的可收合日誌檢視器 HTML。"""
    # 此函式保持不變
    try:
        log_history = log_manager.get_full_history(limit=LOG_COPY_MAX_LINES)
        escaped_lines = [html.escape(line) for line in log_history]
        escaped_log_content = "\n".join(escaped_lines)
        num_logs = len(log_history)
        unique_log_id = f"log-area-{int(time.time() * 1000)}"
        onclick_js = f'''(async () => {{ try {{ const textToCopy = document.getElementById("{unique_log_id}").innerText; await navigator.clipboard.writeText(textToCopy); this.innerText="✅ 已複製!"; }} catch (err) {{ this.innerText="❌ 複製失敗"; }} finally {{ setTimeout(() => {{ this.innerText="📋 複製這 {num_logs} 條日誌"; }}, 2000); }} }})()'''.replace("\n", " ")
        top_button_html = f'<button onclick=\'{onclick_js}\' style="padding: 6px 12px; margin-bottom: 12px; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #fff;">📋 複製這 {num_logs} 條日誌</button>'
        bottom_button_html = f'<button onclick=\'{onclick_js}\' style="padding: 6px 12px; margin-top: 12px; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #fff;">📋 複製這 {num_logs} 條日誌</button>'
        return f'<details style="margin-top: 15px; margin-bottom: 15px; border: 1px solid #e0e0e0; padding: 12px; border-radius: 8px; background-color: #f9f9f9;"><summary style="cursor: pointer; font-weight: bold; color: #333;">點此展開/收合最近 {num_logs} 條詳細日誌</summary><div style="margin-top: 12px;">{top_button_html}<pre id="{unique_log_id}" style="background-color: #fff; padding: 12px; border: 1px solid #e0e0e0; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; font-size: 13px; color: #444;"><code>{escaped_log_content}</code></pre>{bottom_button_html}</div></details>'
    except Exception as e: return f"<p>❌ 產生最終日誌報告時發生錯誤: {e}</p>"


if __name__ == "__main__":
    db_path = Path(f"launcher_logs_{PROJECT_FOLDER_NAME}.db")
    log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, db_path=str(db_path))
    project_path = download_repository(log_manager)
    if project_path:
        # 不再需要版本驗證，因為舊的 orchestrator 不再使用
        launch_application(project_path_str=project_path, log_manager=log_manager)
    else:
        log_manager.log("CRITICAL", "專案準備失敗，無法繼續啟動程序。")
        display(HTML(create_log_viewer_html(log_manager)))
        log_manager.close()
