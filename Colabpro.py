# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器 (v7.0 - 極速啟動) 🐺
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "569" #@param {type:"string"}
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
# 版本: 2.3 (架構: 日誌系統穩定性修復)
# 日期: 2025-08-22T12:20:00+08:00
#
# 🔴 **禁止直接執行**: 本檔案 (Colabpro.py) 被設計為一個程式庫 (library)，
#    由 Colab Notebook 環境導入並呼叫。請勿透過 `python Colabpro.py` 直接執行。
#
# 🟡 **限制修改範圍**:
#    - **允許修改**: 僅限於核心啟動邏輯，即 `launch_application` 或類似功能的內部實作。
#    - **禁止修改**: 絕對不要更動任何與使用者介面 (ipywidgets)、參數輸入、
#      UI 顯示設計，以及最終 HTML 報告產生與複製按鈕相關的程式碼。
#
# 本次變更修正了因日誌資料庫路徑設定不當，導致在「強制刷新」模式下
# 發生「唯讀資料庫」錯誤的問題。已將日誌資料庫移回專案外部，確保
# 在刪除專案資料夾時，日誌系統仍能正常運作。
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
import types
import json

def _setup_colab_mocks():
    """如果不在真實的 Colab 環境中，則建立虛假的 google.colab 模組以避免 ImportError。"""
    print("[MOCK] 偵測到測試模式，正在注入虛假的 google.colab 模組...")
    class FakeColabOutput:
        def eval_js(self, script): return None
    google_module = types.ModuleType('google')
    google_colab_module = types.ModuleType('google.colab')
    google_colab_output_module = types.ModuleType('google.colab.output')
    google_colab_output_module.eval_js = FakeColabOutput().eval_js
    google_colab_module.output = google_colab_output_module
    google_module.colab = google_colab_module
    sys.modules.update({
        'google': google_module,
        'google.colab': google_colab_module,
        'google.colab.output': google_colab_output_module,
    })
    print("[MOCK] ✅ 虛假模組注入成功。")

if os.environ.get('IN_TEST_MODE') == '1':
    _setup_colab_mocks()

try:
    import pytz
except ImportError:
    print("正在安裝 pytz...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pytz"])
    import pytz

from IPython.display import clear_output, display, HTML
from google.colab import output as colab_output

# ==============================================================================
# PART 1: GIT 下載器功能 (保持不變)
# ==============================================================================
def download_repository(log_manager):
    project_path = Path(PROJECT_FOLDER_NAME)
    log_manager.log("INFO", f"準備下載專案至 '{PROJECT_FOLDER_NAME}'...")
    log_manager.log("INFO", f"  - 倉庫 (Repository): {REPOSITORY_URL}")
    log_manager.log("INFO", f"  - 分支 (Branch/Tag): {TARGET_BRANCH_OR_TAG}")
    if FORCE_REPO_REFRESH and project_path.exists():
        log_manager.log("WARN", f"偵測到舊的專案資料夾，正在強制刪除: {project_path}")
        shutil.rmtree(project_path)
        log_manager.log("SUCCESS", "✅ 舊資料夾已成功刪除。")
    if project_path.exists():
        log_manager.log("SUCCESS", f"✅ 專案資料夾 '{project_path}' 已存在，將跳過下載。")
        return str(project_path.resolve())
    log_manager.log("INFO", f"🚀 開始從 Git 下載...")
    subprocess.run(["git", "clone", "--branch", TARGET_BRANCH_OR_TAG, "--depth", "1", REPOSITORY_URL, str(project_path)], check=True)
    log_manager.log("SUCCESS", "✅ 專案程式碼下載成功！")
    return str(project_path.resolve())

# ==============================================================================
# PART 2: UI 與日誌管理器 (修復 LogManager)
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
    def log(self, level: str, message: str, **kwargs):
        full_message = str(message)
        if kwargs.get('exc_info'):
            full_message += "\n" + traceback.format_exc()
        with self._lock:
            now = datetime.now(self.timezone)
            display_message = str(message).split('\n')[0]
            log_entry_for_display = {"timestamp": now, "level": level.upper(), "message": display_message}
            self._log_deque.append(log_entry_for_display)
            cursor = self._db_conn.cursor()
            cursor.execute("INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)", (now.isoformat(), level.upper(), full_message))
            self._db_conn.commit()
    def get_display_logs(self) -> list:
        with self._lock: return list(self._log_deque)
    def get_full_history(self, limit: int) -> list[str]:
        with self._lock:
            # 確保資料庫連線是開啟的
            if not self._db_conn: return ["資料庫連線已關閉。"]
            try:
                cursor = self._db_conn.cursor()
                cursor.execute("SELECT timestamp, level, message FROM logs ORDER BY id DESC LIMIT ?", (limit,))
                rows = cursor.fetchall()
                return [f"[{row[0]}] [{row[1]}] {row[2]}" for row in reversed(rows)]
            except sqlite3.ProgrammingError:
                return ["資料庫連線已關閉。"]
    def close(self):
        if self._db_conn:
            self._db_conn.close()
            self._db_conn = None

