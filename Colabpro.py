# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器 (v8.0 - 高可用性代理) 🐺
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "630" #@param {type:"string"}
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
UI_REFRESH_SECONDS = 0.5 #@param {type:"number"}
#@markdown **日誌顯示行數**
LOG_DISPLAY_LINES = 20 #@param {type:"integer"}
#@markdown **最大日誌複製數量**
LOG_COPY_MAX_LINES = 2000 #@param {type:"integer"}
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
# 版本: 8.1 (架構: 高可用性代理)
# 日期: 2025-08-23T15:40:36+08:00
#
# 🔴 **禁止直接執行**: 本檔案 (Colabpro.py) 被設計為一個程式庫 (library)，
#    由 Colab Notebook 環境導入並呼叫。請勿透過 `python Colabpro.py` 直接執行。
#
# 🟡 **限制修改範圍**:
#    - **允許修改**: 僅限於核心啟動邏輯，即 `launch_application` 或類似功能的內部實作。
#    - **禁止修改**: 絕對不要更動任何與使用者介面 (ipywidgets)、參數輸入、
#      UI 顯示設計，以及最終 HTML 報告產生與複製按鈕相關的程式碼。
#
# 本次變更根據「Colab Pro 高可用性代理策略技術報告」實作了併發競速代理
# 獲取策略。現在系統會同時嘗試啟動 Colab、localtunnel 和 Cloudflare
# Tunnel，並將所有成功的網址都顯示出來，以應對 Colab 環境的不穩定。
# 同時，預設分支已更新至 630。
#
# ======================================================================================

# ==============================================================================
# SECTION 0: 環境準備與核心依賴導入
# ==============================================================================
import sys
import os
import shutil
import subprocess
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
    if 'google.colab' in sys.modules: return
    print("[MOCK] 偵測到測試模式，正在注入虛假的 google.colab 模組...")
    class FakeColabOutput:
        def eval_js(self, *args, **kwargs): return None
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
        try:
            shutil.rmtree(project_path)
            log_manager.log("SUCCESS", "✅ 舊資料夾已成功刪除。")
        except OSError as e:
            log_manager.log("ERROR", f"❌ 刪除舊資料夾失敗: {e}。請手動刪除後再試。")
            return None
    if project_path.exists():
        log_manager.log("SUCCESS", f"✅ 專案資料夾 '{project_path}' 已存在，將跳過下載。")
        return str(project_path.resolve())
    log_manager.log("INFO", f"🚀 開始從 Git 下載...")
    try:
        subprocess.run(["git", "clone", "--branch", TARGET_BRANCH_OR_TAG, "--depth", "1", REPOSITORY_URL, str(project_path)], check=True, capture_output=True, text=True)
        log_manager.log("SUCCESS", "✅ 專案程式碼下載成功！")
        return str(project_path.resolve())
    except subprocess.CalledProcessError as e:
        log_manager.log("CRITICAL", f"❌ Git clone 失敗: {e.stderr}")
        return None

# ==============================================================================
# PART 2: UI 與日誌管理器
# ==============================================================================
ANSI_COLORS = {"SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m", "RESET": "\033[0m", "INFO": "\033[34m", "DEBUG": "\033[90m", "RUNNER": "\033[90m"}
def colorize(text, level): return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS.get('RESET', '')}"

