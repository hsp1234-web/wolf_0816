# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器 (v7.0 - 極速啟動) 🐺
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "602" #@param {type:"string"}
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
# PART 2: UI 與日誌管理器 (LogManager 已被移除，由新的日誌系統取代)
# ==============================================================================
# TODO: 建立一個新的、基於 Huey 佇列的 LogManager，它將日誌任務發送到佇列
# 而不是直接寫入資料庫。
# 目前為了簡化，我們先在 launch_application 中直接使用 print。

ANSI_COLORS = {"SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m", "RESET": "\033[0m", "INFO": "\033[34m", "DEBUG": "\033[90m", "RUNNER": "\033[90m"}
def colorize(text, level): return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS.get('RESET', '')}"

class DisplayManager:
    def __init__(self, stats_dict, refresh_rate):
        self._stats = stats_dict; self._refresh_rate = refresh_rate
        self._stop_event = threading.Event(); self._thread = threading.Thread(target=self._run, daemon=True)
        self._log_deque = deque(maxlen=LOG_DISPLAY_LINES)
        self._full_history = [] # 新增：儲存所有日誌

    def log(self, level, message):
        now = datetime.now(pytz.timezone(TIMEZONE))
        display_message = str(message).split('\n')[0]
        log_entry = {"timestamp": now, "level": level.upper(), "message": display_message}
        self._log_deque.append(log_entry)
        self._full_history.append(f"[{now.isoformat()}] [{level.upper():^8}] {message}") # 儲存完整格式的日誌

    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["🐺 善狼一鍵啟動器 (v7.0 - 極速啟動) 🐺", ""]
        for log in self._log_deque:
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
# PART 3: 新版啟動器邏輯 (架構 v3.0 - 統一啟動腳本)
# ==============================================================================
def launch_application(project_path_str: str, log_manager: DisplayManager):
    """
    使用統一的 `run_app.py` 腳本來啟動應用程式。
    此函式現在只負責協調，將所有複雜的設定工作都交給 `run_app.py`。
    """
    project_path = Path(project_path_str)
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "啟動中...", "proxy_url": None}

    # 注意：新的 DisplayManager 不再需要 log_manager，它只處理顯示
    # 我們直接將 DisplayManager 實例作為日誌管理器傳遞
    display_manager = log_manager
    display_manager._stats = shared_stats # 連接到共享狀態
    display_manager.start()

    server_proc = None
    app_port = None

    try:
        shared_stats['status'] = "呼叫中央啟動腳本..."
        launch_script_path = project_path / "run_app.py"
        if not launch_script_path.exists():
            raise FileNotFoundError(f"找不到中央啟動腳本: {launch_script_path}")

        # 使用 Popen 啟動 run_app.py，這樣我們可以即時讀取其輸出
        command = [sys.executable, str(launch_script_path)]
        server_proc = subprocess.Popen(
            command,
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1
        )
        display_manager.log("SUCCESS", f"✅ 中央啟動腳本已執行 (PID: {server_proc.pid})。")

        # 監聽來自 run_app.py 的輸出
        for line in iter(server_proc.stdout.readline, ''):
            if not line:
                break

            line = line.strip()
            display_manager.log("RUNNER", line) # 將所有日誌轉發到 UI

            # 從輸出中解析 APP_URL，以獲取埠號
            if line.startswith("APP_URL:"):
                url = line.split("APP_URL:")[1].strip()
                app_port = int(url.split(":")[-1])
                display_manager.log("SUCCESS", f"偵測到應用程式埠號: {app_port}")

                # 開始非同步獲取 Colab 代理 URL
                threading.Thread(target=_get_colab_proxy_url, args=(app_port, shared_stats, display_manager), daemon=True).start()

        # 等待子程序結束
        server_proc.wait()
        if server_proc.returncode != 0:
             raise RuntimeError(f"中央啟動腳本執行失敗，返回碼: {server_proc.returncode}")

    except KeyboardInterrupt:
        display_manager.log("WARN", "收到使用者中斷指令，正在優雅地關閉所有服務...")
        shared_stats['status'] = "使用者手動關閉中..."
    except Exception as e:
        # 在 DisplayManager 中只記錄簡潔的錯誤訊息
        display_manager.log("CRITICAL", f"❌ 啟動器發生致命錯誤: {e}")
        # 在標準錯誤輸出中印出完整的追蹤訊息以供除錯
        traceback.print_exc()
        shared_stats['status'] = f"❌ 致命錯誤: {e}"
    finally:
        if server_proc and server_proc.poll() is None:
            display_manager.log("INFO", f"正在終止中央啟動腳本 (PID: {server_proc.pid})...")
            server_proc.terminate()

        display_manager.stop()
        # 恢復：在最後顯示可複製的完整日誌報告
        final_html = create_log_viewer_html(display_manager)
        display(HTML(final_html))
        print("\n".join(display_manager._build_output_buffer()))
        print("\n--- 執行結束 ---")

