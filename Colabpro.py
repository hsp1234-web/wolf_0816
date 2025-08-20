# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器6(模組化執行器)
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "485" #@param {type:"string"}
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
#@markdown ---
#@markdown > **確認所有設定無誤後，點擊此儲存格左側的「執行」按鈕來啟動所有程序。**
#@markdown ---

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
                clear_output(wait=True); print("\n".join(self._build_output_buffer()), flush=True)
                time.sleep(self._refresh_rate)
            except Exception as e: print(f"\nDisplayManager 執行緒發生錯誤: {e}")
    def start(self): self._thread.start()
    def stop(self): self._stop_event.set(); self._thread.join(timeout=1)

# ==============================================================================
# PART 3: 啟動器邏輯與驗證
# ==============================================================================
def verify_codebase_version(project_path: Path, log_manager: LogManager) -> bool:
    """檢查關鍵檔案是否為最新版本，以避免執行過時的程式碼。"""
    log_manager.log("INFO", "正在驗證程式碼版本...")
    orchestrator_path = project_path / "src" / "core" / "orchestrator.py"
    expected_keyword = "db_stdout_thread"
    try:
        content = orchestrator_path.read_text(encoding='utf-8')
        if expected_keyword in content:
            log_manager.log("SUCCESS", "✅ 程式碼版本驗證通過。")
            return True
        else:
            log_manager.log("CRITICAL", "❌ 程式碼版本過舊！")
            log_manager.log("CRITICAL", "偵測到您下載的 `orchestrator.py` 缺少關鍵修復。")
            log_manager.log("CRITICAL", "這會導致啟動失敗。請先將最新的 Pull Request (PR) 合併到您的 GitHub 倉庫中。")
            return False
    except FileNotFoundError:
        log_manager.log("CRITICAL", f"❌ 找不到關鍵檔案: {orchestrator_path}")
        return False
    except Exception as e:
        log_manager.log("CRITICAL", f"❌ 驗證檔案時發生錯誤: {e}")
        return False

def create_log_viewer_html(log_manager):
    """產生一個包含頂部和底部複製按鈕的可收合日誌檢視器 HTML。"""
    try:
        log_history = log_manager.get_full_history(limit=LOG_COPY_MAX_LINES)
        escaped_log_content = html.escape("\n".join(log_history))
        num_logs = len(log_history)
        unique_log_id = f"log-area-{int(time.time() * 1000)}"
        onclick_js = f'''(async () => {{ try {{ const textToCopy = document.getElementById("{unique_log_id}").innerText; await navigator.clipboard.writeText(textToCopy); this.innerText="✅ 已複製!"; }} catch (err) {{ this.innerText="❌ 複製失敗"; }} finally {{ setTimeout(() => {{ this.innerText="📋 複製這 {num_logs} 條日誌"; }}, 2000); }} }})()'''.replace("\n", " ")
        top_button_html = f'<button onclick=\'{onclick_js}\' style="padding: 6px 12px; margin-bottom: 12px; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #fff;">📋 複製這 {num_logs} 條日誌</button>'
        bottom_button_html = f'<button onclick=\'{onclick_js}\' style="padding: 6px 12px; margin-top: 12px; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #fff;">📋 複製這 {num_logs} 條日誌</button>'
        return f'<details style="margin-top: 15px; margin-bottom: 15px; border: 1px solid #e0e0e0; padding: 12px; border-radius: 8px; background-color: #f9f9f9;"><summary style="cursor: pointer; font-weight: bold; color: #333;">點此展開/收合最近 {num_logs} 條詳細日誌</summary><div style="margin-top: 12px;">{top_button_html}<pre id="{unique_log_id}" style="background-color: #fff; padding: 12px; border: 1px solid #e0e0e0; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; font-size: 13px; color: #444;"><code>{escaped_log_content}</code></pre>{bottom_button_html}</div></details>'
    except Exception as e: return f"<p>❌ 產生最終日誌報告時發生錯誤: {e}</p>"

def launch_application(project_path_str: str, log_manager: LogManager):
    """主執行函式，呼叫模組化 runner 來啟動應用。"""
    project_path = Path(project_path_str)
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "啟動中...", "proxy_url": None}
    display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
    display_manager.start()
    runner_proc = None
    try:
        log_manager.log("INFO", "準備執行模組化啟動器 (runner)...")
        runner_script_path = project_path / "runner" / "main_runner.py"
        if not runner_script_path.exists(): raise FileNotFoundError(f"找不到啟動器腳本: {runner_script_path}。請確保此檔案已存在於您下載的 Git 分支中。")
        command = [sys.executable, str(runner_script_path)]
        runner_proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', bufsize=1)
        url_pattern = re.compile(r"FINAL_URL:\s*(https?://[^\s]+)")
        final_url_found = False
        for line in iter(runner_proc.stdout.readline, ''):
            clean_line = line.strip()
            if not clean_line: continue
            log_manager.log("RUNNER", clean_line)
            if "安裝伺服器依賴" in clean_line: shared_stats['status'] = "安裝依賴..."
            elif "啟動核心協調器" in clean_line: shared_stats['status'] = "啟動服務..."
            elif "前端建置成功" in clean_line: shared_stats['status'] = "服務已啟動..."
            match = url_pattern.search(clean_line)
            if match and not final_url_found:
                final_url_found = True
                port = match.group(1).split(':')[-1]
                log_manager.log("SUCCESS", f"內部服務 URL 已獲取: {match.group(1)}")
                shared_stats['status'] = "正在生成 Colab 代理連結..."
                js_script = f"google.colab.kernel.proxyPort({port}, {{'cache': false}})"
                proxy_url = colab_output.eval_js(f"(async () => await {js_script})()")
                shared_stats['proxy_url'] = proxy_url
                shared_stats['status'] = "✅ 應用程式已就緒"
                log_manager.log("SUCCESS", f"成功獲取代理連結: {proxy_url}")
        if runner_proc.wait() != 0: shared_stats['status'] = "❌ 啟動失敗"
    except Exception as e:
        log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}")
        shared_stats['status'] = f"❌ 啟動失敗: {e}"
    finally:
        if runner_proc and runner_proc.poll() is None: runner_proc.terminate()
        display_manager.stop()
        clear_output(wait=True)
        print("\n".join(display_manager._build_output_buffer()))
        print("\n--- 🏁 啟動程序結束 ---")
        display(HTML(create_log_viewer_html(log_manager)))
        log_manager.close()

if __name__ == "__main__":
    # 修正：將日誌資料庫建立在專案資料夾之外，避免被 `FORCE_REPO_REFRESH` 刪除
    db_path = Path(f"launcher_logs_{PROJECT_FOLDER_NAME}.db")
    log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, db_path=str(db_path))

    # 執行下載，並將 log_manager 傳入以便記錄
    project_path = download_repository(log_manager)

    if project_path:
        # 在啟動主應用前，先驗證程式碼版本
        if verify_codebase_version(Path(project_path), log_manager):
            launch_application(project_path_str=project_path, log_manager=log_manager)
        else:
            # 版本錯誤，顯示日誌報告並終止
            display(HTML(create_log_viewer_html(log_manager)))
            log_manager.close()
    else:
        log_manager.log("CRITICAL", "專案準備失敗，無法繼續啟動程序。")
        display(HTML(create_log_viewer_html(log_manager)))
        log_manager.close()
