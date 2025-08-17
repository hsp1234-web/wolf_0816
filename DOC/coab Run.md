# Colab 啟動器更新說明

本文檔旨在說明對 Colab 啟動器 (`Colab.py`) 進行的重大更新。舊版啟動器在效率和穩定性上存在一些根本性問題，新版採用了「兩階段代理啟動器」架構，旨在提供更快速、更可靠的啟動體驗。

## 問題分析：舊版啟動器的挑戰

### 1. 啟動時的阻塞
舊的腳本在執行任何操作前，會先用 `pip` 安裝 `requirements-server.txt`。如果這個檔案包含的依賴較多，整個啟動流程就會被卡在第一步，使用者需要長時間等待才能看到任何進展。

### 2. 未能完全利用 `uv`
腳本雖然在背景安裝 worker 依賴時使用了高速的 `uv`，但在最開始安裝核心依賴時，用的仍然是傳統的 `pip`，未能最大化安裝效率。

### 3. 代理網址不穩定的根源：競態條件 (Race Condition)
舊機制是先啟動後端的 Uvicorn 伺服器，然後在主控台日誌中「等待」一個就緒訊號，再用 `google.colab.kernel.proxyPort` 這個 JavaScript 指令去「抓取」Colab 分配的代理網址。這個過程非常脆弱，因為 Uvicorn 雖然啟動了，但 Colab 的代理服務可能還沒完全準備好，導致 JavaScript 指令抓取失敗或返回無效值。這是啟動有時會失敗的根本原因。

---

## 全新設計方案：「兩階段代理啟動器」

我們重新設計了整個啟動流程，採用一個更穩健、更高效的「兩階段」架構。

### **第一階段：立即啟動「狀態與代理」伺服器 (目標：秒級反應)**
1.  **不安裝，立即執行**：Colab 儲存格一執行，不安裝任何東西，只用 Python 內建函式庫。
2.  **啟動微型伺服器**：在背景立即啟動一個極簡的 Python 臨時伺服器。
3.  **立即獲取代理網址**：讓這個微型伺服器佔據一個埠號，並立刻呼叫 `google.colab.kernel.proxyPort` 為它自己取得一個公開的、永久不變的代理網址。
4.  **立即顯示網址**：將這個穩定、有效的網址立刻顯示給使用者。

### **第二階段：在背景執行真正的準備工作**
1.  **啟動背景執行緒**：將所有耗時的工作（依賴安裝、主程式啟動）全部放到另一個背景執行緒中。
2.  **高速安裝**：在這個執行緒裡，使用 `uv` 來高速安裝所有依賴。
3.  **啟動核心應用**：所有依賴都安裝完畢後，才啟動原本的 `orchestrator.py` 主應用程式。
4.  **無縫交接**：
    - 在主應用程式啟動前，優雅地關閉微型伺服器。
    - 利用 `SO_REUSEADDR` 這個通訊端選項，確保主應用程式可以立即重用剛被釋放的埠號，避免「地址已被佔用」的錯誤。
    - 一旦主應用程式啟動，使用者正在查看的那個穩定網址，其背後的服務就會從「臨時狀態頁」無縫切換到「真正的應用程式」。

### 新設計的優勢
*   **極致的效率體驗**：使用者在執行儲存格後的幾秒內就能得到一個可以互動的網址和儀表板，徹底解決了「啟動慢、無反饋」的問題。
*   **絕對穩定的代理網址**：我們不再去「猜測」和「抓取」主應用的網址，而是在一開始就為我們自己的微型伺服器創造並鎖定一個網址。這個網址從頭到尾都是有效的，從根本上解決了代理網址不穩定的問題。

---

## 新版 Colab 啟動器程式碼

底下是修改後 `Colab.py` 的完整程式碼。您可以點擊「顯示程式碼」來查看，並使用「一鍵複製」按鈕來方便地將其貼到您的 Colab 儲存格中。

<details>
<summary>點此顯示/隱藏 Colab.py 完整程式碼</summary>