class DisplayManager:
    def __init__(self, stats_dict, refresh_rate):
        self._stats = stats_dict; self._refresh_rate = refresh_rate
        self._stop_event = threading.Event(); self._thread = threading.Thread(target=self._run, daemon=True)
        self._log_deque = deque(maxlen=LOG_DISPLAY_LINES)
        self._full_history = []

    def log(self, level, message):
        now = datetime.now(pytz.timezone(TIMEZONE))
        display_message = str(message).split('\n')[0]
        log_entry = {"timestamp": now, "level": level.upper(), "message": display_message}
        self._log_deque.append(log_entry)
        self._full_history.append(f"[{now.isoformat()}] [{level.upper():^8}] {message}")

    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["🐺 善狼一鍵啟動器 (v8.0 - 高可用性代理) 🐺", ""]
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

        # **修改**: 顯示所有可用的代理網址
        proxy_urls = self._stats.get('proxy_urls', [])
        if not proxy_urls:
            output_buffer.append("⏳ 正在啟動服務並生成連結...")
        else:
            output_buffer.append("✅ 應用程式連結 (點擊開啟):")
            for name, url in proxy_urls:
                output_buffer.append(f"  - {name+':':<20} {url}")
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
# PART 3: 高可用性代理獲取器 (High-Availability Proxy Getter)
# ==============================================================================
class HAProxyGetter:
    def __init__(self, port, log_manager):
        self.port = port
        self.log = log_manager.log
        self.results = queue.Queue()
        self.processes = []

    def _install_tool(self, cmd, name, check_cmd):
        try:
            # 檢查工具是否已安裝
            if subprocess.run(check_cmd, shell=True, capture_output=True).returncode == 0:
                self.log("INFO", f"✅ 工具 '{name}' 已安裝。")
                return True
            self.log("INFO", f"正在安裝 {name}...")
            proc = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
            self.log("SUCCESS", f"✅ {name} 安裝成功。")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.log("ERROR", f"❌ {name} 安裝失敗: {e.stderr if hasattr(e, 'stderr') else e}")
            return False

    def _get_colab_url(self):
        try:
            js_get_url_script = f"google.colab.kernel.proxyPort({self.port}, {{'cache': false}})"
            url = colab_output.eval_js(js_get_url_script)
            if url and "googleusercontent.com" in url:
                self.results.put(("Colab 官方代理", url))
                self.log("SUCCESS", f"✅ 成功獲取 Colab 代理: {url}")
            else:
                self.log("WARN", "Colab 代理返回了無效的 URL。")
        except Exception as e:
            self.log("WARN", f"獲取 Colab 代理失敗: {e}")

    def _get_cloudflare_url(self):
        if not self._install_tool(
            "wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared",
            "Cloudflared",
            "command -v cloudflared"
        ): return

        cmd = f"cloudflared tunnel --url http://127.0.0.1:{self.port}"
        proc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(proc)
        for line in iter(proc.stderr.readline, ''):
            if "trycloudflare.com" in line:
                url = re.search(r'(https?://\S+\.trycloudflare\.com)', line)
                if url:
                    self.results.put(("Cloudflare Tunnel", url.group(1)))
                    self.log("SUCCESS", f"✅ 成功獲取 Cloudflare 代理: {url.group(1)}")
                    # 找到後即可，但讓它繼續運行
                    return

    def _get_localtunnel_url(self):
        if not self._install_tool("npm install -g localtunnel", "Localtunnel", "command -v lt"): return
        cmd = f"lt --port {self.port}"
        proc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append(proc)
        for line in iter(proc.stdout.readline, ''):
            if "your url is:" in line:
                url = line.split()[-1]
                self.results.put(("Localtunnel", url))
                self.log("SUCCESS", f"✅ 成功獲取 Localtunnel 代理: {url}")
                return

    def get_urls(self, timeout=15):
        threads = [
            threading.Thread(target=self._get_colab_url),
            threading.Thread(target=self._get_cloudflare_url),
            threading.Thread(target=self._get_localtunnel_url),
        ]
        for t in threads:
            t.start()

        start_time = time.time()
        while time.time() - start_time < timeout and any(t.is_alive() for t in threads):
            for t in threads:
                t.join(0.1)

        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate() # 清理仍在運行的隧道進程

        urls = []
        while not self.results.empty():
            urls.append(self.results.get())
        return sorted(urls, key=lambda x: x[0])