ANSI_COLORS = {"SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m", "RESET": "\033[0m", "INFO": "\033[34m", "DEBUG": "\033[90m", "RUNNER": "\033[90m"}
def colorize(text, level): return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS.get('RESET', '')}"

class DisplayManager:
    def __init__(self, log_manager, stats_dict, refresh_rate):
        self._log_manager = log_manager; self._stats = stats_dict; self._refresh_rate = refresh_rate
        self._stop_event = threading.Event(); self._thread = threading.Thread(target=self._run, daemon=True)
    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["🐺 善狼一鍵啟動器 (v7.0 - 極速啟動) 🐺", ""]
        for log in self._log_manager.get_display_logs():
            ts, level, message = log['timestamp'].strftime('%H:%M:%S'), log['level'], log['message']
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
                if ENABLE_CLEAR_OUTPUT: clear_output(wait=True)
                print("\n".join(self._build_output_buffer()), flush=True)
                time.sleep(self._refresh_rate)
            except Exception: pass
    def start(self): self._thread.start()
    def stop(self): self._stop_event.set(); self._thread.join(timeout=1)

# ==============================================================================
# PART 3: 新版啟動器邏輯 (架構 v2.0 - 極速兩階段啟動)
# ==============================================================================
import socket

def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0)); return s.getsockname()[1]

def run_and_log_subprocess(command, log_manager, cwd=None, env=None):
    log_manager.log("DEBUG", f"執行指令: {' '.join(command)}")
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', bufsize=1)
    for line in iter(proc.stdout.readline, ''):
        if line: log_manager.log("RUNNER", line.strip())
    proc.wait()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, command)

def setup_venv_and_install_deps(venv_name: str, requirements_path: Path, project_path: Path, log_manager) -> Path:
    log_manager.log("INFO", f"--- 為 '{venv_name}' 設定虛擬環境 ---")
    venv_dir = project_path / "venvs"
    venv_path = venv_dir / venv_name
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
    run_and_log_subprocess([sys.executable, "-m", "uv", "venv", str(venv_path)], log_manager)
    python_executable = venv_path / "Scripts" / "python.exe" if sys.platform == "win32" else venv_path / "bin" / "python"
    if not requirements_path.exists():
        raise FileNotFoundError(f"找不到依賴檔案: {requirements_path}")
    run_and_log_subprocess([
        sys.executable, "-m", "uv", "pip", "install", "-r", str(requirements_path), "--python", str(python_executable)
    ], log_manager)
    log_manager.log("SUCCESS", f"✅ '{venv_name}' 環境設定完成。")
    return python_executable

def build_frontend(project_path: Path, log_manager):
    log_manager.log("INFO", "--- 檢查並建置前端 ---")
    vue_app_dir = project_path / "vue-app"
    if (vue_app_dir / "dist").exists() and any((vue_app_dir / "dist").iterdir()):
        log_manager.log("SUCCESS", "✅ 前端 'dist' 目錄已存在，跳過建置。")
        return
    run_and_log_subprocess(["npm", "install"], log_manager, cwd=vue_app_dir)
    run_and_log_subprocess(["npm", "run", "build"], log_manager, cwd=vue_app_dir)
    log_manager.log("SUCCESS", "✅ 前端建置成功！")