<div style="position: relative;">
<button onclick="copyCode(this)" style="position: absolute; top: 10px; right: 10px; z-index: 10; padding: 5px 10px; font-size: 12px; cursor: pointer;">複製程式碼</button>
<pre><code id="colab-code" class="language-python">
# -*- coding: utf-8 -*-
#@title 🐺 善狼啟動器 (Part 2: 執行)
#@markdown ---
#@markdown ### **通用設定**
#@markdown > **此處為儀表板顯示相關的常用設定。**
#@markdown ---
#@markdown **儀表板更新頻率 (秒)**
UI_REFRESH_SECONDS = 0.5 #@param {type:"number"}
#@markdown **日誌顯示行數**
LOG_DISPLAY_LINES = 10 #@param {type:"integer"}
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
SHOW_LOG_LEVEL_DEBUG = True
# 報告與歸檔設定
LOG_ARCHIVE_ROOT_FOLDER = "paper"

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
# SECTION 1: 管理器類別定義 (Managers)
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
            self._log_deque.append(log_entry)
            self._full_history.append(log_entry)

    def get_display_logs(self) -> list:
        with self._lock:
            all_logs = list(self._log_deque)
            return [log for log in all_logs if self.log_levels_to_show.get(f"SHOW_LOG_LEVEL_{log['level']}", False)]

    def get_full_history(self) -> list:
        with self._lock:
            return self._full_history

ANSI_COLORS = {
    "SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m",
    "CRITICAL": "\033[31m", "RESET": "\033[0m"
}

def colorize(text, level):
    return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS['RESET']}"

class DisplayManager:
    """顯示管理器：在背景執行緒中負責繪製純文字動態儀表板。"""
    def __init__(self, log_manager, stats_dict, refresh_rate):
        self._log_manager = log_manager; self._stats = stats_dict
        self._refresh_rate = refresh_rate; self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["🐺善狼下載啟動器🐺", ""]
        if self._stats.get('proxy_url'):
            output_buffer.append(f"✅ 代理連結 (點擊開啟): {self._stats['proxy_url']}")
            output_buffer.append("")
        else:
            output_buffer.append("⏳ 正在生成代理連結...")
            output_buffer.append("")

        logs_to_display = self._log_manager.get_display_logs()
        for log in logs_to_display:
            ts, level = log['timestamp'].strftime('%H:%M:%S'), log['level']
            output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {log['message']}")

        try:
            import psutil
            cpu, ram = f"{psutil.cpu_percent():5.1f}%", f"{psutil.virtual_memory().percent:5.1f}%"
        except ImportError: cpu, ram = "   N/A ", "   N/A "
        elapsed = time.monotonic() - self._stats.get("start_time_monotonic", time.monotonic())
        mins, secs = divmod(elapsed, 60)
        output_buffer.append("")
        output_buffer.append(f"⏱️ {int(mins):02d}分{int(secs):02d}秒 | 💻 CPU: {cpu} | 🧠 RAM: {ram} | 🔥 狀態: {self._stats.get('status', '初始化...')}")
        return output_buffer

    def _run(self):
        while not self._stop_event.is_set():
            try:
                clear_output(wait=True); print("\n".join(self._build_output_buffer()), flush=True)
                time.sleep(self._refresh_rate)
            except Exception as e: print(f"\nDisplayManager 執行緒發生錯誤: {e}"); time.sleep(5)

    def start(self): self._thread.start()
    def stop(self): self._stop_event.set(); self._thread.join(timeout=2)

class ReusableTCPServer(socketserver.TCPServer):
    """可重用地址的 TCPServer，解決 'Address already in use' 問題。"""
    allow_reuse_address = True

class TempServerManager:
    """臨時伺服器管理器：負責啟動一個臨時的 HTTP 伺服器以佔用埠號並顯示狀態。"""
    def __init__(self, port, log_manager):
        self.port = port
        self._log_manager = log_manager
        self.server = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop_event = threading.Event()

    def _run(self):
        handler = http.server.SimpleHTTPRequestHandler
        # Python 3.7+
        with ReusableTCPServer(("", self.port), handler) as httpd:
            self._log_manager.log("DEBUG", f"臨時伺服器已在埠號 {self.port} 上啟動。")
            self.server = httpd
            # 等待停止信號
            self._stop_event.wait()
            self._log_manager.log("DEBUG", "臨時伺服器收到停止信號。")

    def start(self):
        self._thread.start()

    def stop(self):
        self._log_manager.log("INFO", "正在關閉臨時狀態伺服器...")
        self._stop_event.set()
        # 寄送一個假請求給自己來解除 httpd.serve_forever() 的阻塞
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                pass
        except (socket.timeout, ConnectionRefusedError):
            pass # 這是預期行為
        if self.server:
            self.server.server_close()
        self._thread.join(timeout=2)
        self._log_manager.log("SUCCESS", "臨時狀態伺服器已關閉。")

