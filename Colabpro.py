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
# PART 1: GIT 下載器功能 (保持不變)
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

    if FORCE_REPO_REFRESH and project_path.exists():
        print(f"⚠️ 偵測到舊的專案資料夾，正在強制刪除: {project_path}")
        try:
            shutil.rmtree(project_path)
            print("✅ 舊資料夾已成功刪除。")
        except Exception as e:
            print(f"❌ 刪除舊資料夾時發生錯誤: {e}")
            return None

    if project_path.exists():
        print(f"✅ 專案資料夾 '{project_path}' 已存在，將跳過下載。")
        print("如果您需要重新下載，請勾選 'FORCE_REPO_REFRESH' 後再執行一次。")
        return str(project_path.resolve())

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
            git_command, check=False, capture_output=True, text=True, encoding='utf-8'
        )
        if result.returncode == 0:
            print("\n" + result.stderr)
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
# PART 2: UI 與日誌管理器 (恢復資料庫功能)
# ==============================================================================
class LogManager:
    """日誌管理器：負責記錄、過濾和儲存所有日誌訊息至 SQLite。"""
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
            # 寫入顯示用的 deque
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
        with self._lock:
            return list(self._log_deque)

    def get_full_history(self, limit: int) -> list[str]:
        with self._lock:
            cursor = self._db_conn.cursor()
            # 取得最新的 N 筆日誌
            cursor.execute("SELECT timestamp, level, message FROM logs ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            # 格式化並反轉順序，讓日誌從舊到新
            return [f"[{row[0]}] [{row[1]}] {row[2]}" for row in reversed(rows)]

    def close(self):
        if self._db_conn:
            self._db_conn.close()

ANSI_COLORS = {"SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m", "RESET": "\033[0m", "INFO": "\033[34m", "DEBUG": "\033[90m", "RUNNER": "\033[90m"}
def colorize(text, level):
    return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS.get('RESET', '')}"

class DisplayManager:
    """顯示管理器：在背景執行緒中負責繪製純文字動態儀表板。"""
    def __init__(self, log_manager, stats_dict, refresh_rate):
        self._log_manager = log_manager
        self._stats = stats_dict
        self._refresh_rate = refresh_rate
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["🐺 善狼一鍵啟動器 (v5 - 模組化) 🐺", ""]
        logs_to_display = self._log_manager.get_display_logs()
        for log in logs_to_display:
            ts = log['timestamp'].strftime('%H:%M:%S')
            level = log['level']
            message = log['message']
            # 從 runner 的日誌中解析真實等級
            match = re.match(r".*? - (INFO|WARN|ERROR|CRITICAL|SUCCESS|DEBUG) - (.*)", message)
            if match:
                level = match.group(1)
                message = match.group(2)
            output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {message}")

        try:
            import psutil
            cpu = f"{psutil.cpu_percent():5.1f}%"
            ram = f"{psutil.virtual_memory().percent:5.1f}%"
        except ImportError:
            cpu, ram = " N/A ", " N/A "

        elapsed = time.monotonic() - self._stats.get("start_time_monotonic", time.monotonic())
        mins, secs = divmod(elapsed, 60)
        output_buffer.append("")
        output_buffer.append(f"⏱️ {int(mins):02d}分{int(secs):02d}秒 | 💻 CPU: {cpu} | 🧠 RAM: {ram} | 🔥 狀態: {self._stats.get('status', '初始化...')}")
        output_buffer.append("")
        if self._stats.get('proxy_url'):
            output_buffer.append(f"✅ 應用程式連結 (點擊開啟): {self._stats['proxy_url']}")
        else:
            output_buffer.append("⏳ 正在啟動服務並生成連結...")
        return output_buffer

    def _run(self):
        while not self._stop_event.is_set():
            try:
                clear_output(wait=True)
                print("\n".join(self._build_output_buffer()), flush=True)
                time.sleep(self._refresh_rate)
            except Exception as e:
                print(f"\nDisplayManager 執行緒發生錯誤: {e}")
                time.sleep(5)

    def start(self): self._thread.start()
    def stop(self):
        self._stop_event.set()
        try:
            self._thread.join(timeout=1)
        except Exception:
            pass

