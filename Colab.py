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
# 伺服器就緒等待超時
SERVER_READY_TIMEOUT = 120

# ==============================================================================
# SECTION 0: 環境準備與核心依賴導入
# ==============================================================================
import sys
import subprocess
import socket
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
        # --- ✨ 標題更新 ✨ ---
        output_buffer = ["🐺善狼下載啟動器🐺", ""]
        logs_to_display = self._log_manager.get_display_logs()
        for log in logs_to_display:
            ts, level = log['timestamp'].strftime('%H:%M:%S'), log['level']
            output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {log['message']}")
        if self._stats.get('proxy_url'):
            if logs_to_display: output_buffer.append("")
            output_buffer.append(f"✅ 代理連結已生成: {self._stats['proxy_url']}")
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

class ServerManager:
    """伺服器管理器：負責啟動、停止和監控 Uvicorn 子進程。"""
    def __init__(self, log_manager, stats_dict, project_path_str):
        self._log_manager = log_manager; self._stats = stats_dict
        self.project_path = Path(project_path_str)
        self.server_process = None; self.server_ready_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.port = None

    def _run(self):
        try:
            self._stats['status'] = "🚀 呼叫核心協調器..."
            self._log_manager.log("BATTLE", "=== 正在呼叫核心協調器 `orchestrator.py` ===")

            # 動態將下載專案的 src 目錄加入 sys.path
            project_src_path = self.project_path / "src"
            project_src_path_str = str(project_src_path.resolve())
            if project_src_path_str not in sys.path:
                sys.path.insert(0, project_src_path_str)

            from db.database import initialize_database, add_system_log
            initialize_database()
            add_system_log("colab_setup", "INFO", "Starting application execution.")

            # 1. 安裝輕量的核心伺服器依賴 (使用 pip)
            server_reqs_path = self.project_path / "requirements-server.txt"
            if server_reqs_path.is_file():
                self._log_manager.log("INFO", "步驟 1/3: 正在快速安裝核心伺服器依賴...")
                add_system_log("colab_setup", "INFO", "Installing server dependencies...")
                pip_command = [sys.executable, "-m", "pip", "install", "-q", "-r", str(server_reqs_path)]
                install_result = subprocess.run(pip_command, check=False, capture_output=True, text=True, encoding='utf-8')
                if install_result.returncode != 0:
                    self._log_manager.log("CRITICAL", f"核心依賴安裝失敗:\n{install_result.stderr}")
                    add_system_log("colab_setup", "CRITICAL", f"Server dependency installation failed: {install_result.stderr}")
                    return
                self._log_manager.log("SUCCESS", "✅ 核心依賴安裝完成。")
                add_system_log("colab_setup", "SUCCESS", "Server dependencies installed.")
            else:
                self._log_manager.log("WARN", "未找到 requirements-server.txt，跳過核心依賴安裝。")

            # 2. 立刻啟動核心協調器
            self._log_manager.log("INFO", "步驟 2/3: 正在啟動後端服務...")
            orchestrator_script_path = self.project_path / "src" / "core" / "orchestrator.py"
            if not orchestrator_script_path.is_file():
                self._log_manager.log("CRITICAL", f"核心協調器未找到: {orchestrator_script_path}")
                return

            port_file_path = self.project_path / "src" / "db" / "db_manager.port"
            if port_file_path.exists():
                self._log_manager.log("WARN", f"偵測到舊的埠號檔案，正在清理: {port_file_path}")
                try: port_file_path.unlink()
                except Exception as e: self._log_manager.log("ERROR", f"清理舊的埠號檔案時發生錯誤: {e}")

            launch_command = [sys.executable, "src/core/orchestrator.py", "--no-mock"]

            process_env = os.environ.copy()
            google_api_key, key_source = None, None
            try:
                key_from_secret = userdata.get('GOOGLE_API_KEY')
                if key_from_secret:
                    google_api_key, key_source = key_from_secret, "Colab Secret"
            except Exception: pass

            if not google_api_key:
                config_path = self.project_path / "config.json"
                if config_path.is_file():
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f: config_data = json.load(f)
                        key_from_config = config_data.get("GOOGLE_API_KEY")
                        api_key_placeholder = "在此處填入您的 GOOGLE API 金鑰"
                        if key_from_config and key_from_config != api_key_placeholder:
                            google_api_key, key_source = key_from_config, "config.json"
                    except Exception as e: self._log_manager.log("ERROR", f"讀取 config.json 失敗: {e}")

            if google_api_key:
                process_env['GOOGLE_API_KEY'] = google_api_key
                self._log_manager.log("SUCCESS", f"✅ 成功從 {key_source} 讀取 GOOGLE_API_KEY。")
            else:
                self._log_manager.log("WARN", "⚠️ 未找到有效的 GOOGLE_API_KEY，YouTube 相關功能可能受限。")

            src_path_str = str((self.project_path / "src").resolve())
            existing_python_path = process_env.get('PYTHONPATH', '')
            process_env['PYTHONPATH'] = f"{src_path_str}{os.pathsep}{existing_python_path}".strip(os.pathsep)

            self.server_process = subprocess.Popen(
                launch_command, cwd=str(self.project_path), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                preexec_fn=os.setsid, env=process_env
            )
            self._log_manager.log("INFO", f"協調器子進程已啟動 (PID: {self.server_process.pid})，等待握手信號...")

            # 3. 背景安裝大型依賴
            worker_reqs_path = self.project_path / "requirements-worker.txt"
            background_install_thread = threading.Thread(
                target=self._install_worker_deps, args=(worker_reqs_path,), daemon=True
            )
            background_install_thread.start()

            port_pattern = re.compile(r"PROXY_URL: http://127.0.0.1:(\d+)")
            uvicorn_ready_pattern = re.compile(r"Uvicorn running on")
            server_ready = False

            for line in iter(self.server_process.stdout.readline, ''):
                if self._stop_event.is_set(): break
                line = line.strip()
                self._log_manager.log("DEBUG", line)
                if not self.port:
                    port_match = port_pattern.search(line)
                    if port_match:
                        self.port = int(port_match.group(1))
                        self._log_manager.log("INFO", f"✅ 成功解析出 API 埠號: {self.port}")
                if not server_ready and uvicorn_ready_pattern.search(line):
                    server_ready = True
                    self._stats['status'] = "✅ 伺服器運行中"
                    self._log_manager.log("SUCCESS", "伺服器已就緒！收到 Uvicorn 握手信號！")
                if self.port and server_ready:
                    self.server_ready_event.set()

            self.server_process.wait()
            if not self.server_ready_event.is_set():
                self._stats['status'] = "❌ 伺服器啟動失敗"
                self._log_manager.log("CRITICAL", "協調器進程在就緒前已終止。")
        except Exception as e:
            self._stats['status'] = "❌ 發生致命錯誤"; self._log_manager.log("CRITICAL", f"ServerManager 執行緒出錯: {e}")
        finally:
            self._stats['status'] = "⏹️ 已停止"

    def _install_worker_deps(self, requirements_path: Path):
        try:
            self._log_manager.log("INFO", "步驟 3/3: [背景] 開始安裝大型任務依賴...")
            if not requirements_path.is_file():
                self._log_manager.log("WARN", f"[背景] 未找到 {requirements_path.name}，跳過。")
                return
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
            subprocess.run([sys.executable, "-m", "uv", "pip", "install", "-q", "-r", str(requirements_path)], check=True)
            self._log_manager.log("SUCCESS", "[背景] ✅ 所有大型任務依賴均已成功安裝！")
        except Exception as e:
            self._log_manager.log("CRITICAL", f"[背景] 安裝執行緒發生錯誤: {e}")

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

