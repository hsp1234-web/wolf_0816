# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器 (v17.0) 🐺
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "703" #@param {type:"string"}
#@markdown **專案資料夾名稱 (PROJECT_FOLDER_NAME)**
PROJECT_FOLDER_NAME = "wolf_project" #@param {type:"string"}
#@markdown **強制刷新後端程式碼 (FORCE_REPO_REFRESH)**
#@markdown > **如果勾選，每次執行都會先刪除舊的專案資料夾，再重新下載。**
FORCE_REPO_REFRESH = True #@param {type:"boolean"}
#@markdown > **v16 架構更新：舊的依賴包 (`dependencies.tar.gz`) 已被廢棄，此選項不再有效。**
FORCE_DEPS_REFRESH = False #@param {type:"boolean"}
#@markdown **輕量測試模式 (LIGHT_MODE)**
#@markdown > **勾選後，將以輕量模式啟動，使用 `tiny.en` 模型並安裝較少的依賴，適合快速測試。**
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
# 版本: 17.0 (架構: 資料庫中心化)
# 日期: 2025-08-27T19:36:11+08:00
#
# 本次變更重點:
# 1. **核心架構遷移**: 從 v16 的「門面伺服器」模型，遷移至以資料庫為中心的 v17 新架構。
# 2. **服務化啟動**: 啟動器現在會協調啟動三個獨立的常駐服務：
#    - `src/db/manager.py`: 資料庫管理器，確保對 SQLite 的安全並發訪問。
#    - `src/api_server.py`: 統一的 API 伺服器，處理所有 HTTP 和 WebSocket 請求。
#    - `workers/transcription_worker.py`: 背景工作者，主動從資料庫輪詢任務。
# 3. **移除舊元件**: 舊的 `facade_server.py` 和 `background_installer.py` 已被新架構取代並封存。
# 4. **依賴問題修復**: 更新 `faster-whisper` 版本以解決 `av` 套件的編譯問題。
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
                proxy_info = urls.get(name)
                if proxy_info:
                    url = proxy_info.get("url", "錯誤：無效資料")
                    password = proxy_info.get("password")
                    if "錯誤" in str(url):
                        error_msg = f"\033[91m{url}\033[0m" if IN_COLAB else f"{url} (錯誤)"
                        output.append(f"  - {name+':':<15} {error_msg}")
                    else:
                        output.append(f"  - {name+':':<15} {url}")
                        if password:
                            output.append(f"    {'密碼:':<15} {password}")
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

            start_time = time.monotonic()
            for line in iter(proc.stdout.readline, ''):
                if time.monotonic() - start_time > self._timeout:
                    self._state["urls"][name] = {"url": "錯誤：超時"}
                    self._log("ERROR", f"❌ {name} 超時")
                    return

                self._log("RUNNER", f"[{name}] {line.strip()}")
                match = re.search(pattern, line)
                if match:
                    url = match.group(1)
                    result_data = {"url": url}

                    # 恢復 v10 的密碼獲取邏輯
                    if name == "Localtunnel":
                        self._log("INFO", "-> 正在為 Localtunnel 獲取隧道密碼...")
                        try:
                            pass_proc = subprocess.run(['curl', '-s', 'https://loca.lt/mytunnelpassword'], capture_output=True, text=True, timeout=10)
                            if pass_proc.returncode == 0 and pass_proc.stdout.strip():
                                password = pass_proc.stdout.strip()
                                result_data['password'] = password
                                self._log("SUCCESS", f"✅ Localtunnel 密碼已獲取: {password}")
                            else:
                                self._log("WARN", "⚠️ 無法獲取 Localtunnel 密碼。")
                        except Exception as e:
                            self._log("ERROR", f"❌ 獲取 Localtunnel 密碼時出錯: {e}")

                    self._state["urls"][name] = result_data
                    self._log("SUCCESS", f"✅ {name} 成功: {url}")
                    return

            proc.wait(timeout=1)
            if self._state["urls"].get(name) is None:
                self._state["urls"][name] = {"url": f"錯誤：程序已結束 (Code: {proc.returncode})"}
        except Exception as e:
            self._log("ERROR", f"❌ {name} 執行時發生錯誤: {e}")
            self._state["urls"][name] = {"url": f"錯誤：執行失敗"}

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
        name = "Localtunnel"
        try:
            # 修正：避免全域安裝，改用 npx 直接執行套件，更穩健。
            self._log("INFO", "正在使用 'npx localtunnel' 啟動通道...")
            command = ['npx', 'localtunnel', '--port', str(self.port), '--bypass-tunnel-reminder']
            self._run_tunnel_service(name, command, r'(https?://\S+\.loca\.lt)', self._project_path)
        except Exception as e:
            self._log("ERROR", f"❌ Localtunnel 前置作業失敗: {e}")
            self._state["urls"][name] = {"url": "錯誤：前置作業失敗"}


    def _get_colab_url(self):
        name = "Colab"
        self._log("INFO", f"-> {name} 競速開始...")

        # 放寬驗證：改回 v10 的寬鬆驗證邏輯
        max_retries = 10
        retry_delay_seconds = 8
        for attempt in range(max_retries):
            try:
                if attempt > 0: self._log("INFO", f"-> {name} 正在進行第 {attempt + 1}/{max_retries} 次嘗試...")

                result_url = ""
                if IN_COLAB:
                    raw_result = colab_output.eval_js(f"google.colab.kernel.proxyPort({self.port}, {{'cache': false}})", timeout_sec=self._timeout)
                    if isinstance(raw_result, str) and raw_result.startswith('http'):
                        result_url = raw_result
                else: # Mock behavior
                    time.sleep(1)
                    result_url = "https://mock-colab-url.googleusercontent.com"

                if result_url:
                    self._state["urls"][name] = {"url": result_url}
                    self._log("SUCCESS", f"✅ {name} 在第 {attempt + 1} 次嘗試後成功: {result_url}")
                    return
                else:
                    self._log("WARN", f"⚠️ {name} 第 {attempt + 1}/{max_retries} 次嘗試未回傳有效網址 (收到: {raw_result})")

            except Exception as e:
                self._log("WARN", f"⚠️ {name} 第 {attempt + 1}/{max_retries} 次嘗試時發生錯誤: {e}")

            if attempt < max_retries - 1:
                self._log("INFO", f"-> 將在 {retry_delay_seconds} 秒後重試...")
                time.sleep(retry_delay_seconds)

        self._log("CRITICAL", f"❌ {name} 在 {max_retries} 次嘗試後徹底失敗。")
        self._state["urls"][name] = {"url": "錯誤：多次嘗試後失敗"}

    def start_tunnels(self):
        self._state["urls"] = {}

        racers = []
        if ENABLE_CLOUDFLARE:
            racers.append(threading.Thread(target=self._get_cloudflare_url))
        if ENABLE_LOCALTUNNEL:
            racers.append(threading.Thread(target=self._get_localtunnel_url))
        if ENABLE_COLAB_PROXY:
            racers.append(threading.Thread(target=self._get_colab_url))

        if not racers:
            self._log("WARN", "所有代理通道均未啟用，將無法生成公開存取網址。")
            self._state["all_tunnels_done"] = True
            return

        self._log("INFO", f"🚀 開始併發獲取 {len(racers)} 個已啟用的代理網址...")
        for r in racers: r.start(); self.threads.append(r)

    def stop_tunnels(self):
        self._log("INFO", "正在關閉所有隧道服務...")
        for p in self.processes:
            if p.poll() is None: p.terminate()
        for t in self.threads: t.join(timeout=1)

