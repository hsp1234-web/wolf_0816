# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器 (v18) 🐺
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "757-A" #@param {type:"string"}
#@markdown **專案資料夾名稱 (PROJECT_FOLDER_NAME)**
PROJECT_FOLDER_NAME = "wolf_project" #@param {type:"string"}
#@markdown **強制刷新後端程式碼 (FORCE_REPO_REFRESH)**
#@markdown > **如果勾選，每次執行都會先刪除舊的專案資料夾，再重新下載。**
FORCE_REPO_REFRESH = True #@param {type:"boolean"}
#@markdown > **v16 架構更新：舊的依賴包 (`dependencies.tar.gz`) 已被廢棄，此選項不再有效。 [待廢棄]**
FORCE_DEPS_REFRESH = False #@param {type:"boolean"}
#@markdown **輕量測試模式 (LIGHT_MODE) [待廢棄]**
#@markdown > **勾選後，將以輕量模式啟動，使用 `tiny.en` 模型並安裝較少的依賴，適合快速測試。新架構不再使用此選項。**
LIGHT_MODE = True #@param {type:"boolean"}
#@markdown ---
#@markdown ### **(2) 通道啟用設定**
#@markdown > **選擇要啟動的公開存取通道。預設全部啟用。**
#@markdown ---
#@markdown **啟用 Colab 官方代理**
ENABLE_COLAB_PROXY = True #@param {type:"boolean"}
#@markdown **啟用 Localtunnel**
ENABLE_LOCALTUNNEL = True #@param {type:"boolean"}
#@markdown **啟用 Cloudflare**
ENABLE_CLOUDFLARE = True #@param {type:"boolean"}
#@markdown ---
#@markdown ### **(3) 通用設定**
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
# 版本: 18.0
# 日期: 2025-08-29T00:20:00+08:00
#
# 本次變更重點:
# 1. **核心架構整合**: 將啟動器 (Colabpro.py) 與新的輕量化後端 (api_server_v2.py) 整合。
# 2. **啟動邏輯更新**: 移除舊的 run_services.py 服務總管，改為直接透過 uvicorn 啟動 FastAPI 伺服器。
# 3. **動態埠號分配**: 實現了從 uvicorn 日誌中自動解析動態分配的埠號，取代了舊的硬編碼埠號回報機制。
# 4. **依賴清理**: 更新了依賴安裝流程，改為安裝 `requirements-server.txt` 和 `requirements-worker.txt`。
# 5. **參數整理**: 標記了 `FORCE_DEPS_REFRESH` 和 `LIGHT_MODE` 等舊參數為待廢棄。
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
import requests
from queue import Queue, Empty

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
        output = ["🚀 善狼一鍵啟動器 v18 🚀", ""]
        for log_item in self._log_deque:
            ts = log_item['timestamp'].strftime('%H:%M:%S')
            level, msg = log_item['level'], log_item['message']
            output.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {msg}")
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
        output.append("\n🔗 公開存取網址:")
        urls = self._state.get("urls", {})
        if not urls and status not in ["✅ 應用程式已就緒", "❌ 啟動失敗"]:
             output.append("  - (正在產生...)")
        else:
            for name in TUNNEL_ORDER:
                proxy_info = urls.get(name)
                if proxy_info:
                    url, password = proxy_info.get("url", "錯誤"), proxy_info.get("password")
                    if "錯誤" in str(url):
                        output.append(f"  - {name+':':<15} {colorize(url, 'ERROR')}")
                    else:
                        output.append(f"  - {name+':':<15} {url}")
                        if password: output.append(f"    {'密碼:':<15} {password}")
                elif self._state.get("all_tunnels_done"):
                    output.append(f"  - {name+':':<15} (啟動失敗)")
        print("\n".join(output), flush=True)

