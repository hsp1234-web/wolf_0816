# -*- coding: utf-8 -*-
import sys
import os
from pathlib import Path
import shutil
import traceback
import time
import multiprocessing
from unittest.mock import patch

# --- 步驟 1: 設定環境 ---
# 將專案根目錄加入到 Python 的搜尋路徑中，以便腳本可以找到 Colabpro.py
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
    print(f"將根目錄 {ROOT_DIR} 加入到 sys.path")

# 設定環境變數，告知 Colabpro.py 我們在測試模式下
os.environ['IN_TEST_MODE'] = '1'

# --- 步驟 2: 安全地匯入 Colabpro ---
# 在匯入時，Colabpro.py 內部的 _setup_colab_mocks() 會自動執行，
# 並建立一個基礎的、功能不全的 google.colab 模擬模組。
try:
    import Colabpro
except Exception as e:
    print(f"❌ 匯入 Colabpro.py 失敗: {e}", file=sys.stderr)
    sys.exit(1)

# --- 步驟 3: 建立一個智慧的 eval_js 模擬函式 ---
# 這個函式是修復此問題的關鍵。它需要根據收到的 JavaScript 程式碼提供不同的回應。
def smart_eval_js(js_code, *args, **kwargs):
    """一個模擬的 eval_js，能應對健康檢查和代理請求。"""
    print(f"[MOCK eval_js] 收到請求: {js_code[:80]}...")

    # 回應健康檢查
    if js_code == "'pong'":
        print("[MOCK eval_js] -> 回應健康檢查: 'pong'")
        return "pong"  # 健康檢查期待的是字串 'pong'

    # 回應代理埠號（proxy port）請求
    if "google.colab.kernel.proxyPort" in js_code:
        try:
            # 從請求中解析出埠號，以建立一個逼真的假 URL
            port = js_code.split('(')[1].split(',')[0]
            url = f"http://fake-test-url-from-colab:{port}"
            print(f"[MOCK eval_js] -> 回應代理埠號請求: '{url}'")
            return url
        except Exception:
            # 如果解析失敗，回傳一個通用 URL
            return "http://generic-fake-test-url:8888"

    print(f"[MOCK eval_js] -> 未知的請求，回應 None")
    return None

# --- 步驟 4: 加入超時監控邏輯 ---

