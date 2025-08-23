# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器 (v8) 🐺
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "645" #@param {type:"string"}
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
# 版本: 8.0 (架構: 穩定啟動與診斷)
# 日期: 2025-08-23T19:03:00+08:00
#
# 🔴 **禁止直接執行**: 本檔案 (Colabpro.py) 被設計為一個程式庫 (library)，
#    由 Colab Notebook 環境導入並呼叫。請勿透過 `python Colabpro.py` 直接執行。
#
# 🟡 **限制修改範圍**:
#    - **允許修改**: 僅限於核心啟動邏輯，即 `launch_application` 或類似功能的內部實作。
#    - **禁止修改**: 絕對不要更動任何與使用者介面 (ipywidgets)、參數輸入、
#      UI 顯示設計，以及最終 HTML 報告產生與複製按鈕相關的程式碼。
#
# 本次變更重點:
# 1. **修復啟動流程**: 徹底解決了因 DB Manager 未啟動而導致 API Gateway
#    超時崩潰的根本問題。現在 `run_app.py` 會確保服務按正確順序啟動。
# 2. **整合診斷工具**: 加入了環境健康診斷功能，提前發現問題。
# 3. **整合併發代理**: 引入了併發代理獲取機制，提升連線成功率。
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
from http.server import HTTPServer, BaseHTTPRequestHandler

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

from google.colab import output as colab_output

try:
    from IPython.display import clear_output, display, HTML
except ImportError:
    print("警告: 未在 IPython 環境中執行，將使用模擬的 display 函式。")
    def clear_output(wait=False): pass
    def display(obj): print(f"[DISPLAY] {obj}")
    def HTML(html_string): return f"HTML Content: {html_string}"

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
        output_buffer = ["📥🐺 善狼一鍵啟動器 (v8) 🐺", ""]
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

        # **修改**: 顯示所有可用的代理網址，並包含密碼資訊
        proxy_urls = self._stats.get('proxy_urls', [])
        if not proxy_urls:
            output_buffer.append("⏳ 正在啟動服務並生成連結...")
        else:
            output_buffer.append("✅ 應用程式連結 (點擊開啟):")
            # 增加一個空行，讓連結區塊更清晰
            output_buffer.append("")
            for proxy_info in proxy_urls:
                name = proxy_info.get('method', 'N/A')
                url = proxy_info.get('url', 'N/A')
                password = proxy_info.get('password')

                # 顯示服務名稱和網址
                output_buffer.append(f"  - {name+':':<20} {url}")

                # 如果有密碼，則在下一行縮排顯示
                if password:
                    output_buffer.append(f"    {'密碼:':<20} {password}")

                # 在每個條目後增加一個空行以分隔
                output_buffer.append("")
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
# PART 3: 環境健康診斷儀 (Environment Health Diagnostics)
# ==============================================================================
def _run_health_check(log_manager, check_func, *args, **kwargs):
    """執行單個健康檢查並記錄結果的輔助函式。"""
    check_name = check_func.__doc__
    log_manager.log("INFO", f"🩺 {check_name}...")
    try:
        passed, message = check_func(*args, **kwargs)
        if passed:
            log_manager.log("SUCCESS", f"✅ {check_name}: 通過 ({message})")
            return True
        else:
            log_manager.log("CRITICAL", f"❌ {check_name}: 失敗 ({message})")
            return False
    except Exception as e:
        log_manager.log("CRITICAL", f"❌ {check_name}: 執行時發生無法預期的錯誤: {e}")
        return False

def check_external_network():
    """檢查外部網路連線"""
    import socket
    try:
        with socket.create_connection(("google.com", 80), timeout=5):
            return True, "能夠成功連線到 google.com"
    except OSError as e:
        return False, str(e)