def _get_colab_proxy_url(port: int, shared_stats: dict, display_manager: DisplayManager):
    """在背景執行緒中嘗試獲取 Colab 的代理 URL。"""
    for attempt in range(20):
        shared_stats['status'] = f"正在嘗試取得代理連結... (第 {attempt + 1}/20 次)"
        try:
            # Colab 的 JS 執行可能不穩定，將其放在 try-except 中
            proxy_url = colab_output.eval_js(f'''(async () => {{
                const url = await google.colab.kernel.proxyPort({port}, {{'cache': false}});
                return url;
            }})()''', timeout_sec=15)

            if proxy_url and isinstance(proxy_url, str) and proxy_url.startswith('http'):
                shared_stats['proxy_url'] = proxy_url
                shared_stats['status'] = "✅ 應用程式已就緒"
                display_manager.log("SUCCESS", f"成功取得代理連結: {proxy_url}")
                return # 成功獲取，退出執行緒
            else:
                display_manager.log("WARN", f"收到無效的代理回傳值: {str(proxy_url)[:100]}...")
        except Exception as e:
            display_manager.log("WARN", f"獲取代理連結時發生 JS 錯誤: {e}")

        time.sleep(2) # 等待一段時間再重試

    display_manager.log("ERROR", "❌ 無法取得 Colab 代理連結。請檢查瀏覽器主控台是否有錯誤。")
    shared_stats['status'] = "❌ 獲取連結失敗"

def create_log_viewer_html(display_manager: DisplayManager) -> str:
    """
    產生一個包含日誌內容的、功能獨立的 HTML 檢視器。
    """
    try:
        # 從 DisplayManager 獲取完整的日誌歷史
        log_history = display_manager._full_history
        # 限制複製的日誌行數
        log_to_copy = log_history[-LOG_COPY_MAX_LINES:]
        num_logs = len(log_to_copy)

        unique_id = f"log-area-{int(time.time() * 1000)}"

        log_content_string = "\n".join(log_to_copy)
        escaped_log_for_display = html.escape(log_content_string)

        textarea_html = f'<textarea id="{unique_id}" style="position:absolute; left: -9999px; top: -9999px;" readonly>{escaped_log_for_display}</textarea>'

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

        button_html = f'<button onclick="{html.escape(onclick_js)}" style="padding: 6px 12px; margin: 12px 0; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #f9f9f9;">📋 複製這 {num_logs} 條日誌</button>'

        return f'''
        <details style="margin-top: 15px; margin-bottom: 15px; border: 1px solid #e0e0e0; padding: 12px; border-radius: 8px; background-color: #fafafa;">
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
        return f"<p>❌ 產生最終日誌報告時發生錯誤: {html.escape(str(e))}</p>"

if __name__ == "__main__":
    # 此區塊僅用於在本地對 Colabpro.py 進行基本測試。
    # 它模擬了 Colab Notebook 儲存格的執行流程。
    print("--- Colabpro.py 本地測試模式 ---")

    # 1. 建立一個 DisplayManager 實例來捕捉日誌
    # 在真實的 Colab 環境中，這是由 Notebook 提供的。
    # 我們傳入一個空的 stats_dict，因為它會被 launch_application 覆寫。
    display_manager = DisplayManager(stats_dict={}, refresh_rate=UI_REFRESH_SECONDS)

    try:
        # 2. 設定環境變數以啟用模擬模式
        os.environ['IN_TEST_MODE'] = '1'
        _setup_colab_mocks() # 手動呼叫 mock 安裝

        # 3. 執行下載（在測試模式下，這只會確認路徑）
        # 注意：我們現在傳遞 DisplayManager 實例作為日誌管理器
        project_path = download_repository(log_manager=display_manager)

        # 4. 執行主啟動邏輯
        if project_path:
            launch_application(project_path_str=project_path, log_manager=display_manager)
        else:
            display_manager.log("CRITICAL", "專案準備失敗，無法繼續啟動程序。")

    except Exception as e:
        # 統一處理所有來自本地測試主流程的錯誤
        print(f"\n--- 致命錯誤 ---")
        traceback.print_exc()
    finally:
        print("\n--- 本地測試結束 ---")