# ==============================================================================
# PART 4: 主啟動器邏輯
# ==============================================================================
def launch_application(project_path_str: str, log_manager: DisplayManager):
    project_path = Path(project_path_str)
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "啟動中...", "proxy_urls": []}
    display_manager = log_manager
    display_manager._stats = shared_stats
    display_manager.start()

    server_proc = None
    try:
        shared_stats['status'] = "呼叫中央啟動腳本..."
        launch_script_path = project_path / "run_app.py"
        if not launch_script_path.exists():
            raise FileNotFoundError(f"找不到中央啟動腳本: {launch_script_path}")

        command = [sys.executable, str(launch_script_path)]
        server_proc = subprocess.Popen(command, cwd=project_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', bufsize=1)
        display_manager.log("SUCCESS", f"✅ 中央啟動腳本已執行 (PID: {server_proc.pid})。")

        app_port = None
        for line in iter(server_proc.stdout.readline, ''):
            if not line: break
            line = line.strip()
            display_manager.log("RUNNER", line)
            if line.startswith("APP_URL:"):
                url = line.split("APP_URL:")[1].strip()
                app_port = int(url.split(":")[-1])
                display_manager.log("SUCCESS", f"偵測到應用程式埠號: {app_port}")
                break # 找到埠號後就跳出

        if app_port:
            shared_stats['status'] = "併發獲取代理網址中..."
            proxy_getter = HAProxyGetter(app_port, display_manager)
            urls = proxy_getter.get_urls()
            shared_stats['proxy_urls'] = urls
            if urls:
                shared_stats['status'] = "✅ 應用程式已就緒"
            else:
                shared_stats['status'] = "❌ 獲取代理網址失敗"
                display_manager.log("CRITICAL", "所有代理方案均失敗，請檢查網路連線或 Colab 環境。")
        else:
            raise RuntimeError("無法從啟動腳本中偵測到應用程式埠號。")

        # 讓主應用程式繼續在背景運行
        display_manager.log("INFO", "主服務正在背景運行，此 Colab 儲存格將保持活躍狀態。")
        server_proc.wait() # 等待主服務結束 (例如被手動停止)

    except KeyboardInterrupt:
        display_manager.log("WARN", "收到使用者中斷指令，正在優雅地關閉所有服務...")
        shared_stats['status'] = "使用者手動關閉中..."
    except Exception as e:
        display_manager.log("CRITICAL", f"❌ 啟動器發生致命錯誤: {e}")
        traceback.print_exc()
        shared_stats['status'] = f"❌ 致命錯誤"
    finally:
        if server_proc and server_proc.poll() is None:
            display_manager.log("INFO", f"正在終止中央啟動腳本 (PID: {server_proc.pid})...")
            server_proc.terminate()
        display_manager.stop()
        final_html = create_log_viewer_html(display_manager)
        display(HTML(final_html))
        print("\n".join(display_manager._build_output_buffer()))
        print("\n--- 執行結束 ---")


def create_log_viewer_html(display_manager: DisplayManager) -> str:
    try:
        log_history = display_manager._full_history
        log_to_copy = log_history[-LOG_COPY_MAX_LINES:]
        num_logs = len(log_to_copy)
        unique_id = f"log-area-{int(time.time() * 1000)}"
        log_content_string = "\n".join(log_to_copy)
        escaped_log_for_display = html.escape(log_content_string)
        textarea_html = f'<textarea id="{unique_id}" style="position:absolute; left: -9999px; top: -9999px;" readonly>{escaped_log_for_display}</textarea>'
        onclick_js = f'''(async () => {{ const ta = document.getElementById('{unique_id}'); if (!ta) return; await navigator.clipboard.writeText(ta.value); this.innerText = "✅ 已複製!"; setTimeout(() => {{ this.innerText = "📋 複製這 {num_logs} 條日誌"; }}, 2000); }})()'''.replace("\n", " ").strip()
        button_html = f'<button onclick="{html.escape(onclick_js)}" style="padding: 6px 12px; margin: 12px 0; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #f9f9f9;">📋 複製這 {num_logs} 條日誌</button>'
        return f'''<details style="margin-top: 15px; margin-bottom: 15px; border: 1px solid #e0e0e0; padding: 12px; border-radius: 8px; background-color: #fafafa;"><summary style="cursor: pointer; font-weight: bold; color: #333;">點此展開/收合最近 {num_logs} 條詳細日誌</summary><div style="margin-top: 12px;">{textarea_html}{button_html}<pre style="background-color: #fff; padding: 12px; border: 1px solid #e0e0e0; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; font-size: 13px; color: #444;"><code>{escaped_log_for_display}</code></pre>{button_html}</div></details>'''
    except Exception as e:
        return f"<p>❌ 產生最終日誌報告時發生錯誤: {html.escape(str(e))}</p>"

if __name__ == "__main__":
    print("--- Colabpro.py 本地測試模式 ---")
    display_manager = DisplayManager(stats_dict={}, refresh_rate=UI_REFRESH_SECONDS)
    try:
        os.environ['IN_TEST_MODE'] = '1'
        _setup_colab_mocks()
        project_path = download_repository(log_manager=display_manager)
        if project_path:
            launch_application(project_path_str=project_path, log_manager=display_manager)
        else:
            display_manager.log("CRITICAL", "專案準備失敗，無法繼續啟動程序。")
    except Exception as e:
        print(f"\n--- 致命錯誤 ---")
        traceback.print_exc()
    finally:
        print("\n--- 本地測試結束 ---")