# ==============================================================================
# PART 3: 新的啟動器邏輯與日誌報告
# ==============================================================================
def display_final_log_report(log_manager: LogManager):
    """在程序結束時，顯示一個包含完整日誌和複製按鈕的 HTML 報告。"""
    log_history = log_manager.get_full_history(limit=LOG_COPY_MAX_LINES)
    log_content = "\n".join(log_history)
    escaped_log_content = html.escape(log_content)

    html_template = f"""
    <div style="border: 1px solid #ccc; border-radius: 8px; padding: 16px; background-color: #f9f9f9; font-family: monospace;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h3 style="margin: 0;">📋 完整執行日誌</h3>
            <button onclick="copyToClipboard('log-content-area')">複製下方日誌</button>
        </div>
        <pre id="log-content-area" style="white-space: pre-wrap; word-wrap: break-word; max-height: 400px; overflow-y: auto; background-color: #fff; padding: 10px; border: 1px solid #ddd; border-radius: 4px;">{escaped_log_content}</pre>
        <div style="text-align: right; margin-top: 12px;">
            <button onclick="copyToClipboard('log-content-area')">複製上方日誌</button>
        </div>
    </div>
    <script>
    function copyToClipboard(elementId) {{
        const text = document.getElementById(elementId).innerText;
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        alert('日誌已複製到剪貼簿！');
    }}
    </script>
    """
    display(HTML(html_template))

def launch_application(project_path_str: str):
    """主執行函式，呼叫新的模組化 runner 來啟動應用。"""
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "啟動中...", "proxy_url": None}
    db_path = Path(project_path_str) / "launcher_logs.db"
    log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, db_path=str(db_path))
    display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
    display_manager.start()

    runner_proc = None
    try:
        log_manager.log("INFO", "準備執行模組化啟動器 (runner)...")
        runner_script = Path(project_path_str) / "runner" / "main_runner.py"

        if not runner_script.exists():
            raise FileNotFoundError(f"找不到啟動器腳本: {runner_script}")

        command = [sys.executable, str(runner_script)]
        runner_proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1
        )

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
                internal_url = match.group(1)
                port = internal_url.split(':')[-1]
                log_manager.log("SUCCESS", f"內部服務 URL 已獲取: {internal_url}")
                shared_stats['status'] = "正在生成 Colab 代理連結..."

                js_script = f"google.colab.kernel.proxyPort({port}, {{'cache': false}})"
                proxy_url = colab_output.eval_js(f"(async () => await {js_script})()")
                shared_stats['proxy_url'] = proxy_url
                shared_stats['status'] = "✅ 應用程式已就緒"
                log_manager.log("SUCCESS", f"成功獲取代理連結: {proxy_url}")

        return_code = runner_proc.wait()
        if return_code != 0:
            log_manager.log("CRITICAL", f"啟動器程序異常退出，返回碼: {return_code}")
            shared_stats['status'] = "❌ 啟動失敗"

    except Exception as e:
        log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}")
        shared_stats['status'] = f"❌ 啟動失敗: {e}"
    finally:
        if runner_proc and runner_proc.poll() is None:
            runner_proc.terminate()

        display_manager.stop()
        clear_output(wait=True)
        print("\n".join(display_manager._build_output_buffer()))
        print("\n--- 🏁 啟動程序結束 ---")
        display_final_log_report(log_manager)
        log_manager.close()

if __name__ == "__main__":
    project_path = download_repository()
    if project_path:
        clear_output(wait=True)
        launch_application(project_path_str=project_path)
    else:
        print("\n" + "="*60)
        print("❌ 錯誤：專案準備失敗，無法繼續啟動程序。")
        print("="*60)
