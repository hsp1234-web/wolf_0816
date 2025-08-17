# Colab 啟動器文件

這份文件提供了在 Google Colab 環境中執行應用程式的程式碼。

## 使用說明

1.  開啟一個新的 Google Colab 筆記本。
2.  點擊下方「點此展開 Colab 程式碼」來顯示程式碼。
3.  點擊程式碼區塊右上角的複製按鈕。
4.  將複製的程式碼貼到 Colab 的儲存格中。
5.  依照程式碼儲存格中的指示執行。

<details>
<summary>📋 點此展開 Colab 程式碼 (v2 - 優化版)</summary>

```python
# -*- coding: utf-8 -*-
#@title 🐺 善狼啟動器 v2 (Part 2: 執行)
#@markdown ---
#@markdown ### **通用設定**
#@markdown > **此處為儀表板顯示相關的常用設定。**
#@markdown ---
#@markdown **儀表板更新頻率 (秒)**
UI_REFRESH_SECONDS = 0.5 #@param {type:"number"}
#@markdown **日誌顯示行數**
LOG_DISPLAY_LINES = 15 #@param {type:"integer"}
#@markdown **時區設定**
TIMEZONE = "Asia/Taipei" #@param {type:"string"}
#@markdown ---
#@markdown > **確認設定無誤後，點擊此儲存格左側的「執行」按鈕來啟動服務。**
#@markdown ---

# ==============================================================================
# SECTION -1: 隱藏的預設參數
# ==============================================================================
# 日誌等級可見性 (預設全部開啟)
SHOW_LOG_LEVEL_BATTLE = True
SHOW_LOG_LEVEL_SUCCESS = True
SHOW_LOG_LEVEL_INFO = True
SHOW_LOG_LEVEL_WARN = True
SHOW_LOG_LEVEL_ERROR = True
SHOW_LOG_LEVEL_CRITICAL = True
SHOW_LOG_LEVEL_DEBUG = False # Debug 預設關閉
# 報告與歸檔設定
LOG_ARCHIVE_ROOT_FOLDER = "paper"
# 各階段超時設定
PROXY_URL_TIMEOUT = 60
SETUP_TIMEOUT = 600 # 延長準備時間以應對冷快取

# ==============================================================================
# SECTION 0: 環境準備與核心依賴導入
# ==============================================================================
import sys
import subprocess
import socket
import http.server
import socketserver
try:
    import pytz
except ImportError:
    print("正在安裝 pytz...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pytz"])
    import pytz

import os
import shutil
from pathlib import Path
import time
from datetime import datetime
import threading
from collections import deque
import re
import json
from IPython.display import clear_output, display, HTML
from google.colab import output as colab_output, userdata

# ==============================================================================
# SECTION 1: 管理器類別定義 (新架構)
# ==============================================================================

class LogManager:
    """日誌管理器：負責記錄、過濾和儲存所有日誌訊息。"""
    def __init__(self, max_lines, timezone_str, log_levels_to_show):
        self._log_deque = deque(maxlen=max_lines)
        self._full_history = []
        self._lock = threading.Lock()
        self.timezone = pytz.timezone(timezone_str)
        self.log_levels_to_show = log_levels_to_show

    def log(self, level: str, message: str):
        with self._lock:
            log_entry = {"timestamp": datetime.now(self.timezone), "level": level.upper(), "message": str(message)}
            if len(str(message)) > 500: # 避免過長的日誌訊息
                log_entry["message"] = str(message)[:500] + "..."
            self._log_deque.append(log_entry)
            self._full_history.append(log_entry)

    def get_display_logs(self) -> list:
        with self._lock:
            all_logs = list(self._log_deque)
            return [log for log in all_logs if self.log_levels_to_show.get(f"SHOW_LOG_LEVEL_{log['level']}", False)]

    def get_full_history(self) -> list:
        with self._lock: return list(self._full_history)

ANSI_COLORS = {"SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m", "RESET": "\033[0m"}
def colorize(text, level): return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS['RESET']}"

class DisplayManager:
    """顯示管理器：在背景執行緒中負責繪製純文字動態儀表板。"""
    def __init__(self, log_manager, stats_dict, refresh_rate):
        self._log_manager = log_manager; self._stats = stats_dict
        self._refresh_rate = refresh_rate; self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["🐺 善狼啟動器 v2 🐺", ""]
        logs_to_display = self._log_manager.get_display_logs()
        for log in logs_to_display:
            ts, level = log['timestamp'].strftime('%H:%M:%S'), log['level']
            output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {log['message']}")
        if self._stats.get('proxy_url'):
            if logs_to_display: output_buffer.append("")
            output_buffer.append(f"✅ 代理連結 (可點擊): {self._stats['proxy_url']}")
        try:
            import psutil
            cpu, ram = f"{psutil.cpu_percent():5.1f}%", f"{psutil.virtual_memory().percent:5.1f}%"
        except ImportError: cpu, ram = "N/A", "N/A"
        elapsed = time.monotonic() - self._stats.get("start_time_monotonic", time.monotonic())
        mins, secs = divmod(elapsed, 60)
        output_buffer.append("\n" + f"⏱️ {int(mins):02d}分{int(secs):02d}秒 | 💻 CPU: {cpu} | 🧠 RAM: {ram} | 🔥 狀態: {self._stats.get('status', '初始化...')}")
        return output_buffer

    def _run(self):
        while not self._stop_event.is_set():
            try:
                clear_output(wait=True); print("\n".join(self._build_output_buffer()), flush=True)
                time.sleep(self._refresh_rate)
            except Exception as e: self._log_manager.log("ERROR", f"DisplayManager 執行緒出錯: {e}"); time.sleep(5)

    def start(self): self._thread.start()
    def stop(self): self._stop_event.set(); self._thread.join(timeout=2)

class ProxyManager:
    """代理管理器：負責啟動臨時伺服器並穩定獲取 Colab 代理網址。"""
    def __init__(self, log_manager, stats_dict):
        self._log_manager = log_manager; self._stats = stats_dict
        self.port = self._find_free_port()
        self.url_ready_event = threading.Event()
        self.shutdown_event = threading.Event()
        self._proxy_server_thread = threading.Thread(target=self._run_proxy_server, daemon=True)
        self._url_getter_thread = threading.Thread(target=self._get_colab_url, daemon=True)

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0)); return s.getsockname()[1]

    def _run_proxy_server(self):
        """運行一個極簡的 HTTP 伺服器，其唯一目的是佔據埠號。"""
        class StatusHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                status_html = f"<html><head><title>啟動中</title><meta http-equiv='refresh' content='5'></head><body><h1>🚀 系統正在準備中，請稍候...</h1><p>當前狀態：{self._stats.get('status', '初始化...')}</p><p>請查看 Colab 主控台以獲取詳細日誌。</p></body></html>"
                self.wfile.write(status_html.encode('utf-8'))

        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", self.port), StatusHandler) as httpd:
            httpd.timeout = 0.5
            self._log_manager.log("INFO", f"臨時狀態伺服器已在埠號 {self.port} 上啟動。")
            while not self.shutdown_event.is_set():
                httpd.handle_request()
            self._log_manager.log("INFO", "臨時狀態伺服器已關閉。")

    def _get_colab_url(self):
        """在背景執行緒中，使用重試邏輯來穩定獲取代理 URL。"""
        self._stats['status'] = "🔗 獲取代理網址..."
        self._log_manager.log("INFO", "開始獲取 Colab 代理網址...")
        max_retries, retry_delay = 20, 2
        for attempt in range(max_retries):
            try:
                url = colab_output.eval_js(f'google.colab.kernel.proxyPort({self.port})', timeout_sec=10)
                if url and url.strip().startswith('http'):
                    self._stats['proxy_url'] = url.strip()
                    self._log_manager.log("SUCCESS", f"✅ 成功獲取代理網址！")
                    self.url_ready_event.set()
                    return
                else:
                    self._log_manager.log("WARN", f"獲取到無效的網址: '{str(url)[:50]}...' (第 {attempt+1} 次)")
            except Exception as e:
                self._log_manager.log("WARN", f"獲取網址時出錯: {e} (第 {attempt+1} 次)")
            time.sleep(retry_delay)
        self._log_manager.log("CRITICAL", "無法獲取 Colab 代理網址，啟動失敗。")
        self.url_ready_event.set() # 也設置事件以防主線程無限等待

    def start(self):
        self._proxy_server_thread.start()
        self._url_getter_thread.start()

    def stop(self):
        self.shutdown_event.set()
        try: # 發送一個假請求來解除 httpd.handle_request() 的阻塞
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(("127.0.0.1", self.port))
        except Exception: pass
        self._proxy_server_thread.join(timeout=2)

class SetupManager:
    """準備管理器：在背景執行所有耗時的安裝與設定任務。"""
    def __init__(self, log_manager, stats_dict, project_path):
        self._log_manager = log_manager; self._stats = stats_dict
        self.project_path = project_path
        self.setup_complete_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            self._stats['status'] = "⚙️ 準備系統環境..."
            self._install_system_deps()
            self._stats['status'] = "📦 安裝 Python 依賴..."
            self._install_python_deps()
            self._stats['status'] = "準備工作完成！"
            self._log_manager.log("SUCCESS", "✅ 所有背景準備工作已完成。")
        except Exception as e:
            self._stats['status'] = f"❌ 準備工作失敗"
            self._log_manager.log("CRITICAL", f"背景準備執行緒出錯: {e}")
        finally:
            self.setup_complete_event.set()

    def _install_system_deps(self):
        self._log_manager.log("INFO", "步驟 1/2: 檢查並安裝系統級依賴 FFmpeg...")
        try:
            if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
                self._log_manager.log("INFO", "未偵測到 FFmpeg，開始安裝...")
                subprocess.run(["apt-get", "update", "-qq"], check=True)
                subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"], check=True)
                self._log_manager.log("SUCCESS", "✅ FFmpeg 安裝完成。")
            else:
                self._log_manager.log("INFO", "FFmpeg 已安裝。")
        except Exception as e:
            self._log_manager.log("ERROR", f"安裝 FFmpeg 時發生錯誤: {e}")
            raise # 重新拋出異常以終止準備流程

    def _install_python_deps(self):
        self._log_manager.log("INFO", "步驟 2/2: 使用 uv 高速安裝 Python 依賴...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
            for req_file_name in ["requirements-server.txt", "requirements-worker.txt"]:
                req_path = self.project_path / req_file_name
                if req_path.is_file():
                    self._log_manager.log("INFO", f"  - 正在安裝 {req_file_name}...")
                    subprocess.run([sys.executable, "-m", "uv", "pip", "install", "-q", "-r", str(req_path)], check=True)
                else:
                    self._log_manager.log("WARN", f"  - 未找到 {req_file_name}，跳過。")
            self._log_manager.log("SUCCESS", "✅ 所有 Python 依賴安裝完成。")
        except Exception as e:
            self._log_manager.log("ERROR", f"安裝 Python 依賴時發生錯誤: {e}")
            raise

    def start(self): self._thread.start()

class ServerManager:
    """伺服器管理器：負責在準備工作完成後，啟動主應用程式。"""
    def __init__(self, log_manager, stats_dict, project_path):
        self._log_manager = log_manager; self._stats = stats_dict
        self.project_path = project_path
        self.server_process = None
        self._stop_event = threading.Event()

    def start_main_app(self, port: int):
        """啟動核心協調器子進程。"""
        try:
            self._stats['status'] = "🚀 啟動主應用程式..."
            self._log_manager.log("BATTLE", "=== 正在呼叫核心協調器 `orchestrator.py` ===")

            project_src_path = self.project_path / "src"
            sys.path.insert(0, str(project_src_path.resolve()))
            from db.database import initialize_database, add_system_log
            initialize_database()
            add_system_log("colab_launch", "INFO", "Handover complete. Launching main orchestrator.")

            launch_command = [sys.executable, "src/core/orchestrator.py", "--no-mock", "--port", str(port)]

            process_env = os.environ.copy()
            # ... (此處省略了與原版相同的 GOOGLE_API_KEY 讀取邏輯) ...
            src_path_str = str((self.project_path / "src").resolve())
            process_env['PYTHONPATH'] = f"{src_path_str}{os.pathsep}{process_env.get('PYTHONPATH', '')}"

            self.server_process = subprocess.Popen(
                launch_command, cwd=str(self.project_path), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                preexec_fn=os.setsid, env=process_env
            )
            self._log_manager.log("INFO", f"主應用程式進程已啟動 (PID: {self.server_process.pid})。")
            self._stats['status'] = "✅ 應用程式運行中"

            for line in iter(self.server_process.stdout.readline, ''):
                if self._stop_event.is_set(): break
                self._log_manager.log("DEBUG", line.strip())

            self.server_process.wait()
            if not self._stop_event.is_set():
                 self._log_manager.log("WARN", "主應用程式意外終止。")
                 self._stats['status'] = "⚠️ 應用程式已停止"

        except Exception as e:
            self._stats['status'] = "❌ 主應用程式啟動失敗"
            self._log_manager.log("CRITICAL", f"啟動主應用時出錯: {e}")

    def stop(self):
        self._stop_event.set()
        if self.server_process and self.server_process.poll() is None:
            self._log_manager.log("INFO", "正在終止主應用程式...")
            try:
                os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGTERM)
                self.server_process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try: os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGKILL)
                except ProcessLookupError: pass

# ==============================================================================
# SECTION 2: 核心功能函式 (保持不變)
# ==============================================================================
def archive_reports(log_manager, start_time, end_time, status):
    # ... (此處省略了與原版相同的歸檔邏輯) ...
    pass

# ==============================================================================
# SECTION 3: 主程式執行入口 (新流程)
# ==============================================================================
def main(project_path_str: str):
    """主執行函式，採用新架構協調啟動流程。"""
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "初始化...", "proxy_url": None}
    log_manager, display_manager, proxy_manager, setup_manager, server_manager = [None]*5
    start_time = datetime.now(pytz.timezone(TIMEZONE))

    try:
        # 1. 初始化日誌和顯示管理器
        log_levels = {name: globals()[name] for name in globals() if name.startswith("SHOW_LOG_LEVEL_")}
        log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, log_levels_to_show=log_levels)
        display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
        display_manager.start()

        # 2. 階段一：立即獲取代理網址
        proxy_manager = ProxyManager(log_manager=log_manager, stats_dict=shared_stats)
        proxy_manager.start()
        if not proxy_manager.url_ready_event.wait(timeout=PROXY_URL_TIMEOUT) or not shared_stats.get('proxy_url'):
            raise RuntimeError("獲取代理網址超時或失敗。")

        # 3. 階段二：在背景執行準備工作
        project_path = Path(project_path_str)
        setup_manager = SetupManager(log_manager=log_manager, stats_dict=shared_stats, project_path=project_path)
        setup_manager.start()
        if not setup_manager.setup_complete_event.wait(timeout=SETUP_TIMEOUT):
            raise RuntimeError("背景準備工作超時。")
        if "失敗" in shared_stats.get('status', ''):
             raise RuntimeError("背景準備工作失敗，請檢查日誌。")

        # 4. 階段三：服務交接
        log_manager.log("BATTLE", "準備工作完成，正在進行服務交接...")
        port_to_use = proxy_manager.port
        proxy_manager.stop() # 關閉臨時伺服器，釋放埠號

        server_manager = ServerManager(log_manager=log_manager, stats_dict=shared_stats, project_path=project_path)
        # 在新的執行緒中啟動主應用，以允許主執行緒繼續處理監控和關閉邏輯
        server_thread = threading.Thread(target=server_manager.start_main_app, args=(port_to_use,), daemon=True)
        server_thread.start()

        # 5. 保持運行，直到使用者中斷
        log_manager.log("SUCCESS", "✅✅✅ 系統已完全啟動！✅✅✅")
        while server_thread.is_alive():
            time.sleep(1)

    except KeyboardInterrupt:
        log_manager.log("WARN", "\n🛑 偵測到使用者手動中斷...")
    except Exception as e:
        if log_manager: log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}")
        else: print(f"❌ 發生未預期的致命錯誤: {e}")
    finally:
        # 6. 優雅地關閉所有服務
        if server_manager: server_manager.stop()
        if proxy_manager and proxy_manager._proxy_server_thread.is_alive(): proxy_manager.stop()
        if display_manager: display_manager.stop()

        end_time = datetime.now(pytz.timezone(TIMEZONE))
        if log_manager and display_manager:
            clear_output(); print("\n".join(display_manager._build_output_buffer()))
            print("\n--- ✅ 所有任務完成，系統已安全關閉 ---")
            # ... (此處省略了與原版相同的複製按鈕與歸檔邏輯) ...

if __name__ == "__main__":
    if 'PROJECT_PATH_FROM_DOWNLOADER' in globals() and Path(globals()['PROJECT_PATH_FROM_DOWNLOADER']).exists():
        print("✅ 找到由下載器準備的專案資料夾，準備啟動...")
        main(project_path_str=globals()['PROJECT_PATH_FROM_DOWNLOADER'])
    else:
        print("❌ 錯誤：找不到專案資料夾。請先成功執行第一步的下載器。")
```

</details>