def launch_application(project_path_str: str, log_manager: LogManager):
    project_path = Path(project_path_str)
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "啟動中...", "proxy_url": None}
    display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
    display_manager.start()
    server_proc = None
    try:
        shared_stats['status'] = "建置前端..."
        build_frontend(project_path, log_manager)
        shared_stats['status'] = "設定網頁伺服器..."
        server_reqs = project_path / "services" / "static_web_server" / "requirements.txt"
        server_python = setup_venv_and_install_deps("static_web_server", server_reqs, project_path, log_manager)
        port = _find_free_port()
        shared_stats['status'] = f"啟動網頁伺服器於埠號 {port}..."
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_path / "services" / "static_web_server")
        server_proc = subprocess.Popen([
            str(server_python), "-m", "uvicorn", "main:app",
            "--host", "0.0.0.0", "--port", str(port), "--log-level", "warning"
        ], cwd=str(project_path / "services" / "static_web_server"), env=env)
        log_manager.log("SUCCESS", f"✅ 靜態網頁伺服器已啟動 (PID: {server_proc.pid})。")
        print(f"APP_URL: http://127.0.0.1:{port}", flush=True)
        time.sleep(5)

        for attempt in range(20):
            shared_stats['status'] = f"正在嘗試取得代理連結... (第 {attempt + 1}/20 次)"
            result_queue = queue.Queue()
            def _eval_js_in_thread(q):
                try: q.put(colab_output.eval_js(f'''(async () => {{ const url = await google.colab.kernel.proxyPort({port}, {{'cache': false}}); return url; }})()'''))
                except Exception as e: q.put(e)
            eval_thread = threading.Thread(target=_eval_js_in_thread, args=(result_queue,))
            eval_thread.start()
            eval_thread.join(timeout=10)
            if eval_thread.is_alive() or result_queue.empty():
                log_manager.log("WARN", "獲取代理連結操作超時。")
                continue
            result = result_queue.get()
            if isinstance(result, Exception):
                log_manager.log("WARN", f"獲取代理連結時發生 JS 錯誤: {result}")
            elif result and isinstance(result, str) and result.startswith('http'):
                shared_stats['proxy_url'] = result; shared_stats['status'] = "✅ 應用程式已就緒"
                log_manager.log("SUCCESS", f"成功取得代理連結: {result}")
                break
            else:
                log_manager.log("WARN", f"收到無效的代理回傳值: {str(result)[:100]}...")
            time.sleep(1)
        else:
            raise RuntimeError("無法取得 Colab 代理連結。")

        log_manager.log("INFO", "應用程式已進入持續運行模式。")
        # 使用一個長時間的休眠迴圈來保持主執行緒存活，
        # 這樣背景的 uvicorn 伺服器程序才能持續運行。
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log_manager.log("WARN", "收到使用者中斷指令，正在優雅地關閉所有服務...")
        shared_stats['status'] = "使用者手動關閉中..."
    except Exception as e:
        log_manager.log("CRITICAL", f"❌ launch_application 發生未預期的致命錯誤", exc_info=True)
        shared_stats['status'] = f"❌ 致命錯誤: {e}"
    finally:
        # 新增一個內層 try/except 來防止清理過程本身被中斷
        try:
            log_manager.log("INFO", "開始執行最終清理程序...")
            if server_proc and server_proc.poll() is None:
                log_manager.log("INFO", f"正在終止網頁伺服器 (PID: {server_proc.pid})...")
                server_proc.terminate()
                # 移除了 server_proc.wait()，讓關閉程序能立即回應，避免使用者感覺卡頓。

            display_manager.stop()
            print("\n".join(display_manager._build_output_buffer()))

            # 在關閉 log_manager 之前，先產生 HTML
            final_html = create_log_viewer_html(log_manager)
            log_manager.close()
            display(HTML(final_html))
        except KeyboardInterrupt:
            log_manager.log("WARN", "清理程序被再次中斷，可能會有殘留的背景程序。")
            print("\n[WARN] 清理程序被強制中斷。")
        except Exception as final_e:
            log_manager.log("ERROR", f"清理程序中發生未預期錯誤: {final_e}")