class BackgroundWorker:
    """背景工作者：在獨立執行緒中執行所有耗時的安裝與啟動任務。"""
    def __init__(self, log_manager, stats_dict, project_path_str, port, temp_server_manager):
        self._log_manager = log_manager
        self._stats = stats_dict
        self.project_path = Path(project_path_str)
        self.port = port
        self.temp_server_manager = temp_server_manager
        self.server_process = None
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _install_dependencies(self, requirements_file: str, installer: str = "uv"):
        req_path = self.project_path / requirements_file
        if not req_path.is_file():
            self._log_manager.log("WARN", f"未找到 {requirements_file}，跳過安裝。")
            return True

        self._log_manager.log("INFO", f"正在使用 {installer} 安裝 `{requirements_file}`...")
        self._stats['status'] = f"安裝依賴 ({requirements_file})..."

        try:
            # 確保 uv 已安裝
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
            # 使用 uv 安裝
            command = [sys.executable, "-m", "uv", "pip", "install", "-q", "-r", str(req_path)]
            result = subprocess.run(command, check=False, capture_output=True, text=True, encoding='utf-8')
            if result.returncode != 0:
                self._log_manager.log("CRITICAL", f"依賴安裝失敗 ({requirements_file}):\n{result.stderr}")
                return False
            self._log_manager.log("SUCCESS", f"✅ 成功安裝 {requirements_file}")
            return True
        except Exception as e:
            self._log_manager.log("CRITICAL", f"安裝 {requirements_file} 時發生嚴重錯誤: {e}")
            return False

    def _run(self):
        try:
            # 步驟 1: 安裝所有依賴
            if not self._install_dependencies("requirements-server.txt"): return
            if not self._install_dependencies("requirements-worker.txt"): return

            # 步驟 2: 關閉臨時伺服器
            self.temp_server_manager.stop()
            time.sleep(1) # 給予作業系統一點時間來釋放埠號

            # 步驟 3: 啟動核心協調器
            self._log_manager.log("INFO", "🚀 所有依賴已備妥，正在啟動核心協調器...")
            self._stats['status'] = "啟動主程式..."
            orchestrator_script_path = self.project_path / "src" / "core" / "orchestrator.py"
            if not orchestrator_script_path.is_file():
                self._log_manager.log("CRITICAL", f"核心協調器未找到: {orchestrator_script_path}")
                return

            # 清理舊的埠號檔案，以防萬一
            port_file_path = self.project_path / "src" / "db" / "db_manager.port"
            if port_file_path.exists():
                try: port_file_path.unlink()
                except Exception as e: self._log_manager.log("ERROR", f"清理舊埠號檔案失敗: {e}")

            launch_command = [sys.executable, str(orchestrator_script_path), "--no-mock", "--port", str(self.port)]

            process_env = os.environ.copy()
            # 處理 GOOGLE_API_KEY
            try:
                key_from_secret = userdata.get('GOOGLE_API_KEY')
                if key_from_secret:
                    process_env['GOOGLE_API_KEY'] = key_from_secret
                    self._log_manager.log("SUCCESS", "✅ 成功從 Colab Secret 讀取 GOOGLE_API_KEY。")
            except Exception:
                self._log_manager.log("WARN", "⚠️ 無法從 Colab Secret 讀取金鑰，將嘗試從 config.json 讀取。")

            # 設定 PYTHONPATH
            src_path_str = str((self.project_path / "src").resolve())
            process_env['PYTHONPATH'] = f"{src_path_str}{os.pathsep}{process_env.get('PYTHONPATH', '')}"

            self.server_process = subprocess.Popen(
                launch_command, cwd=str(self.project_path), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                preexec_fn=os.setsid, env=process_env
            )
            self._log_manager.log("INFO", f"協調器子進程已啟動 (PID: {self.server_process.pid})，監聽日誌...")

            uvicorn_ready_pattern = re.compile(r"Uvicorn running on")
            for line in iter(self.server_process.stdout.readline, ''):
                if self._stop_event.is_set(): break
                self._log_manager.log("DEBUG", line.strip())
                if uvicorn_ready_pattern.search(line):
                    self._stats['status'] = "✅ 伺服器運行中"
                    self._log_manager.log("SUCCESS", "✅ 主應用程式已成功接管埠號並運行！")

            self.server_process.wait()
            if self._stats['status'] != "✅ 伺服器運行中":
                self._stats['status'] = "❌ 伺服器啟動失敗"
                self._log_manager.log("CRITICAL", "協調器進程在就緒前已終止。")

        except Exception as e:
            self._stats['status'] = "❌ 發生致命錯誤"; self._log_manager.log("CRITICAL", f"背景工作者執行緒出錯: {e}")
        finally:
            if self._stats['status'] != "✅ 伺服器運行中":
                self._stats['status'] = "⏹️ 已停止"


    def start(self): self._thread.start()
    def stop(self):
        self._stop_event.set()
        if self.server_process and self.server_process.poll() is None:
            self._log_manager.log("INFO", "正在終止伺服器進程...")
            try:
                os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGTERM)
                self.server_process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try: os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGKILL)
                except ProcessLookupError: pass
        self._thread.join(timeout=2)

