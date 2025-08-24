# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器 (v13) 🐺
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "689" #@param {type:"string"}
#@markdown **專案資料夾名稱 (PROJECT_FOLDER_NAME)**
PROJECT_FOLDER_NAME = "wolf_project" #@param {type:"string"}
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
LOG_DISPLAY_LINES = 15 #@param {type:"integer"}
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
# 版本: 13.0 (架構: 功能整合)
# 日期: 2025-08-25T05:15:00+08:00
#
# 本次變更重點:
# 1. **功能恢復**: 將 v10 版本中的即時日誌、效能監控、HTML報告等 UI 功能，
#    與 v12 的穩定架構進行整合。
# 2. **日誌系統**: 引入了更完善的日誌管理器，取代了原有的 print() 呼叫。
# 3. **配置更新**: 將預設分支更新為 "689"。
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
import threading
import re
from pathlib import Path
import traceback
from datetime import datetime
from collections import deque
import html

# --- 模擬 Colab 環境 ---
try:
    from google.colab import output as colab_output
    from IPython.display import display, HTML, clear_output as ipy_clear_output
    import pytz
    IN_COLAB = True
except ImportError:
    class MockColab:
        def eval_js(self, *args, **kwargs): return ""
        def clear_output(self, wait=False): print("\n--- 清除輸出 ---\n")
        def display(self, *args, **kwargs): pass
        def HTML(self, *args, **kwargs): pass
    colab_output = MockColab().eval_js
    ipy_clear_output = MockColab().clear_output
    display = MockColab().display
    HTML = MockColab().HTML
    # Mock pytz if not available
    class MockPytz:
        def timezone(self, tz_str):
            from datetime import timezone, timedelta
            return timezone(timedelta(hours=8)) # Assume UTC+8 for tests
    pytz = MockPytz()
    IN_COLAB = False
    print("警告：未在 Colab 環境中執行，將使用模擬的 display 功能。")

# ==============================================================================
# PART 1: GIT 下載器功能
# ==============================================================================
def download_repository(log_manager):
    project_path = Path(PROJECT_FOLDER_NAME)
    log_manager.log("INFO", f"準備下載專案至 '{PROJECT_FOLDER_NAME}'...")
    if FORCE_REPO_REFRESH and project_path.exists():
        log_manager.log("WARN", f"正在強制刪除舊資料夾: {project_path}")
        shutil.rmtree(project_path)
    if project_path.exists():
        log_manager.log("SUCCESS", f"✅ 專案資料夾 '{project_path}' 已存在，跳過下載。")
        return str(project_path.resolve())
    log_manager.log("INFO", f"🚀 開始從 Git 下載...")
    try:
        subprocess.run(
            ["git", "clone", "--branch", TARGET_BRANCH_OR_TAG, "--depth", "1", REPOSITORY_URL, str(project_path)],
            check=True, capture_output=True, text=True,
        )
        log_manager.log("SUCCESS", "✅ 專案程式碼下載成功！")
        return str(project_path.resolve())
    except subprocess.CalledProcessError as e:
        log_manager.log("CRITICAL", f"❌ Git clone 失敗: {e.stderr}")
        return None

# ==============================================================================
# PART 2: UI 與通道管理器
# ==============================================================================
TUNNEL_ORDER = ["Cloudflare", "Localtunnel", "Colab"]
ANSI_COLORS = {"SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m", "RESET": "\033[0m", "INFO": "\033[34m", "RUNNER": "\033[90m"}
def colorize(text, level): return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS.get('RESET', '')}"