def create_log_viewer_html(log_manager):
    """
    產生一個包含日誌內容的、功能獨立的 HTML 檢視器。
    此版本經過重構，以提高「複製」按鈕的穩定性。
    """
    try:
        log_history = log_manager.get_full_history(limit=LOG_COPY_MAX_LINES)
        num_logs = len(log_history)
        unique_id = f"log-area-{int(time.time() * 1000)}"

        # 準備用於顯示和複製的日誌內容
        log_content_string = "\n".join(log_history)
        escaped_log_for_display = html.escape(log_content_string)

        # 1. 建立一個隱藏的 <textarea> 來儲存原始日誌文字。
        #    這種方法將資料與 JS 邏輯分離，可避免因日誌內容包含特殊字元而破壞 onclick 屬性。
        textarea_html = f'<textarea id="{unique_id}" style="position:absolute; left: -9999px; top: -9999px;" readonly>{escaped_log_for_display}</textarea>'

        # 2. 建立 onclick 的 JavaScript 程式碼。
        #    它會從 textarea 讀取內容，而不是直接將內容嵌入 JS 字串中。
        onclick_js = f'''(async () => {{
            const textarea = document.getElementById('{unique_id}');
            if (!textarea) {{ console.error('找不到日誌源'); return; }}
            try {{
                await navigator.clipboard.writeText(textarea.value);
                this.innerText = "✅ 已複製!";
            }} catch (err) {{
                console.error('複製失敗:', err);
                this.innerText = "❌ 複製失敗";
            }} finally {{
                setTimeout(() => {{ this.innerText = "📋 複製這 {num_logs} 條日誌"; }}, 2000);
            }}
        }})()'''.replace("\n", " ").strip()

        # 3. 建立按鈕 HTML
        button_html = f'<button onclick="{html.escape(onclick_js)}" style="padding: 6px 12px; margin: 12px 0; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #fff;">📋 複製這 {num_logs} 條日誌</button>'

        # 4. 組裝最終的 HTML
        return f'''
        <details style="margin-top: 15px; margin-bottom: 15px; border: 1px solid #e0e0e0; padding: 12px; border-radius: 8px; background-color: #f9f9f9;">
            <summary style="cursor: pointer; font-weight: bold; color: #333;">點此展開/收合最近 {num_logs} 條詳細日誌</summary>
            <div style="margin-top: 12px;">
                {textarea_html}
                {button_html}
                <pre style="background-color: #fff; padding: 12px; border: 1px solid #e0e0e0; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; font-size: 13px; color: #444;"><code>{escaped_log_for_display}</code></pre>
                {button_html}
            </div>
        </details>
        '''
    except Exception as e:
        # 確保錯誤訊息也能被正確顯示
        return f"<p>❌ 產生最終日誌報告時發生錯誤: {html.escape(str(e))}</p>"

if __name__ == "__main__":
    # 將日誌資料庫的路徑設定在根目錄，以避免在強制刷新專案時發生衝突
    db_path = Path(f"launcher_logs_{PROJECT_FOLDER_NAME}.db")
    log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, db_path=str(db_path))
    try:
        # 檢查是否處於測試模式，如果是，則跳過下載，直接使用當前目錄
        if os.environ.get('IN_TEST_MODE') == '1':
            project_path = str(Path('.').resolve())
            log_manager.log("INFO", "測試模式啟用：跳過 Git 下載，使用當前目錄作為專案路徑。")
        else:
            project_path = download_repository(log_manager)

        if project_path:
            launch_application(project_path_str=project_path, log_manager=log_manager)
        else:
            log_manager.log("CRITICAL", "專案準備失敗，無法繼續啟動程序。")
    except Exception as e:
        log_manager.log("CRITICAL", "啟動器主流程發生致命錯誤。", exc_info=True)
    finally:
        # 確保即使在 launch_application 之前失敗，也能顯示日誌
        if 'log_manager' in locals() and log_manager:
            # 在 finally 的最末端才顯示，確保所有日誌都已產生
            # 並且此時 log_manager 尚未關閉
            display(HTML(create_log_viewer_html(log_manager)))

            # 新增：將完整日誌儲存一份到 /content/paper/
            try:
                log_content = "\n".join(log_manager.get_full_history(limit=LOG_COPY_MAX_LINES))

                # 建立儲存目錄 /content/paper
                paper_dir = Path("/content/paper")
                paper_dir.mkdir(exist_ok=True)

                # 使用台北時區的 ISO 時間戳命名檔案
                timestamp_str = datetime.now(pytz.timezone(TIMEZONE)).isoformat(timespec='seconds')
                log_filename = f"{timestamp_str}.md"
                log_save_path = paper_dir / log_filename

                with open(log_save_path, "w", encoding="utf-8") as f:
                    f.write(f"# 執行日誌：{timestamp_str}\n\n")
                    f.write("```\n")
                    f.write(log_content)
                    f.write("\n```\n")

                log_manager.log("INFO", f"完整日誌副本已儲存至: {log_save_path}")
            except Exception as e:
                log_manager.log("WARN", f"無法儲存日誌檔案副本: {e}")

            log_manager.close()