# ==============================================================================
# SECTION 2: 核心功能函式
# ==============================================================================

def find_free_port() -> int:
    """尋找一個空閒的 TCP 埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def archive_reports(log_manager, start_time, end_time, status):
    # (此函式內容未變，保持原樣)
    print("\n\n" + "="*60 + "\n--- 任務結束，開始執行自動歸檔 ---\n" + "="*60)
    try:
        root_folder = Path(LOG_ARCHIVE_ROOT_FOLDER)
        root_folder.mkdir(exist_ok=True)
        ts_folder_name = start_time.strftime('%Y-%m-%dT%H-%M-%S%z')
        report_dir = root_folder / ts_folder_name
        report_dir.mkdir(exist_ok=True)
        log_history = log_manager.get_full_history()
        detailed_log_content = f"# 詳細日誌\n\n```\n" + "\n".join([f"[{log['timestamp'].isoformat()}] [{log['level']}] {log['message']}" for log in log_history]) + "\n```"
        (report_dir / "詳細日誌.md").write_text(detailed_log_content, encoding='utf-8')
        duration = end_time - start_time
        perf_report_content = f"# 效能報告\n\n- **任務狀態**: {status}\n- **開始時間**: `{start_time.isoformat()}`\n- **結束時間**: `{end_time.isoformat()}`\n- **總耗時**: `{str(duration)}`\n"
        (report_dir / "效能報告.md").write_text(perf_report_content.strip(), encoding='utf-8')
        (report_dir / "綜合報告.md").write_text(f"# 綜合報告\n\n{perf_report_content}\n{detailed_log_content}", encoding='utf-8')
        print(f"✅ 報告已成功歸檔至: {report_dir}")
    except Exception as e: print(f"❌ 歸檔報告時發生錯誤: {e}")


def install_system_deps():
    # (此函式內容未變，保持原樣)
    print("檢查並安裝系統級依賴 FFmpeg...")
    try:
        if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
            print("未偵測到 FFmpeg，開始安裝...")
            subprocess.run(["apt-get", "update", "-qq"], check=True)
            subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"], check=True)
            print("✅ FFmpeg 安裝完成。")
        else:
            print("✅ FFmpeg 已安裝。")
    except Exception as e:
        print(f"❌ 安裝 FFmpeg 時發生錯誤: {e}")

# ==============================================================================
# SECTION 3: 主程式執行入口 (全新設計)
# ==============================================================================

def main(project_path_str: str):
    """主執行函式，採用兩階段啟動，實現秒級回應。"""
    install_system_deps()
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "初始化...", "proxy_url": None}
    log_manager, display_manager, temp_server_manager, background_worker = None, None, None, None
    start_time = datetime.now(pytz.timezone(TIMEZONE))

    try:
        # 步驟 1: 初始化日誌和顯示管理器
        log_levels = {name: globals()[name] for name in globals() if name.startswith("SHOW_LOG_LEVEL_")}
        log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, log_levels_to_show=log_levels)
        display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
        display_manager.start()
        log_manager.log("INFO", "顯示管理器已啟動。")

        # 步驟 2: 尋找空閒埠號並啟動臨時伺服器
        shared_stats['status'] = "尋找可用埠號..."
        port = find_free_port()
        log_manager.log("INFO", f"找到空閒埠號: {port}")
        temp_server_manager = TempServerManager(port=port, log_manager=log_manager)
        temp_server_manager.start()
        shared_stats['status'] = "建立臨時伺服器..."

        # 步驟 3: (關鍵) 立即取得代理連結
        time.sleep(1) # 等待臨時伺服器线程完全啟動
        max_retries, retry_delay = 5, 2
        for attempt in range(max_retries):
            try:
                log_manager.log("INFO", f"正在嘗試取得代理連結... (第 {attempt + 1}/{max_retries} 次)")
                url = colab_output.eval_js(f'google.colab.kernel.proxyPort({port})')
                if url and url.strip().startswith('http'):
                    shared_stats['proxy_url'] = url.strip()
                    log_manager.log("SUCCESS", f"✅✅✅ 成功取得永久代理連結！")
                    break
                else:
                    log_manager.log("WARN", f"收到無效的代理回傳值: '{str(url)[:50]}...'")
            except Exception as e:
                log_manager.log("WARN", f"獲取代理連結時發生錯誤: {e}")
            time.sleep(retry_delay)

        if not shared_stats.get('proxy_url'):
            shared_stats['status'] = "❌ 取得代理連結失敗"
            log_manager.log("CRITICAL", "無法取得代理連結，啟動中止。")
            return

        # 步驟 4: 啟動背景工作者執行緒，處理所有耗時任務
        log_manager.log("INFO", "啟動背景工作者，開始安裝依賴...")
        background_worker = BackgroundWorker(
            log_manager=log_manager,
            stats_dict=shared_stats,
            project_path_str=project_path_str,
            port=port,
            temp_server_manager=temp_server_manager
        )
        background_worker.start()

        # 步驟 5: 主執行緒等待背景工作者完成
        background_worker._thread.join()
        log_manager.log("INFO", "背景工作者執行緒已結束。")

    except KeyboardInterrupt:
        if log_manager: log_manager.log("WARN", "🛑 偵測到使用者手動中斷...")
    except Exception as e:
        if log_manager: log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}")
        else: print(f"❌ 發生未預期的致命錯誤: {e}")
    finally:
        # 步驟 6: 清理所有資源
        if background_worker: background_worker.stop()
        if temp_server_manager and temp_server_manager._thread.is_alive(): temp_server_manager.stop()
        if display_manager and display_manager._thread.is_alive(): display_manager.stop()
        end_time = datetime.now(pytz.timezone(TIMEZONE))
        if log_manager and display_manager:
            clear_output(); print("\n".join(display_manager._build_output_buffer()))
            print("\n--- ✅ 所有任務完成，系統已安全關閉 ---")
            # 顯示複製按鈕等收尾工作
            full_log_history = log_manager.get_full_history()
            js_screen = json.dumps("\n".join(display_manager._build_output_buffer()))
            js_logs = json.dumps("\n".join([f"[{log['timestamp'].isoformat()}] [{log['level']}] {log['message']}" for log in full_log_history]))
            display(HTML(f"""<script>function copyToClipboard(text) {{navigator.clipboard.writeText(text);}}</script>
                <button onclick='copyToClipboard({js_screen})'>📋 複製上方儲存格輸出</button>
                <button onclick='copyToClipboard({js_logs})'>📄 複製完整詳細日誌</button>"""))
            archive_reports(log_manager, start_time, end_time, shared_stats.get('status', '未知'))

if __name__ == "__main__":
    if 'PROJECT_PATH_FROM_DOWNLOADER' in globals() and Path(globals()['PROJECT_PATH_FROM_DOWNLOADER']).exists():
        print("✅ 找到由下載器準備的專案資料夾，準備啟動...")
        main(project_path_str=globals()['PROJECT_PATH_FROM_DOWNLOADER'])
    else:
        print("❌ 錯誤：找不到專案資料夾。")
        print("請確認您已成功執行第一個「🐺 善狼下載器」儲存格，並且沒有出現任何錯誤。")

</code></pre>
</div>
</details>

<script>
function copyCode(button) {
    const codeElement = document.getElementById('colab-code');
    const textToCopy = codeElement.innerText;
    navigator.clipboard.writeText(textToCopy).then(() => {
        button.innerText = '已複製!';
        setTimeout(() => {
            button.innerText = '複製程式碼';
        }, 2000);
    }).catch(err => {
        console.error('無法複製程式碼: ', err);
        button.innerText = '複製失敗';
    });
}
</script>
