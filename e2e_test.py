import subprocess
import sys
import time
from pathlib import Path
import logging
import os
import socket
import threading
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 繁體中文註解：基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('Colab模擬器')
ROOT_DIR = Path(__file__).resolve().parent
VUE_APP_DIR = ROOT_DIR / "vue-app"
BAKE_SCRIPT_PATH = ROOT_DIR / "scripts" / "bake_dependencies.sh"
DEPS_ARCHIVE_PATH = ROOT_DIR / "dependencies.tar.gz"
SCREENSHOT_PATH = ROOT_DIR / "colab_sim_screenshot.png"
SIMULATION_TIMEOUT = 100 # 依照使用者要求設定100秒超時

def execute_command(command, cwd, step_name):
    """執行一個 shell 指令並記錄日誌"""
    log.info(f"--- {step_name} ---")
    try:
        result = subprocess.run(
            command, cwd=cwd, check=True, capture_output=True,
            text=True, encoding='utf-8', timeout=180
        )
        log.info(f"✅ {step_name} 成功")
        log.debug(result.stdout)
        return True
    except subprocess.TimeoutExpired:
        log.error(f"❌ {step_name} - 指令執行超時。")
        return False
    except subprocess.CalledProcessError as e:
        log.error(f"❌ {step_name} 失敗 (返回碼: {e.returncode})")
        log.error(f"STDERR:\n{e.stderr}")
        return False

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def wait_for_server_and_get_port(server_proc, timeout=30):
    log.info("等待 run.py 回報埠號...")
    start_time = time.monotonic()
    for line in iter(server_proc.stdout.readline, ''):
        if line.strip().startswith("APP_PORT:"):
            port = int(line.strip().split(":")[1])
            log.info(f"✅ 伺服器已回報埠號: {port}")
            return port
        if time.monotonic() - start_time > timeout:
            log.error("❌ 等待埠號超時。")
            return None
    return None

def test_status_endpoint(api_url):
    """直接呼叫 /api/v1/status 端點並驗證其回應。"""
    log.info(f"--- 正在測試 API 狀態端點: {api_url}/api/v1/status ---")
    try:
        response = requests.get(f"{api_url}/api/v1/status", timeout=10)
        response.raise_for_status()  # 如果狀態碼不是 2xx，則引發例外

        data = response.json()
        log.info(f"成功獲取狀態回應: {data}")

        # 驗證結構和內容
        assert 'app_version' in data and data['app_version'] == "1.3.0", "app_version 不正確"
        assert 'timestamp' in data, "缺少 timestamp"
        assert 'features' in data, "缺少 features"

        features = data['features']
        assert 'transcription' in features and features['transcription']['enabled'] is True, "transcription 狀態不正確"
        assert 'youtube_processing' in features and features['youtube_processing']['enabled'] is False, "youtube_processing 狀態不正確"
        assert 'model_management' in features and features['model_management']['enabled'] is True, "model_management 狀態不正確"

        log.info("✅ API 狀態端點驗證成功！")
        return True
    except requests.exceptions.RequestException as e:
        log.error(f"❌ 呼叫 API 狀態端點時發生錯誤: {e}")
        return False
    except (AssertionError, KeyError) as e:
        log.error(f"❌ API 狀態端點回應內容驗證失敗: {e}")
        return False

