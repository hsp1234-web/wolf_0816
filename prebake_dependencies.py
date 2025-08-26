#@title 🛠️ 依賴包預烘烤產生器 (v1.0)
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請確認 Git 專案已下載到 Colab 環境中。**
PROJECT_FOLDER_NAME = "wolf_project" #@param {type:"string"}
#@markdown ---
#@markdown ### **(2) 輸出設定**
#@markdown > **設定產出的依賴包名稱。**
OUTPUT_FILENAME = "dependencies.tar.gz" #@param {type:"string"}
#@markdown ---
#@markdown > **確認設定後，點擊「執行」按鈕開始。**
#@markdown ---

import subprocess
import sys
import os
import time
import threading
from pathlib import Path
from collections import deque
from datetime import datetime

# --- 環境設定 ---
# 模擬 Colab 環境以便在本地測試
try:
    from google.colab import output as colab_output
    from IPython.display import display, HTML, clear_output as ipy_clear_output
    import pytz
    IN_COLAB = True
except ImportError:
    class MockColab:
        def clear_output(self, wait=False): print("\n--- 清除輸出 ---\n")
    ipy_clear_output = MockColab().clear_output
    # Mock pytz if not available
    class MockPytz:
        def timezone(self, tz_str):
            from datetime import timezone, timedelta
            return timezone(timedelta(hours=8)) # Assume UTC+8 for tests
    pytz = MockPytz()
    IN_COLAB = False
    print("警告：未在 Colab 環境中執行，將使用模擬的 display 功能。")

# --- UI 與日誌管理器 ---
# 顏色代碼，用於美化輸出
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
GRAY = '\033[90m'

class UIManager:
    """一個簡單的 UI 管理器，用於顯示動態刷新的儀表板。"""
    def __init__(self, log_lines=20):
        self.start_time = time.monotonic()
        self.status = "初始化..."
        self.log_deque = deque(maxlen=log_lines)

    def log(self, message):
        """記錄一條訊息到日誌隊列。"""
        now = datetime.now(pytz.timezone('Asia/Taipei')).strftime('%H:%M:%S')
        for line in message.split('\n'):
            if line:
                self.log_deque.append(f"{GRAY}[{now}]{RESET} {line}")

    def set_status(self, status):
        """設定目前的狀態文字。"""
        self.status = status
        self.log(f"狀態變更 -> {status}")

    def print_ui(self):
        """打印整個 UI 到主控台。"""
        if IN_COLAB:
            ipy_clear_output(wait=True)

        elapsed = time.monotonic() - self.start_time
        mins, secs = divmod(elapsed, 60)

        print("--- 🛠️ 依賴包預烘烤產生器 ---")
        print(f"⏱️ 已執行時間: {int(mins):02d}分{int(secs):02d}秒 | 🔥 狀態: {self.status}")
        print("-" * 30)
        print("\n".join(self.log_deque))

# --- 核心函式 ---
def run_command_realtime(command, ui_manager, cwd=None):
    """
    執行一個 shell 指令，並將其輸出即時傳遞給 UI 管理器。
    """
    ui_manager.log(f"▶️  執行: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        bufsize=1
    )

    for line in iter(process.stdout.readline, ''):
        ui_manager.log(line.strip())

    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command)