class DisplayManager:
    """ 負責管理 Colab 儲存格的純文字 UI 輸出，並整合日誌記錄。"""
    def __init__(self, shared_state):
        self._state = shared_state
        self._log_deque = deque(maxlen=LOG_DISPLAY_LINES)
        self._full_history = []

    def log(self, level, message):
        now = datetime.now(pytz.timezone(TIMEZONE))
        for line in str(message).split('\n'):
            log_entry = {"timestamp": now, "level": level.upper(), "message": line}
            self._log_deque.append(log_entry)
            self._full_history.append(f"[{now.isoformat()}] [{level.upper():^8}] {line}")

    def get_full_log_history(self):
        return self._full_history

    def print_ui(self):
        if ENABLE_CLEAR_OUTPUT: ipy_clear_output(wait=True)

        output = ["🚀 善狼一鍵啟動器 v13 🚀", ""]

        # 顯示日誌
        for log_item in self._log_deque:
            ts = log_item['timestamp'].strftime('%H:%M:%S')
            level, msg = log_item['level'], log_item['message']
            output.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {msg}")

        # 顯示狀態行
        try:
            import psutil
            cpu, ram = f"{psutil.cpu_percent():5.1f}%", f"{psutil.virtual_memory().percent:5.1f}%"
        except ImportError:
            cpu, ram = " N/A ", " N/A "
        elapsed = time.monotonic() - self._state.get("start_time_monotonic", time.monotonic())
        mins, secs = divmod(elapsed, 60)
        status = self._state.get("status", "初始化...")
        output.append("")
        output.append(f"⏱️ {int(mins):02d}分{int(secs):02d}秒 | 💻 CPU: {cpu} | 🧠 RAM: {ram} | 🔥 狀態: {status}")

        # 顯示通道
        output.append("\n🔗 公開存取網址:")
        urls = self._state.get("urls", {})
        if not urls and status not in ["✅ 應用程式已就緒", "❌ 啟動失敗"]:
             output.append("  - (正在產生...)")
        else:
            for name in TUNNEL_ORDER:
                url = urls.get(name)
                if url:
                    if "錯誤" in str(url):
                        error_msg = f"\033[91m{url}\033[0m" if IN_COLAB else f"{url} (錯誤)"
                        output.append(f"  - {name+':':<15} {error_msg}")
                    else:
                        output.append(f"  - {name+':':<15} {url}")
                elif self._state.get("all_tunnels_done"):
                    output.append(f"  - {name+':':<15} (啟動失敗)")

        print("\n".join(output), flush=True)