# 為了監控日誌輸出，我們需要一個能跨進程共享狀態的 DisplayManager
class MonitoredDisplayManager(Colabpro.DisplayManager):
    """一個特製的 DisplayManager，每次記錄日誌時會更新一個共享的時間戳。"""
    def __init__(self, last_log_time_value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 這個 last_log_time_value 是一個 multiprocessing.Value，可以在進程間共享
        self.last_log_time = last_log_time_value
        # 立即更新一次時間，避免啟動時就因空閒而超時
        self.last_log_time.value = time.time()

    def log(self, level, message):
        super().log(level, message)
        # 每次呼叫 log 方法，都更新共享的時間戳
        self.last_log_time.value = time.time()

def application_target(last_log_time, project_path_str):
    """這個函式將在一個獨立的進程中執行，負責啟動應用程式。"""
    # 建立一個 DisplayManager 的實例，這是 launch_application 的必要參數
    display_manager = MonitoredDisplayManager(last_log_time, stats_dict={}, refresh_rate=0.2)

    # 我們需要模擬兩個外部依賴：
    # 1. `eval_js`: 用於通過健康檢查。
    # 2. `HAProxyGetter.get_urls`: 用於避免下載大型二進位檔案 (如 cloudflared)。
    try:
        with patch('google.colab.output.eval_js', side_effect=smart_eval_js), \
             patch('Colabpro.HAProxyGetter.get_urls', return_value=[('Mocked Tunnel', 'http://mocked.url/for-test')]) as mock_get_urls:

            print("\n🚀 已替換 eval_js 和 get_urls，即將呼叫 Colabpro.launch_application...")
            # 直接呼叫核心功能，傳入假的路徑和日誌管理器
            Colabpro.launch_application(
                project_path_str=project_path_str,
                log_manager=display_manager
            )
    except Exception:
        # launch_application 內部會處理多數預期內的退出（如 KeyboardInterrupt）
        # 如果有未預期的錯誤洩漏出來，我們在此捕獲並回報。
        print(f"\n--- ❌ 測試執行期間發生未預期的錯誤 ---")
        traceback.print_exc()

# --- 步驟 5: 準備測試環境並執行 ---
def run_test_with_timeout():
    """執行完整測試流程的主函式，並帶有超時監控。"""
    print("\n--- Colabpro.py 本地整合測試啟動 (含超時監控) ---")

    # 為了完全繞過 Git 下載，我們手動建立一個假的專案目錄
    fake_project_path = ROOT_DIR / "FAKE_PROJECT_FOR_TEST"
    if fake_project_path.exists():
        shutil.rmtree(fake_project_path)
    fake_project_path.mkdir()
    print(f"建立假的專案目錄: {fake_project_path}")

    # Colabpro.launch_application 會尋找並執行 run_app.py，所以我們建立一個假的腳本
    # 這個假腳本模擬真實應用程式的行為：報告埠號，然後長時間睡眠以測試超時。
    fake_run_app_script = fake_project_path / "run_app.py"
    fake_run_app_script.write_text(
        "import time\n"
        "print('APP_URL:http://127.0.0.1:7860', flush=True)\n"
        "print('假的應用程式啟動成功，將在 180 秒後退出 (以測試超時)...', flush=True)\n" # 執行時間要比總超時長
        "time.sleep(180)\n"
        "print('假的應用程式正常關閉。', flush=True)\n",
        encoding='utf-8'
    )
    print(f"已建立假的 run_app.py 以供測試")

    # 建立一個跨進程共享的變數來儲存最後日誌時間
    last_log_time = multiprocessing.Value('d', time.time())

    # 建立並啟動子進程
    process = multiprocessing.Process(
        target=application_target,
        args=(last_log_time, str(fake_project_path))
    )
    process.start()
    print(f"✅ 子進程已啟動 (PID: {process.pid})，開始監控...")

    start_time = time.time()
    TOTAL_TIMEOUT = 120  # 總超時 120 秒
    IDLE_TIMEOUT = 20   # 無日誌輸出超時 20 秒

    try:
        while process.is_alive():
            # 檢查總時間是否超時
            if time.time() - start_time > TOTAL_TIMEOUT:
                print(f"⏰ 偵測到總執行時間超時（超過 {TOTAL_TIMEOUT} 秒），正在終止進程...")
                process.terminate()
                break

            # 檢查是否因無日誌輸出而空閒超時
            if time.time() - last_log_time.value > IDLE_TIMEOUT:
                print(f"⏰ 偵測到日誌輸出空閒超時（超過 {IDLE_TIMEOUT} 秒），正在終止進程...")
                process.terminate()
                break

            time.sleep(1) # 每秒檢查一次

        process.join(timeout=5) # 等待進程終止
        if process.is_alive():
             print("⚠️ 進程無法正常終止，將強制結束。")
             process.kill()

    except KeyboardInterrupt:
        print("\n收到手動中斷，正在清理...")
        process.terminate()
    finally:
        # 測試結束後，清理我們建立的假專案目錄
        if fake_project_path.exists():
            shutil.rmtree(fake_project_path)
            print(f"清理並刪除假的專案目錄: {fake_project_path}")
        print("\n--- Colabpro.py 本地整合測試結束 ---")

if __name__ == "__main__":
    # 需要設定好多進程的啟動方式，以避免在某些作業系統上出錯
    # 在 Colab 或類似的 Jupyter 環境中，'fork' 是較佳的選擇
    try:
        multiprocessing.set_start_method('fork', force=True)
    except RuntimeError:
        # 如果 'fork' 已被設定，或環境不支援，則忽略
        pass
    run_test_with_timeout()