def create_log_viewer_html(log_manager):
    """ 產生最終的 HTML 日誌報告，樣式與 v10 版本完全一致。 """
    try:
        log_history = log_manager.get_full_log_history()
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

# ==============================================================================
# PART 3: 主啟動器邏輯
# ==============================================================================
def _log_subprocess_output(server_proc, log_manager, shared_state):
    """在一個獨立的執行緒中持續讀取和記錄子程序的輸出。"""
    if not server_proc or not server_proc.stdout:
        return
    for line in iter(server_proc.stdout.readline, ''):
        line = line.strip()
        if not line:
            continue
        log_manager.log("RUNNER", line)
        # 同時檢查埠號，並更新共享狀態
        if line.startswith("APP_PORT:"):
            try:
                port = int(line.split(":")[1].strip())
                shared_state['app_port'] = port
            except (ValueError, IndexError):
                log_manager.log("ERROR", f"無法從行 '{line}' 中解析埠號。")

def launch_application(project_path_str: str, log_manager: DisplayManager):
    """
    v18 架構：採用 v10 的單點委派模式，啟動一個統一的總管腳本。
    """
    project_path = Path(project_path_str)
    shared_state = log_manager._state
    manager_proc, tunnel_manager = None, None

    try:
        # --- 步驟 1: 啟動統一的服務總管腳本 ---
        shared_state["status"] = "正在啟動後端服務總管..."
        log_manager.print_ui()

        manager_command = [sys.executable, str(project_path / "scripts" / "run_services.py")]

        # 準備環境變數，將 LIGHT_MODE 傳遞給總管腳本
        manager_env = os.environ.copy()
        if LIGHT_MODE:
            manager_env["LIGHT_MODE"] = "1"
            log_manager.log("INFO", "輕量測試模式已啟用。")

        manager_proc = subprocess.Popen(
            manager_command, cwd=project_path, text=True,
            encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=manager_env
        )

        # 在背景執行緒中監聽總管腳本的輸出，以獲取埠號
        log_thread = threading.Thread(target=_log_subprocess_output, args=(manager_proc, log_manager, shared_state), daemon=True)
        log_thread.start()

        # --- 步驟 2: 等待後端回報埠號 ---
        shared_state["status"] = "等待後端服務回報埠號..."
        port_detection_timeout = 30  # 等待30秒
        start_time = time.monotonic()
        app_port = None
        while time.monotonic() - start_time < port_detection_timeout:
            if manager_proc.poll() is not None:
                raise RuntimeError(f"後端服務總管在回報埠號前已意外終止，返回碼: {manager_proc.poll()}")
            app_port = shared_state.get('app_port')
            if app_port:
                log_manager.log("SUCCESS", f"✅ 成功從後端獲取到應用程式埠號: {app_port}")
                break
            time.sleep(0.5)

        if not app_port:
            raise RuntimeError(f"在 {port_detection_timeout} 秒內未偵測到後端回報的埠號。")

        # --- 步驟 3: 為 API 伺服器啟動網路通道 ---
        shared_state["status"] = "正在建立網路通道..."
        tunnel_manager = TunnelManager(app_port, shared_state, project_path, log_manager)
        tunnel_manager.start_tunnels()

        # 等待所有啟用的通道完成 (或失敗)
        enabled_tunnels_count = ENABLE_COLAB_PROXY + ENABLE_LOCALTUNNEL + ENABLE_CLOUDFLARE
        if enabled_tunnels_count > 0:
            while len(shared_state.get("urls", {})) < enabled_tunnels_count:
                if manager_proc.poll() is not None:
                    shared_state["status"] = f"❌ 後端服務已停止 (返回碼: {manager_proc.poll()})"
                    log_manager.log("CRITICAL", "後端服務總管意外終止！")
                    raise RuntimeError("後端服務在通道建立期間意外終止。")
                log_manager.print_ui()
                time.sleep(UI_REFRESH_SECONDS)

        shared_state["all_tunnels_done"] = True
        log_manager.log("INFO", "通道已建立，準備驗證服務健康度...")
        log_manager.print_ui()

        # --- 步驟 4: 執行健康檢查 ---
        shared_state["status"] = "正在驗證服務健康度..."
        health_check_passed = False
        health_check_timeout = 90  # 總超時秒數
        health_check_start_time = time.monotonic()

        # 從已有的 URL 中找到一個可用的來進行健康檢查
        urls_to_check = [info["url"] for info in shared_state.get("urls", {}).values() if "錯誤" not in info.get("url", "")]

        if not urls_to_check:
            log_manager.log("CRITICAL", "❌ 沒有可用的代理網址來進行健康檢查。")
        else:
            while time.monotonic() - health_check_start_time < health_check_timeout:
                if manager_proc.poll() is not None:
                    log_manager.log("CRITICAL", "❌ 後端服務在健康檢查期間意外終止。")
                    break

                for base_url in urls_to_check:
                    try:
                        health_url = f"{base_url.rstrip('/')}/api/health"
                        log_manager.log("INFO", f"正在嘗試健康檢查: {health_url}")
                        response = requests.get(health_url, timeout=10)
                        if response.status_code == 200 and response.json().get("status") == "ok":
                            log_manager.log("SUCCESS", f"✅ 健康檢查通過！服務在 {base_url} 上已就緒。")
                            health_check_passed = True
                            break
                        else:
                            log_manager.log("WARN", f"健康檢查失敗 (狀態碼: {response.status_code})，將重試...")
                    except requests.exceptions.RequestException as e:
                        log_manager.log("WARN", f"健康檢查請求失敗: {e}，將重試...")

                if health_check_passed:
                    break

                log_manager.print_ui()
                time.sleep(5) # 每次重試間隔

        if health_check_passed:
            shared_state["status"] = "✅ 應用程式已就緒"
            log_manager.log("SUCCESS", "✅ 應用程式已通過健康檢查並準備就緒！")
        else:
            shared_state["status"] = "❌ 健康檢查失敗"
            log_manager.log("CRITICAL", "❌ 後端服務未能在指定時間內通過健康檢查。")

        log_manager.print_ui()

        # --- 步驟 5: 持續監控，直到使用者中斷 ---
        log_manager.log("INFO", "啟動器將保持運行以維持後端服務。可隨時手動中斷。")
        manager_proc.wait()

    except KeyboardInterrupt:
        log_manager.log("WARN", "收到使用者中斷指令，正在優雅地關閉所有服務...")
    except Exception as e:
        log_manager.log("CRITICAL", f"啟動器發生致命錯誤: {e}")
        traceback.print_exc()
    finally:
        shared_state["status"] = "關閉中..."
        log_manager.print_ui()
        if tunnel_manager:
            tunnel_manager.stop_tunnels()
        if manager_proc and manager_proc.poll() is None:
            log_manager.log("INFO", "正在終止後端服務總管...")
            manager_proc.terminate()
            try:
                manager_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                manager_proc.kill()

        display(HTML(create_log_viewer_html(log_manager)))
        log_manager.log("INFO", "所有服務已關閉。")

