# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器5 (模組化執行器)
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
# PART 2: UI 與日誌管理器 (大部分保持不變)
# ==============================================================================
class LogManager:
    """日誌管理器：負責記錄、過濾和顯示日誌。"""
    def __init__(self, max_lines, timezone_str):
        self._log_deque = deque(maxlen=max_lines)
        self.timezone = pytz.timezone(timezone_str)
        self._lock = threading.Lock()
        # 移除日誌等級可見性過濾，簡化邏輯，永遠顯示所有日誌
        # 移除資料庫相關程式碼，簡化為僅在記憶體中顯示

    def log(self, level: str, message: str):
        with self._lock:
            now = datetime.now(self.timezone)
            log_entry = {"timestamp": now, "level": level.upper(), "message": str(message)}
            self._log_deque.append(log_entry)

    def get_display_logs(self) -> list:
        with self._lock:
            return list(self._log_deque)

ANSI_COLORS = {"SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m", "RESET": "\033[0m", "INFO": "\033[34m", "DEBUG": "\033[90m"}
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
            # 從 runner 的日誌中解析真實等級
            match = re.match(r".*? - (INFO|WARN|ERROR|CRITICAL|SUCCESS|DEBUG) - (.*)", log['message'])
            if match:
                level = match.group(1)
                message = match.group(2)
                output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {message}")
            else:
                # 如果不匹配，則按原樣顯示
                output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', 'INFO')} {log['message']}")

        try:
            # psutil 可能尚未安裝，進行保護
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
            self._thread.join(timeout=2)
        except Exception:
            pass

# ==============================================================================
# PART 3: 新的、簡化的啟動器邏輯
# ==============================================================================
def launch_application(project_path_str: str):
    """
    主執行函式，呼叫新的模組化 runner 來啟動應用。
    """
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "啟動中...", "proxy_url": None}
    log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE)
    display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
    display_manager.start()

    runner_proc = None
    try:
        log_manager.log("INFO", "準備執行模組化啟動器 (runner)...")
        runner_script = Path(project_path_str) / "runner" / "main_runner.py"

        if not runner_script.exists():
            log_manager.log("CRITICAL", f"找不到啟動器腳本: {runner_script}")
            shared_stats['status'] = "❌ 啟動失敗：找不到核心檔案"
            return

        command = [sys.executable, str(runner_script)]
        runner_proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # 將 stderr 合併到 stdout
            text=True,
            encoding='utf-8',
            bufsize=1 # 行緩衝
        )

        url_pattern = re.compile(r"FINAL_URL:\s*(https?://[^\s]+)")
        final_url_found = False

        for line in iter(runner_proc.stdout.readline, ''):
            clean_line = line.strip()
            log_manager.log("RUNNER", clean_line) # 將 runner 的所有輸出都顯示出來

            # 更新狀態，讓使用者看到進度
            if "安裝伺服器依賴" in clean_line:
                shared_stats['status'] = "安裝依賴..."
            elif "啟動核心協調器" in clean_line:
                shared_stats['status'] = "啟動服務..."
            elif "前端建置成功" in clean_line:
                shared_stats['status'] = "服務已啟動，生成連結..."

            # 尋找最終的 URL
            match = url_pattern.search(clean_line)
            if match and not final_url_found:
                final_url_found = True
                internal_url = match.group(1)
                port = internal_url.split(':')[-1]
                log_manager.log("SUCCESS", f"內部服務 URL 已獲取: {internal_url}")
                shared_stats['status'] = "正在生成 Colab 代理連結..."

                # 使用 Colab API 獲取外部代理 URL
                js_script = f"google.colab.kernel.proxyPort({port}, {{'cache': false}})"
                proxy_url = colab_output.eval_js(f"(async () => await {js_script})()")
                shared_stats['proxy_url'] = proxy_url
                shared_stats['status'] = "✅ 應用程式已就緒"
                log_manager.log("SUCCESS", f"成功獲取代理連結: {proxy_url}")

        runner_proc.wait() # 等待 runner 程序結束

    except Exception as e:
        log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}")
        shared_stats['status'] = f"❌ 啟動失敗: {e}"
    finally:
        if runner_proc and runner_proc.poll() is None:
            runner_proc.terminate() # 確保子程序被關閉
        # 等待顯示執行緒結束，確保最後的畫面被印出
        time.sleep(UI_REFRESH_SECONDS * 2)
        display_manager.stop()
        # 在最終停止後再印一次，確保顯示最新狀態
        clear_output(wait=True)
        print("\n".join(display_manager._build_output_buffer()))
        print("\n--- 🏁 啟動程序結束 ---")


if __name__ == "__main__":
    project_path = download_repository()
    if project_path:
        clear_output(wait=True)
        # 不再需要 install_system_deps()，因為 runner 會處理
        launch_application(project_path_str=project_path)
    else:
        print("\n" + "="*60)
        print("❌ 錯誤：專案準備失敗，無法繼續啟動程序。")
        print("="*60)