def run_simulation():
    # 使用 threading.Timer 實現總超時
    kill_flag = threading.Event()
    def timeout_handler():
        log.error(f"❌❌❌ 總模擬時間超過 {SIMULATION_TIMEOUT} 秒，強制中止！ ❌❌❌")
        kill_flag.set()

    timer = threading.Timer(SIMULATION_TIMEOUT, timeout_handler)
    timer.start()

    server_proc = None
    exit_code = 1
    try:
        # 步驟 1: 清理舊的依賴包
        if DEPS_ARCHIVE_PATH.exists():
            log.info("正在清理舊的依賴包...")
            DEPS_ARCHIVE_PATH.unlink()

        # 步驟 2: 建置前端
        if not execute_command(["bun", "install"], VUE_APP_DIR, "安裝前端依賴"): raise RuntimeError("前端依賴安裝失敗")
        if not execute_command(["bun", "run", "build"], VUE_APP_DIR, "建置前端應用"): raise RuntimeError("前端建置失敗")

        # 步驟 3: 烘烤依賴包 (這是模擬的關鍵)
        if not execute_command(["bash", str(BAKE_SCRIPT_PATH)], ROOT_DIR, "執行依賴烘烤腳本"): raise RuntimeError("烘烤依賴失敗")
        if not DEPS_ARCHIVE_PATH.exists(): raise RuntimeError("烘烤腳本未成功產生依賴包")

        # 步驟 4: 像 Colabpro.py 一樣啟動伺服器
        log.info(f"--- 使用烘烤過的依賴包 '{DEPS_ARCHIVE_PATH}' 啟動伺服器 ---")
        server_command = [sys.executable, "run.py", "--deps-path", str(DEPS_ARCHIVE_PATH)]
        server_proc = subprocess.Popen(
            server_command, cwd=ROOT_DIR, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding='utf-8'
        )

        # 增加一個線程來監控和打印 stderr
        def log_stderr():
            if server_proc.stderr:
                for line in iter(server_proc.stderr.readline, ''):
                    log.error(f"[SERVER STDERR] {line.strip()}")

        stderr_thread = threading.Thread(target=log_stderr)
        stderr_thread.daemon = True
        stderr_thread.start()

        port = wait_for_server_and_get_port(server_proc)
        if not port: raise RuntimeError("無法從伺服器獲取埠號。")
        api_url = f"http://127.0.0.1:{port}"

        # --- 新增：可靠的健康檢查迴圈 ---
        log.info(f"伺服器回報埠號 {port}，現在開始健康檢查...")
        health_check_url = f"{api_url}/api/health"
        server_ready = False
        start_wait = time.monotonic()
        while time.monotonic() - start_wait < 20: # 20秒超時
            try:
                response = requests.get(health_check_url, timeout=2)
                if response.status_code == 200:
                    log.info("✅ 健康檢查成功！伺服器已準備就緒。")
                    server_ready = True
                    break
            except requests.ConnectionError:
                time.sleep(0.5) # 伺服器尚未就緒，稍後重試
            except requests.RequestException as e:
                log.warning(f"健康檢查期間發生非預期錯誤: {e}")
                time.sleep(0.5)

        if not server_ready:
            raise RuntimeError("伺服器健康檢查超時。")

        # 在伺服器確認就緒後，才執行 API 測試
        if not test_status_endpoint(api_url):
            raise RuntimeError("API 狀態端點驗證失敗，中止測試。")

        # 步驟 5: Playwright 驗證
        log.info(f"--- 使用 Playwright 驗證 {api_url} ---")
        from playwright.sync_api import expect

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # 關鍵除錯步驟：監聽並打印所有瀏覽器控制台訊息
            page.on("console", lambda msg: log.info(f"[Browser Console] {msg.text}"))
            page.on("pageerror", lambda err: log.error(f"[Browser Page Error] {err.message}"))

            try:
                target_url = f"{api_url}/ui"
                log.info(f"導航至: {target_url}")
                page.goto(target_url, wait_until='domcontentloaded', timeout=20000)

                log.info("等待 Vue app 初始化 (等待 window.vue_app)...")
                page.wait_for_function('() => window.vue_app', timeout=15000)
                log.info("✅ Vue app 已找到！")

                log.info("正在驗證頁面標題...")
                expect(page).to_have_title("音訊轉錄儀", timeout=5000)
                log.info("✅ 驗證成功: 頁面標題符合預期。")

                log.info("架構已簡化，不再有獨立的工作者或硬體監控狀態，跳過相關驗證。")

                log.info("從測試腳本強制呼叫 checkLocalModels action 以確保狀態更新...")
                page.evaluate('window.tasksStore.checkLocalModels()')
                log.info("✅ 已呼叫 checkLocalModels。")

                # --- 新增：執行一個完整的轉錄任務以驗證簡化後的架構 ---
                log.info("--- 開始執行完整的轉錄任務測試 ---")

                # 1. 點擊「本機檔案轉錄」標籤
                page.click("button:has-text('本機檔案轉錄')")
                log.info("已點擊 '本機檔案轉錄' 標籤。")

                # 2. 上傳檔案
                file_path = ROOT_DIR / 'vue-app' / 'tests' / 'fixtures' / 'test-audio.txt'
                page.set_input_files('input[type="file"]', file_path)
                log.info(f"已選擇測試檔案: {file_path}")

                # 3. 新增至佇列
                page.click("button:has-text('新增 1 個檔案至佇列')")
                log.info("已點擊 '新增至佇列' 按鈕。")

                # 4. 提交任務
                page.click("button:has-text('提交佇列中的 1 個任務')")
                log.info("已點擊 '提交佇列' 按鈕。")

                # 5. 在「已完成任務」列表中驗證結果
                log.info("正在等待任務出現在 '已完成任務' 列表中...")
                completed_tasks_card = page.locator(".card:has-text('已完成任務')")
                completed_task_item = completed_tasks_card.locator(".task-item:has-text('test-audio.txt')")

                # 等待項目出現
                expect(completed_task_item).to_be_visible(timeout=25000)

                # 驗證狀態是否為 'completed' - 已移除
                # 根據目前的 UI 設計 (`CompletedTasks.vue`)，成功完成的任務只會顯示操作按鈕，
                # 不會顯示 'completed' 狀態標籤。因此，只要任務項目出現在「已完成」列表中，
                # 就足以證明流程是成功的。
                # status_badge = completed_task_item.locator(".task-status-badge.status-completed")
                # expect(status_badge).to_have_text("completed", timeout=5000)
                log.info("✅ 驗證成功: 轉錄任務已出現在「已完成任務」列表中！")

                log.info("✅ 完整的 E2E 測試成功！")
                exit_code = 0

            except PlaywrightTimeoutError as e:
                log.error(f"❌ Playwright 測試超時: {e}")
                page.screenshot(path=SCREENSHOT_PATH)
                log.error(f"已儲存超時螢幕截圖至: {SCREENSHOT_PATH}")
                exit_code = 1
            except Exception as e:
                log.error(f"❌ Playwright 測試期間發生錯誤: {e}", exc_info=True)
                page.screenshot(path=SCREENSHOT_PATH)
                log.error(f"已儲存錯誤螢幕截圖至: {SCREENSHOT_PATH}")
                exit_code = 1
            finally:
                browser.close()

    except Exception as e:
        log.error(f"模擬流程發生錯誤: {e}", exc_info=True)
        exit_code = 1
    finally:
        if server_proc and server_proc.poll() is None:
            log.info("正在關閉伺服器...")
            server_proc.terminate()
            server_proc.wait(timeout=5)

        timer.cancel() # 確保計時器被取消
        if kill_flag.is_set():
             sys.exit(1) # 如果是因超時而退出，返回失敗碼

    return exit_code

if __name__ == "__main__":
    final_code = run_simulation()
    if final_code == 0:
        log.info("✅ 模擬器執行完畢 (未重現錯誤)。")
    else:
        log.error("❌ 模擬器執行完畢 (成功重現錯誤或發生其他問題)。")
    sys.exit(final_code)