# ==============================================================================
# FINAL EXECUTION BLOCK
# ==============================================================================
if __name__ == '__main__':
    # 初始化狀態管理器和日誌
    shared_state_main = {
        "start_time_monotonic": time.monotonic(),
        "status": "初始化...",
        "urls": {},
        "all_tunnels_done": False
    }
    log_manager_main = DisplayManager(shared_state_main)

    try:
        # 步驟 1: 下載或更新專案程式碼
        project_path = download_repository(log_manager_main)
        if not project_path:
            raise RuntimeError("專案下載失敗，請檢查日誌。")

        # 步驟 2: 安裝門面伺服器所需的最基本依賴
        log_manager_main.log("INFO", "正在安裝門面伺服器所需的基本依賴...")
        requirements_path = Path(project_path) / "src" / "requirements_light.txt"
        if not requirements_path.exists():
            raise FileNotFoundError(f"找不到輕量級依賴檔案: {requirements_path}")

        pip_install_command = [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)]
        subprocess.run(pip_install_command, check=True, capture_output=True, text=True)
        log_manager_main.log("SUCCESS", "✅ 基本依賴安裝完成。")

        # 步驟 3: 啟動新的應用程式架構
        # 注意：新的 launch_application 不再需要 deps_path_str
        launch_application(project_path, log_manager_main)

    except Exception as e:
        log_manager_main.log("CRITICAL", f"發生無法處理的致命錯誤: {e}")
        # 打印詳細的 traceback 以便除錯
        import traceback
        log_manager_main.log("CRITICAL", traceback.format_exc())
    finally:
        log_manager_main.log("INFO", "--- 啟動器執行結束 ---")
        # 確保最終的 UI 狀態被打印
        log_manager_main.print_ui()
        # 確保最終的日誌報告被顯示
        if 'project_path' in locals() and locals()['project_path']:
             display(HTML(create_log_viewer_html(log_manager_main)))
