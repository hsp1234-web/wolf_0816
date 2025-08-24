# -*- coding: utf-8 -*-
import sys
import os
from pathlib import Path
import shutil
import traceback
import time
import multiprocessing
from unittest.mock import patch, MagicMock

# --- 步驟 1: 設定環境 ---
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
    print(f"將根目錄 {ROOT_DIR} 加入到 sys.path")

os.environ['IN_TEST_MODE'] = '1'

try:
    import Colabpro
except Exception as e:
    print(f"❌ 匯入 Colabpro.py 失敗: {e}", file=sys.stderr)
    sys.exit(1)

# --- 步驟 2: 智慧的模擬函式 ---
def smart_eval_js(js_code, *args, **kwargs):
    if js_code == "'pong'": return "pong"
    if "google.colab.kernel.proxyPort" in js_code:
        port = js_code.split('(')[1].split(',')[0]
        return f"http://fake-test-url-from-colab:{port}"
    return None

# --- 步驟 3: 改造後的測試目標函式 ---
def application_target(last_log_time):
    """這個函式將在一個獨立的進程中執行，負責完整地模擬 Colabpro.py 的啟動流程。"""

    # 建立一個可監控的 DisplayManager
    display_manager = MonitoredDisplayManager(last_log_time, stats_dict={}, refresh_rate=0.2)

    try:
        # 我們需要模擬所有會產生外部互動的函式
        with patch('google.colab.output.eval_js', side_effect=smart_eval_js), \
             patch('Colabpro.HAProxyGetter.get_urls', return_value=[{'method': 'Mocked Tunnel', 'url': 'http://mocked.url/for-test'}]), \
             patch('sys.executable', 'python'): # 確保 subprocess 使用正確的 python

            print("\n🚀 已設定模擬 (mock)，即將開始測試 `download_repository`...")

            # 核心測試邏輯：
            # 1. 呼叫 download_repository
            project_path = Colabpro.download_repository(log_manager=display_manager)

            # 2. 驗證其回傳值是否為 "."
            print(f"🔍 `download_repository` 回傳的路徑: '{project_path}'")
            if project_path != ".":
                raise AssertionError(f"驗證失敗！預期路徑為 '.'，但實際為 '{project_path}'")
            print("✅ 驗證成功: `download_repository` 正確回傳了 '.'。")

            # 3. 如果驗證成功，繼續呼叫 launch_application
            if project_path:
                Colabpro.launch_application(
                    project_path_str=project_path,
                    log_manager=display_manager
                )

    except Exception:
        print(f"\n--- ❌ 測試執行期間發生未預期的錯誤 ---")
        traceback.print_exc()

# --- 步驟 4: 加入超時監控邏輯 (與原版類似) ---
class MonitoredDisplayManager(Colabpro.DisplayManager):
    def __init__(self, last_log_time_value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_log_time = last_log_time_value
        self.last_log_time.value = time.time()

    def log(self, level, message):
        # 在測試中，我們希望看到所有日誌，所以直接 print
        now = time.strftime('%H:%M:%S')
        print(f"[{now}] [{level.upper():^8}] {message}")
        super().log(level, message)
        self.last_log_time.value = time.time()

# --- 步驟 5: 準備測試環境並執行 (改造版) ---
def run_test_with_timeout():
    print("\n--- Colabpro.py 環境適應性整合測試 ---")

    # 為了測試我們的修復，我們需要一個假的 run_app.py 在根目錄
    # 但我們不能汙染真實的 run_app.py。所以我們先將其改名，測試完再改回來。
    real_run_app_path = ROOT_DIR / "run_app.py"
    temp_run_app_path = ROOT_DIR / "run_app.py.bak"
    fake_run_app_created = False
    process = None # 在 try 區塊外初始化

    try:
        # 將真實的 run_app.py 改名為 .bak
        if real_run_app_path.exists():
            os.rename(real_run_app_path, temp_run_app_path)
            print(f"暫時將 '{real_run_app_path}' 改名為 '{temp_run_app_path}'")

        # 建立一個假的 run_app.py，它只會報告埠號然後等待
        real_run_app_path.write_text(
            "import time, sys\n"
            "print('APP_URL:http://127.0.0.1:7860', flush=True)\n"
            "sys.stdout.flush()\n"
            "time.sleep(180)\n",
            encoding='utf-8'
        )
        fake_run_app_created = True
        print(f"已建立假的 'run_app.py' 用於測試。")

        # --- 執行監控 ---
        last_log_time = multiprocessing.Value('d', time.time())
        process = multiprocessing.Process(target=application_target, args=(last_log_time,))
        process.start()
        print(f"✅ 子進程已啟動 (PID: {process.pid})，開始監控...")

        start_time = time.time()
        TOTAL_TIMEOUT = 60
        IDLE_TIMEOUT = 20

        while process.is_alive():
            if time.time() - start_time > TOTAL_TIMEOUT:
                print(f"⏰ 偵測到總執行時間超時（超過 {TOTAL_TIMEOUT} 秒），正在終止進程...")
                process.terminate()
                break
            if time.time() - last_log_time.value > IDLE_TIMEOUT:
                print(f"⏰ 偵測到日誌輸出空閒超時（超過 {IDLE_TIMEOUT} 秒），正在終止進程...")
                process.terminate()
                break
            time.sleep(1)

        process.join(timeout=5)
        if process.is_alive():
             process.kill()

        # 檢查子進程的退出碼
        if process.exitcode == 0:
            print("\n✅ 測試成功: 子進程正常結束。")
        else:
            print(f"\n❌ 測試失敗: 子進程以錯誤碼 {process.exitcode} 結束。")
            raise RuntimeError("測試子進程執行失敗！")

    except KeyboardInterrupt:
        print("\n收到手動中斷，正在清理...")
        if process and process.is_alive(): process.terminate()
    finally:
        # --- 清理環境 ---
        if fake_run_app_created:
            if real_run_app_path.exists():
                os.remove(real_run_app_path)
                print(f"已刪除假的 'run_app.py'")
        if temp_run_app_path.exists():
            os.rename(temp_run_app_path, real_run_app_path)
            print(f"已將 '{real_run_app_path}' 還原。")
        print("\n--- Colabpro.py 整合測試結束 ---")

if __name__ == "__main__":
    try:
        multiprocessing.set_start_method('fork', force=True)
    except RuntimeError:
        pass
    run_test_with_timeout()