class TunnelManager:
    def __init__(self, port, project_path, log_manager, results_queue, timeout=20):
        self.port, self._project_path, self._log, self._results_queue, self._timeout = port, Path(project_path), log_manager.log, results_queue, timeout
        self.threads, self.processes = [], []

    def _run_tunnel_service(self, name, command, pattern, cwd):
        self._log("INFO", f"-> {name} 競速開始...")
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', cwd=cwd)
            self.processes.append(proc)
            start_time = time.monotonic()
            for line in iter(proc.stdout.readline, ''):
                if time.monotonic() - start_time > self._timeout:
                    self._results_queue.put((name, {"url": "錯誤：超時"})); self._log("ERROR", f"❌ {name} 超時"); return
                self._log("RUNNER", f"[{name}] {line.strip()}")
                if match := re.search(pattern, line):
                    url = match.group(1); self._results_queue.put((name, {"url": url})); self._log("SUCCESS", f"✅ {name} 成功: {url}"); return
            proc.wait(timeout=1)
            self._results_queue.put((name, {"url": f"錯誤：程序已結束 (Code: {proc.returncode})"}))
        except Exception as e:
            self._log("ERROR", f"❌ {name} 執行時發生錯誤: {e}"); self._results_queue.put((name, {"url": "錯誤：執行失敗"}))

    def _get_cloudflare_url(self):
        name = "Cloudflare"
        try:
            cf_path = self._project_path / 'cloudflared'
            if not cf_path.exists():
                self._log("INFO", "下載 Cloudflared..."); subprocess.run(['wget', '-q', 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64', '-O', str(cf_path)], check=True); subprocess.run(['chmod', '+x', str(cf_path)], check=True)
            self._run_tunnel_service(name, [str(cf_path), 'tunnel', '--url', f'http://127.0.0.1:{self.port}'], r'(https?://\S+\.trycloudflare\.com)', self._project_path)
        except Exception as e:
            self._log("ERROR", f"❌ Cloudflared 前置作業失敗: {e}"); self._results_queue.put((name, {"url": "錯誤：前置作業失敗"}))

    def _get_localtunnel_url(self): self._log("ERROR", "Localtunnel 已被棄用"); self._results_queue.put(("Localtunnel", {"url": "錯誤：已被棄用"}))
    def _get_colab_url(self): self._log("ERROR", "Colab Proxy 已被棄用"); self._results_queue.put(("Colab", {"url": "錯誤：已被棄用"}))

    def start_tunnels(self):
        racers = [threading.Thread(target=self._get_cloudflare_url)] if ENABLE_CLOUDFLARE else []
        if not racers: self._log("WARN", "所有代理通道均未啟用。"); return
        self._log("INFO", f"🚀 開始併發獲取 {len(racers)} 個已啟用的代理網址..."); [r.start() for r in racers]; self.threads.extend(racers)

    def stop_tunnels(self):
        self._log("INFO", "正在關閉所有隧道服務..."); [p.terminate() for p in self.processes if p.poll() is None]; [t.join(timeout=1) for t in self.threads]

def create_log_viewer_html(log_manager):
    try:
        log_history, num_logs = log_manager.get_full_log_history()[-LOG_COPY_MAX_LINES:], len(log_manager.get_full_log_history())
        unique_id, log_content_string = f"log-area-{int(time.time() * 1000)}", "\n".join(log_history)
        escaped_log = html.escape(log_content_string)
        textarea_html = f'<textarea id="{unique_id}" style="position:absolute; left: -9999px;" readonly>{escaped_log}</textarea>'
        onclick_js = f'''(async () => {{ await navigator.clipboard.writeText(document.getElementById('{unique_id}').value); this.innerText = "✅ 已複製!"; setTimeout(() => {{ this.innerText = "📋 複製這 {num_logs} 條日誌"; }}, 2000); }})()'''
        button_html = f'<button onclick="{html.escape(onclick_js)}" style="padding: 6px 12px; margin: 12px 0; cursor: pointer;">📋 複製這 {num_logs} 條日誌</button>'
        return f'<details style="margin-top: 15px; padding: 12px; border: 1px solid #e0e0e0; border-radius: 8px;"><summary style="cursor: pointer; font-weight: bold;">點此展開/收合最近 {num_logs} 條詳細日誌</summary><div style="margin-top: 12px;">{textarea_html}{button_html}<pre style="background-color: #fff; padding: 12px; border: 1px solid #e0e0e0; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word;"><code>{escaped_log}</code></pre>{button_html}</div></details>'
    except Exception as e:
        return f"<p>❌ 產生最終日誌報告時發生錯誤: {html.escape(str(e))}</p>"

# ==============================================================================
# PART 3: 主啟動器邏輯
# ==============================================================================
def _log_subprocess_output(server_proc, log_manager, shared_state):
    stream = server_proc.stdout if server_proc.stdout else server_proc.stderr
    if not stream: return
    for line in iter(stream.readline, ''):
        line = line.strip()
        if not line: continue
        log_manager.log("RUNNER", line)
        if not shared_state.get('app_port'):
            if match := re.search(r"Uvicorn running on .*:(\d+)", line):
                try:
                    port = int(match.group(1)); shared_state['app_port'] = port
                    log_manager.log("INFO", f"成功從日誌中解析到應用程式埠號: {port}")
                except (ValueError, IndexError):
                    log_manager.log("ERROR", f"無法從 uvicorn 日誌 '{line}' 中解析埠號。")

def launch_application(project_path_str: str, log_manager: DisplayManager):
    project_path, shared_state = Path(project_path_str), log_manager._state
    manager_proc, tunnel_manager = None, None
    try:
        shared_state["status"] = "正在啟動後端服務..."; log_manager.print_ui()
        manager_command = [sys.executable, "-u", "-m", "uvicorn", "api_server_v2:app", "--host", "0.0.0.0", "--port", "0"]
        manager_proc = subprocess.Popen(manager_command, cwd=project_path, text=True, encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=os.environ.copy())
        threading.Thread(target=_log_subprocess_output, args=(manager_proc, log_manager, shared_state), daemon=True).start()

        shared_state["status"] = "等待後端服務回報埠號..."; start_time = time.monotonic()
        app_port = None
        while time.monotonic() - start_time < 30:
            if manager_proc.poll() is not None: raise RuntimeError(f"後端服務在回報埠號前已意外終止，返回碼: {manager_proc.poll()}")
            if app_port := shared_state.get('app_port'): log_manager.log("SUCCESS", f"✅ 成功從後端獲取到應用程式埠號: {app_port}"); break
            time.sleep(0.5)
        else: raise RuntimeError("在 30 秒內未偵測到後端回報的埠號。")

        shared_state["status"] = "正在建立網路通道..."; shared_state['urls'] = {}; results_queue = Queue()
        tunnel_manager = TunnelManager(app_port, project_path, log_manager, results_queue); tunnel_manager.start_tunnels()

        # In this new simplified architecture, we don't need a complex health check loop.
        # We just wait for the first URL to be generated.
        urls_to_check = []
        enabled_tunnels_count = ENABLE_CLOUDFLARE + ENABLE_LOCALTUNNEL + ENABLE_COLAB_PROXY
        monitoring_deadline = time.monotonic() + 120
        while time.monotonic() < monitoring_deadline and not shared_state.get("urls"):
             if manager_proc.poll() is not None: shared_state["status"] = f"❌ 後端服務已停止"; raise RuntimeError("後端服務在通道建立期間意外終止。")
             try: name, data = results_queue.get_nowait(); shared_state["urls"][name] = data
             except Empty: pass
             log_manager.print_ui(); time.sleep(UI_REFRESH_SECONDS)

        shared_state["status"] = "✅ 應用程式已就緒"
        log_manager.print_ui()
        log_manager.log("INFO", "啟動器將保持運行以維持後端服務。"); manager_proc.wait()

    except Exception as e:
        log_manager.log("CRITICAL", f"啟動器發生致命錯誤: {e}"); traceback.print_exc()
    finally:
        shared_state["status"] = "關閉中..."; log_manager.print_ui()
        if tunnel_manager: tunnel_manager.stop_tunnels()
        if manager_proc and manager_proc.poll() is None: log_manager.log("INFO", "正在終止後端服務..."); manager_proc.terminate(); manager_proc.wait(timeout=5)
        display(HTML(create_log_viewer_html(log_manager)))
        log_manager.log("INFO", "所有服務已關閉。")

# ==============================================================================
# FINAL EXECUTION BLOCK
# ==============================================================================
if __name__ == '__main__':
    shared_state_main = {"start_time_monotonic": time.monotonic(), "status": "初始化...", "urls": {}, "all_tunnels_done": False}
    log_manager_main = DisplayManager(shared_state_main)
    try:
        project_path = download_repository(log_manager_main)
        if not project_path: raise RuntimeError("專案下載失敗，請檢查日誌。")

        log_manager_main.log("INFO", "正在安裝 API 伺服器 (FastAPI) 所需的依賴...")
        server_reqs = Path(project_path) / "requirements-server.txt"
        if server_reqs.exists(): subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(server_reqs)], check=True, capture_output=True, text=True)
        else: raise FileNotFoundError(f"找不到伺服器依賴檔案: {server_reqs}")
        log_manager_main.log("SUCCESS", "✅ API 伺服器依賴安裝完成。")

        log_manager_main.log("INFO", "正在安裝腳本 (Scripts) 所需的依賴...")
        worker_reqs = Path(project_path) / "requirements-worker.txt"
        if worker_reqs.exists(): subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(worker_reqs)], check=True, capture_output=True, text=True)
        else: log_manager_main.log("WARN", f"未找到腳本依賴檔案: {worker_reqs}，跳過安裝。")
        log_manager_main.log("SUCCESS", "✅ 腳本依賴安裝完成。")

        launch_application(project_path, log_manager_main)
    except Exception as e:
        log_manager_main.log("CRITICAL", f"發生無法處理的致命錯誤: {e}"); log_manager_main.log("CRITICAL", traceback.format_exc())
    finally:
        log_manager_main.log("INFO", "--- 啟動器執行結束 ---"); log_manager_main.print_ui()
        if 'project_path' in locals() and locals()['project_path']: display(HTML(create_log_viewer_html(log_manager_main)))