def check_port_allocation():
    """檢查內部埠號分配"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            port = s.getsockname()[1]
            if port > 0:
                return True, f"成功分配到埠號 {port}"
            else:
                return False, "作業系統回傳了無效的埠號 0"
    except Exception as e:
        return False, str(e)

def check_communication_pipe():
    """檢查 Colab 前後端通訊管道"""
    try:
        result = colab_output.eval_js("'pong'", timeout_sec=15)
        if result == 'pong':
            return True, "成功收到 'pong' 回應"
        else:
            return False, f"預期收到 'pong'，但收到了: {result}"
    except Exception as e:
        return False, f"通訊管道完全中斷: {e}"

import socket

class _SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, format, *args): return

class _StoppableHTTPServer(HTTPServer):
    def run(self):
        try:
            self.serve_forever()
        except Exception:
            pass # Suppress errors on shutdown
    def stop(self):
        # shutdown is not instant, so run in a thread
        threading.Thread(target=self.shutdown, daemon=True).start()

def _find_available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0)); return s.getsockname()[1]

def check_colab_proxy_availability():
    """檢查 Colab 官方代理服務是否能正常運作"""
    port = _find_available_port()
    if not port:
        return False, "無法找到可用埠號來啟動測試伺服器。"

    server = _StoppableHTTPServer(("127.0.0.1", port), _SimpleHTTPRequestHandler)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    time.sleep(0.5) # 給予伺服器啟動時間

    try:
        # 使用一個較短的超時來進行此項檢查
        result = colab_output.eval_js(f"google.colab.kernel.proxyPort({port}, {{'cache': false}})", timeout_sec=20)

        if isinstance(result, str) and result.startswith('http'):
            return True, f"成功獲取測試伺服器的代理網址"
        else:
            return False, f"無法獲取代理網址 (eval_js 回傳了非預期的值: {result})"
    except Exception as e:
        return False, f"獲取代理網址時發生錯誤: {e}"
    finally:
        server.stop()
        server_thread.join(timeout=2) # 等待伺服器線程結束


def run_all_diagnostics(log_manager):
    """執行所有前置健康檢查。"""
    log_manager.log("INFO", "="*40)
    log_manager.log("INFO", "🚀 開始執行 Colab 環境健康診斷...")
    log_manager.log("INFO", "="*40)

    checks = [
        check_external_network,
        check_port_allocation,
        check_communication_pipe,
        check_colab_proxy_availability,
    ]

    all_passed = True
    for check_func in checks:
        if not _run_health_check(log_manager, check_func):
            all_passed = False

    log_manager.log("INFO", "="*40)
    if all_passed:
        log_manager.log("SUCCESS", "✅ 所有健康檢查項目均已通過！")
    else:
        log_manager.log("CRITICAL", "❌ 部分健康檢查失敗，建議中斷執行並檢查環境。")
    log_manager.log("INFO", "="*40)

    return all_passed

# ==============================================================================
# PART 4: 高可用性代理獲取器 (High-Availability Proxy Getter)
# ==============================================================================
class HAProxyGetter:
    def __init__(self, port, log_manager, timeout=15):
        self.port = port
        self.log = log_manager.log
        self.timeout = timeout
        self.results_queue = queue.Queue()
        self.active_processes = []

    def _get_colab_url(self):
        method_name = "Colab 官方代理"
        self.log("INFO", f"-> {method_name} 競速開始...")
        max_retries = 10
        retry_delay_seconds = 8

        for attempt in range(max_retries):
            try:
                # 在每次嘗試時記錄日誌
                if attempt > 0:
                    self.log("INFO", f"-> {method_name} 正在進行第 {attempt + 1}/{max_retries} 次嘗試...")

                result = colab_output.eval_js(f"google.colab.kernel.proxyPort({self.port}, {{'cache': false}})", timeout_sec=self.timeout)

                if isinstance(result, str) and result.startswith('http'):
                    self.results_queue.put({'method': method_name, 'url': result})
                    self.log("SUCCESS", f"✅ {method_name} 在第 {attempt + 1} 次嘗試後成功: {result}")
                    return # 成功後立即退出函式
                else:
                    self.log("WARN", f"⚠️ {method_name} 第 {attempt + 1}/{max_retries} 次嘗試未回傳有效網址 (收到: {result})")

            except Exception as e:
                self.log("WARN", f"⚠️ {method_name} 第 {attempt + 1}/{max_retries} 次嘗試時發生錯誤: {e}")

            # 如果不是最後一次嘗試，則等待後重試
            if attempt < max_retries - 1:
                self.log("INFO", f"-> 將在 {retry_delay_seconds} 秒後重試...")
                time.sleep(retry_delay_seconds)

        # 如果迴圈正常結束（表示所有嘗試都失敗了）
        self.log("CRITICAL", f"❌ {method_name} 在 {max_retries} 次嘗試後徹底失敗。")

    def _run_tunnel_service(self, method_name, cmd, pattern):
        self.log("INFO", f"-> {method_name} 競速開始...")
        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
            self.active_processes.append(proc)

            start_time = time.monotonic()
            while time.monotonic() - start_time < self.timeout:
                line = proc.stdout.readline()
                if not line: break
                match = re.search(pattern, line)
                if match:
                    url = match.group(1)
                    result_data = {'method': method_name, 'url': url}

                    # 如果是 Localtunnel，額外獲取密碼
                    if method_name == "Localtunnel":
                        self.log("INFO", "-> 正在為 Localtunnel 獲取隧道密碼...")
                        try:
                            # 使用 curl 獲取作為密碼的公開 IP 位址
                            pass_proc = subprocess.run(['curl', 'https://loca.lt/mytunnelpassword'], capture_output=True, text=True, timeout=10)
                            if pass_proc.returncode == 0 and pass_proc.stdout.strip():
                                password = pass_proc.stdout.strip()
                                result_data['password'] = password
                                self.log("SUCCESS", f"✅ Localtunnel 密碼已獲取: {password}")
                            else:
                                self.log("WARN", "⚠️ 無法獲取 Localtunnel 密碼。")
                        except Exception as e:
                            self.log("ERROR", f"❌ 獲取 Localtunnel 密碼時出錯: {e}")

                    self.results_queue.put(result_data)
                    self.log("SUCCESS", f"✅ {method_name} 成功: {url}")
                    return # 讓子程序在背景繼續運行
                time.sleep(0.1)
            self.log("WARN", f"⚠️ {method_name} 在時限內未輸出網址。")
        except Exception as e:
            self.log("ERROR", f"❌ {method_name} 執行時發生錯誤: {e}")
        # 不在此處終止 proc，讓 get_urls 決定何時清理

    def _get_localtunnel_url(self):
        try:
            # 檢查並安裝
            if shutil.which('npm') is None:
                self.log("INFO", "安裝 Node.js 和 npm...")
                subprocess.run(['apt-get', 'install', '-qqy', 'nodejs', 'npm'], check=True, capture_output=True)
            if shutil.which('lt') is None:
                 self.log("INFO", "安裝 localtunnel...")
                 subprocess.run(['npm', 'install', '-g', 'localtunnel'], check=True, capture_output=True)

            cmd = ['lt', '--port', str(self.port)]
            self._run_tunnel_service("Localtunnel", cmd, r'(https?://\S+\.loca\.lt)')
        except Exception as e:
            self.log("ERROR", f"❌ Localtunnel 前置作業失敗: {e}")


    def _get_cloudflare_url(self):
        try:
            # 檢查並安裝
            if not Path('./cloudflared').exists():
                self.log("INFO", "下載 Cloudflared...")
                subprocess.run(['wget', '-q', 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64', '-O', 'cloudflared'], check=True)
                subprocess.run(['chmod', '+x', 'cloudflared'], check=True)

            cmd = ['./cloudflared', 'tunnel', '--url', f'http://127.0.0.1:{self.port}']
            self._run_tunnel_service("Cloudflare Tunnel", cmd, r'(https?://\S+\.trycloudflare\.com)')
        except Exception as e:
            self.log("ERROR", f"❌ Cloudflared 前置作業失敗: {e}")

    def get_urls(self):
        racers = [
            threading.Thread(target=self._get_colab_url),
            threading.Thread(target=self._get_localtunnel_url),
            threading.Thread(target=self._get_cloudflare_url),
        ]

        self.log("INFO", "🚀 開始併發獲取代理網址...")
        for r in racers:
            r.start()

        # 等待所有線程跑完或超時
        for r in racers:
            r.join(timeout=self.timeout + 2) # 給予額外2秒的緩衝

        # 從佇列中收集所有成功結果
        urls = []
        while not self.results_queue.empty():
            try:
                result = self.results_queue.get_nowait()
                # 直接附加整個字典，而不是只附加元組，以保留密碼等額外資訊
                urls.append(result)
            except queue.Empty:
                break

        # 按 method 名稱排序，以確保顯示順序一致
        return sorted(urls, key=lambda x: x['method'])

    def stop_tunnels(self):
        self.log("INFO", "正在關閉所有隧道服務...")
        for proc in self.active_processes:
            if proc.poll() is None:
                proc.terminate()
        self.log("INFO", "隧道服務已關閉。")


# ==============================================================================
# PART 5: 主啟動器邏輯
# ==============================================================================
def launch_application(project_path_str: str, log_manager: DisplayManager):
    project_path = Path(project_path_str)
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "啟動中...", "proxy_urls": []}
    display_manager = log_manager
    display_manager._stats = shared_stats
    display_manager.start()

    # --- 步驟 1: 執行環境健康診斷 ---
    if not run_all_diagnostics(display_manager):
        # 健康檢查現在是非致命的。如果失敗，只記錄警告而不是中止。
        shared_stats['status'] = "⚠️ 環境檢查警告"
        display_manager.log("WARN", "部分環境健康檢查未通過，將繼續嘗試啟動，但過程可能不穩定。")
        # 讓使用者有時間看到警告
        time.sleep(3)

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

        proxy_getter = None # 在 try 區塊外初始化
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
        if proxy_getter:
            proxy_getter.stop_tunnels()
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

# ==============================================================================
# FINAL EXECUTION BLOCK (貼上到 Colab 後執行的程式碼)
# ==============================================================================
# 主要執行流程
# 建立日誌管理器
main_display_manager = DisplayManager(
    stats_dict={},
    refresh_rate=UI_REFRESH_SECONDS
)

# 下載專案
project_path = download_repository(log_manager=main_display_manager)

# 如果專案下載成功，則啟動應用程式
if project_path:
    try:
        launch_application(
            project_path_str=project_path,
            log_manager=main_display_manager
        )
    except Exception as e:
        # launch_application 內部已經有自己的異常處理和日誌記錄
        # 但為了以防萬一，我們在這裡再加一層
        main_display_manager.log("CRITICAL", f"啟動程序發生頂層未捕獲錯誤: {e}")
        traceback.print_exc()
        main_display_manager.stop() # 確保在意外失敗時停止
else:
    # 如果下載失敗
    main_display_manager.log("CRITICAL", "專案下載失敗，無法啟動應用程式。")
    main_display_manager.stop() # 停止日誌更新
    # 顯示最終日誌
    final_html = create_log_viewer_html(main_display_manager)
    display(HTML(final_html))
    print("\n--- 執行因錯誤而終止 ---")