def archive_reports(log_manager, start_time, end_time, status):
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
# SECTION 3: 主程式執行入口
# ==============================================================================

def main(project_path_str: str):
    """主執行函式，負責初始化管理器、協調流程並處理生命週期。"""
    install_system_deps()
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "初始化...", "proxy_url": None}
    log_manager, display_manager, server_manager = None, None, None
    start_time = datetime.now(pytz.timezone(TIMEZONE))
    try:
        log_levels = {name: globals()[name] for name in globals() if name.startswith("SHOW_LOG_LEVEL_")}
        log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, log_levels_to_show=log_levels)
        server_manager = ServerManager(log_manager=log_manager, stats_dict=shared_stats, project_path_str=project_path_str)
        display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)

        display_manager.start()
        server_manager.start()

        if server_manager.server_ready_event.wait(timeout=SERVER_READY_TIMEOUT):
            if not server_manager.port:
                log_manager.log("CRITICAL", "伺服器已就緒，但未能解析出埠號，無法建立代理連結。")
            else:
                # --- 💡 關鍵修復：增加一個禮貌性的延遲 💡 ---
                # 在伺服器就緒後，給予 Colab 前端一個固定的緩衝時間來準備代理服務
                grace_period = 2
                log_manager.log("INFO", f"伺服器核心已就緒，等待 {grace_period} 秒讓代理服務穩定...")
                time.sleep(grace_period)

                max_retries, retry_delay = 20, 2
                for attempt in range(max_retries):
                    try:
                        log_manager.log("INFO", f"正在嘗試取得代理連結... (第 {attempt + 1}/{max_retries} 次)")
                        url = colab_output.eval_js(f'google.colab.kernel.proxyPort({server_manager.port})')

                        if url and url.strip().startswith('http'):
                            shared_stats['proxy_url'] = url
                            log_manager.log("SUCCESS", f"✅ 成功取得代理連結！埠號: {server_manager.port}")
                            break
                        else:
                            log_manager.log("WARN", f"收到無效的代理回傳值: '{str(url)[:50]}...'，將重試。")

                    except Exception as e:
                        log_manager.log("WARN", f"獲取代理連結時發生錯誤: {e}，將重試。")

                    if not shared_stats.get('proxy_url'):
                        time.sleep(retry_delay)

                if not shared_stats.get('proxy_url'):
                    shared_stats['status'] = "❌ 取得代理連結失敗"
                    log_manager.log("CRITICAL", f"在 {max_retries} 次嘗試後，仍無法取得有效的代理連結。")
        else:
            shared_stats['status'] = "❌ 伺服器啟動超時"
            log_manager.log("CRITICAL", f"伺服器在 {SERVER_READY_TIMEOUT} 秒內未能就緒。")

        while server_manager._thread.is_alive(): time.sleep(1)
    except KeyboardInterrupt:
        if log_manager: log_manager.log("WARN", "🛑 偵測到使用者手動中斷...")
    except Exception as e:
        if log_manager: log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}")
        else: print(f"❌ 發生未預期的致命錯誤: {e}")
    finally:
        if display_manager and display_manager._thread.is_alive(): display_manager.stop()
        if server_manager: server_manager.stop()
        end_time = datetime.now(pytz.timezone(TIMEZONE))
        if log_manager and display_manager:
            clear_output(); print("\n".join(display_manager._build_output_buffer()))
            print("\n--- ✅ 所有任務完成，系統已安全關閉 ---")
            full_log_history = log_manager.get_full_history()
            js_screen = json.dumps("\n".join(display_manager._build_output_buffer()))
            js_logs = json.dumps("\n".join([f"[{log['timestamp'].isoformat()}] [{log['level']}] {log['message']}" for log in full_log_history]))
            display(HTML(f"""<script>function copyToClipboard(text) {{navigator.clipboard.writeText(text);}}</script>
                <button onclick='copyToClipboard({js_screen})'>📋 複製上方儲存格輸出</button>
                <button onclick='copyToClipboard({js_logs})'>📄 複製完整詳細日誌</button>"""))
            archive_reports(log_manager, start_time, end_time, shared_stats.get('status', '未知'))

if __name__ == "__main__":
    # 檢查第一個儲存格是否已成功執行並設定了專案路徑
    if 'PROJECT_PATH_FROM_DOWNLOADER' in globals() and Path(globals()['PROJECT_PATH_FROM_DOWNLOADER']).exists():
        print("✅ 找到由下載器準備的專案資料夾，準備啟動...")
        main(project_path_str=globals()['PROJECT_PATH_FROM_DOWNLOADER'])
    else:
        print("❌ 錯誤：找不到專案資料夾。")
        print("請確認您已成功執行第一個「🐺 善狼下載器」儲存格，並且沒有出現任何錯誤。")