class TunnelManager:
    def __init__(self, port, shared_state, project_path, log_manager, timeout=20):
        self.port = port
        self._state = shared_state
        self._project_path = Path(project_path)
        self._log = log_manager.log
        self._timeout = timeout
        self.threads = []
        self.processes = []

    def _run_tunnel_service(self, name, command, pattern, cwd):
        self._log("INFO", f"-> {name} 競速開始...")
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', cwd=cwd)
            self.processes.append(proc)
            for line in iter(proc.stdout.readline, ''):
                self._log("RUNNER", f"[{name}] {line.strip()}")
                match = re.search(pattern, line)
                if match:
                    url = match.group(1)
                    self._state["urls"][name] = url
                    self._log("SUCCESS", f"✅ {name} 成功: {url}")
                    return
            proc.wait(timeout=self._timeout)
            if self._state["urls"].get(name) is None:
                self._state["urls"][name] = f"錯誤：程序已結束 (Code: {proc.returncode})"
        except Exception as e:
            self._log("ERROR", f"❌ {name} 執行時發生錯誤: {e}")
            self._state["urls"][name] = f"錯誤：執行失敗"

    def _get_cloudflare_url(self):
        # ... (implementation is the same as v12, just uses self._log) ...
        name = "Cloudflare"
        try:
            cf_path = self._project_path / 'cloudflared'
            if not cf_path.exists():
                self._log("INFO", "下載 Cloudflared...")
                subprocess.run(['wget', '-q', 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64', '-O', str(cf_path)], check=True)
                subprocess.run(['chmod', '+x', str(cf_path)], check=True)
            command = [str(cf_path), 'tunnel', '--url', f'http://127.0.0.1:{self.port}']
            self._run_tunnel_service(name, command, r'(https?://\S+\.trycloudflare\.com)', self._project_path)
        except Exception as e:
            self._log("ERROR", f"❌ Cloudflared 前置作業失敗: {e}")
            self._state["urls"][name] = f"錯誤：前置作業失敗"


    def _get_localtunnel_url(self):
        # ... (implementation is the same as v12, just uses self._log) ...
        name = "Localtunnel"
        try:
            if shutil.which('lt') is None:
                self._log("INFO", "安裝 localtunnel...")
                subprocess.run(['npm', 'install', '-g', 'localtunnel'], check=True, capture_output=True)
            command = ['lt', '--port', str(self.port), '--bypass-tunnel-reminder']
            self._run_tunnel_service(name, command, r'(https?://\S+\.loca\.lt)', self._project_path)
        except Exception as e:
            self._log("ERROR", f"❌ Localtunnel 前置作業失敗: {e}")
            self._state["urls"][name] = f"錯誤：前置作業失敗"


    def _get_colab_url(self):
        name = "Colab"
        self._log("INFO", f"-> {name} 競速開始...")
        try:
            if IN_COLAB:
                result = colab_output.eval_js(f"google.colab.kernel.proxyPort({self.port}, {{'cache': false}})", timeout_sec=self._timeout)
                if isinstance(result, str) and result.startswith('http'):
                    self._state["urls"][name] = result
                    self._log("SUCCESS", f"✅ {name} 成功: {result}")
                else:
                    self._state["urls"][name] = "錯誤：未返回有效網址"
            else:
                time.sleep(1); self._state["urls"][name] = "http://mock-colab-url.dev"
        except Exception as e:
            self._log("ERROR", f"❌ {name} 執行時發生錯誤: {e}")
            self._state["urls"][name] = f"錯誤：執行失敗"

    def start_tunnels(self):
        self._state["urls"] = {}
        racers = [
            threading.Thread(target=self._get_cloudflare_url),
            threading.Thread(target=self._get_localtunnel_url),
            threading.Thread(target=self._get_colab_url),
        ]
        for r in racers: r.start(); self.threads.append(r)

    def stop_tunnels(self):
        self._log("INFO", "正在關閉所有隧道服務...")
        for p in self.processes:
            if p.poll() is None: p.terminate()
        for t in self.threads: t.join(timeout=1)

def create_log_viewer_html(log_manager):
    log_history = log_manager.get_full_log_history()
    log_to_copy = log_history[-LOG_COPY_MAX_LINES:]
    num_logs = len(log_to_copy)
    unique_id = f"log-area-{int(time.time() * 1000)}"
    log_content_string = "\n".join(log_to_copy)
    escaped_log = html.escape(log_content_string)

    textarea_html = f'<textarea id="{unique_id}" style="position:absolute; left: -9999px; top: -9999px;" readonly>{escaped_log}</textarea>'
    onclick_js = f'''(async () => {{ const ta = document.getElementById('{unique_id}'); if (!ta) return; await navigator.clipboard.writeText(ta.value); this.innerText = "✅ 已複製!"; setTimeout(() => {{ this.innerText = "📋 複製這 {num_logs} 條日誌"; }}, 2000); }})()'''.replace("\n", " ").strip()
    button_html = f'<button onclick="{html.escape(onclick_js)}" style="padding: 6px 12px; margin: 12px 0; cursor: pointer;">📋 複製這 {num_logs} 條日誌</button>'

    return f'''<details style="margin-top: 15px; border: 1px solid #e0e0e0; padding: 12px;"><summary style="cursor: pointer; font-weight: bold;">點此展開/收合最近 {num_logs} 條詳細日誌</summary><div>{textarea_html}{button_html}<pre style="background-color: #f5f5f5; padding: 10px; border: 1px solid #ddd;"><code>{escaped_log}</code></pre>{button_html}</div></details>'''

# ==============================================================================
# PART 3: 主啟動器邏輯
# ==============================================================================
def launch_application(project_path_str: str, deps_path_str: str, log_manager: DisplayManager):
    project_path = Path(project_path_str)
    shared_state = log_manager._state
    server_proc, tunnel_manager = None, None
    try:
        shared_state["status"] = "啟動後端服務中..."
        log_manager.print_ui()

        server_command = [sys.executable, "run.py", "--deps-path", deps_path_str]
        server_proc = subprocess.Popen(server_command, cwd=project_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')

        app_port = None
        for line in iter(server_proc.stdout.readline, ''):
            line = line.strip()
            log_manager.log("RUNNER", line)
            if line.startswith("APP_PORT:"):
                app_port = int(line.split(":")[1].strip())
                shared_state["status"] = f"服務運行中 (埠號: {app_port})"
                break

        if app_port is None: raise RuntimeError("無法從 run.py 獲取應用程式埠號。")

        tunnel_manager = TunnelManager(app_port, shared_state, project_path, log_manager)
        tunnel_manager.start_tunnels()
        shared_state["status"] = "正在建立網路通道..."

        while len(shared_state["urls"]) < len(TUNNEL_ORDER):
            if server_proc.poll() is not None:
                shared_state["status"] = f"❌ 服務已停止 (返回碼: {server_proc.poll()})"
                break
            log_manager.print_ui()
            time.sleep(UI_REFRESH_SECONDS)

        shared_state["all_tunnels_done"] = True
        shared_state["status"] = "✅ 應用程式已就緒"
        log_manager.print_ui()

        log_manager.log("INFO", "主服務正在背景運行，可關閉此儲存格以終止所有服務。")
        server_proc.wait()

    except KeyboardInterrupt:
        log_manager.log("WARN", "收到使用者中斷指令，正在優雅地關閉所有服務...")
    except Exception as e:
        log_manager.log("CRITICAL", f"啟動器發生致命錯誤: {e}")
        traceback.print_exc()
    finally:
        shared_state["status"] = "關閉中..."
        if tunnel_manager: tunnel_manager.stop_tunnels()
        if server_proc and server_proc.poll() is None:
            log_manager.log("INFO", "正在終止後端伺服器...")
            server_proc.terminate()
            server_proc.wait(timeout=5)
        log_manager.print_ui()
        display(HTML(create_log_viewer_html(log_manager)))
        log_manager.log("INFO", "所有服務已關閉。")

# ==============================================================================
# FINAL EXECUTION BLOCK
# ==============================================================================
if __name__ == '__main__':
    shared_state_main = {
        "start_time_monotonic": time.monotonic(),
        "status": "初始化...",
        "urls": {},
        "all_tunnels_done": False
    }
    log_manager_main = DisplayManager(shared_state_main)

    try:
        project_path = download_repository(log_manager_main)
        if not project_path: raise RuntimeError("專案下載失敗")

        root_dir = Path(os.getcwd())
        deps_archive_path = root_dir / "dependencies.tar.gz"

        if not deps_archive_path.exists():
            log_manager_main.log("WARN", f"依賴壓縮檔不存在，正在嘗試自動建立...")
            bake_script_path = Path(project_path) / "scripts" / "bake_dependencies.sh"
            if not bake_script_path.exists(): raise FileNotFoundError(f"找不到烘烤腳本 {bake_script_path}")

            subprocess.run(["bash", str(bake_script_path)], cwd=project_path, check=True)
            generated_deps = Path(project_path) / "dependencies.tar.gz"
            if not generated_deps.exists(): raise FileNotFoundError("烘烤腳本未成功產生依賴包")

            shutil.move(str(generated_deps), str(root_dir))
            log_manager_main.log("SUCCESS", f"✅ 成功建立並移動依賴包至 '{deps_archive_path}'")

        launch_application(project_path, str(deps_archive_path), log_manager_main)

    except Exception as e:
        log_manager_main.log("CRITICAL", f"發生無法處理的致命錯誤: {e}")
        traceback.print_exc()
    finally:
        log_manager_main.log("INFO", "--- 執行結束 ---")
        log_manager_main.print_ui()
        display(HTML(create_log_viewer_html(log_manager_main)))