def main():
    """主執行流程"""
    ui = UIManager()
    ui.print_ui()

    try:
        # --- 步驟 0: 檢查環境 ---
        ui.set_status("檢查環境中...")
        base_dir = Path("/content") if IN_COLAB else Path.cwd()
        project_dir = base_dir / PROJECT_FOLDER_NAME
        build_dir = base_dir / "_build_prebake"
        deps_dir = build_dir / "deps"
        output_archive = base_dir / OUTPUT_FILENAME

        if not project_dir.is_dir():
            raise FileNotFoundError(f"錯誤：專案目錄 '{project_dir}' 不存在。請先執行 Colabpro.py 的第一部分來下載專案。")
        ui.log(f"專案目錄 '{project_dir}' 已找到。")

        # --- 步驟 1: 寫入需求檔案 ---
        ui.set_status("準備依賴清單...")
        requirements_file = base_dir / "temp_requirements_prebake.txt"
        requirements_content = """
fastapi
uvicorn
httpx
pytest
trio
python-multipart
pytz
jsonpatch
requests
websockets
pydantic-settings
psutil
torch
faster-whisper
opencc-python-reimplemented
"""
        requirements_file.write_text(requirements_content.strip())
        ui.log(f"已建立暫存需求檔案: {requirements_file.name}")

        # --- 步驟 2: 建立暫存目錄 ---
        ui.set_status("建立建置目錄...")
        if build_dir.exists():
            run_command_realtime(["rm", "-rf", str(build_dir)], ui)
        deps_dir.mkdir(parents=True, exist_ok=True)
        ui.log(f"已建立暫存目錄: {deps_dir}")

        # --- 步驟 3: 安裝 uv ---
        ui.set_status("檢查/安裝 uv...")
        try:
            run_command_realtime(["uv", "--version"], ui)
        except (subprocess.CalledProcessError, FileNotFoundError):
            ui.log("uv 未找到，正在透過 pip 安裝...")
            run_command_realtime([sys.executable, "-m", "pip", "install", "-q", "uv"], ui)

        # --- 步驟 4: 安裝依賴 ---
        ui.set_status("安裝 Python 依賴 (此步驟耗時較長)...")
        # 啟動一個執行緒來定期刷新 UI
        stop_event = threading.Event()
        def ui_refresher():
            while not stop_event.is_set():
                ui.print_ui()
                time.sleep(0.5)

        refresher_thread = threading.Thread(target=ui_refresher)
        refresher_thread.start()

        try:
            run_command_realtime([
                "uv", "pip", "install",
                "-r", str(requirements_file),
                "--target", str(deps_dir)
            ], ui)
        finally:
            stop_event.set()
            refresher_thread.join()

        ui.print_ui() # 最終打印一次以顯示所有日誌

        # --- 步驟 5: 複製原始碼 ---
        ui.set_status("複製專案原始碼...")
        for subdir in ["src", "services", "workers", "vue-app", "youtube_downloads"]:
            source = project_dir / subdir
            if source.is_dir():
                run_command_realtime(["cp", "-r", str(source), str(deps_dir)], ui)
            else:
                ui.log(f"警告: 來源目錄 '{source}' 不存在，跳過。")

        # --- 步驟 6: 打包 ---
        ui.set_status("打包成 .tar.gz...")
        run_command_realtime([
            "tar", "-czf", str(output_archive),
            "-C", str(deps_dir), "."
        ], ui)

        # --- 完成 ---
        ui.set_status("全部完成！")
        ui.print_ui()
        print("\n" + "="*60)
        print(f"{GREEN}✅  成功！依賴包已成功建立。{RESET}")
        print(f"   檔案路徑: {GREEN}{output_archive}{RESET}")
        print("   您現在可以將此檔案上傳到 Google Drive 以供未來快速取用。")
        print("="*60 + "\n")

    except Exception as e:
        ui.set_status("發生錯誤！")
        ui.log(f"❌ 錯誤: {e}")
        ui.print_ui()
        # 打印更詳細的錯誤追蹤
        import traceback
        traceback.print_exc()
    finally:
        # 清理暫存檔案
        if 'requirements_file' in locals() and requirements_file.exists():
            requirements_file.unlink()
        if 'build_dir' in locals() and build_dir.exists():
            ui.log("正在清理暫存建置目錄...")
            # 使用 subprocess.run 以避免污染 UI 的最後輸出
            subprocess.run(["rm", "-rf", str(build_dir)], capture_output=True)
            ui.print_ui()

# --- 執行主函式 ---
if __name__ == "__main__":
    main()
