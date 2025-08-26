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
SIMULATION_TIMEOUT = 200 # 增加超時以容納模型下載

def execute_command(command, cwd, step_name):
    """執行一個 shell 指令並記錄日誌"""
    log.info(f"--- {step_name} ---")
    try:
        result = subprocess.run(
            command, cwd=cwd, check=True, capture_output=True,
            text=True, encoding='utf-8', timeout=600
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

def test_websocket_echo(page, expect, api_url):
    """測試 WebSocket echo 功能。"""
    log.info("--- 開始執行 WebSocket Echo 驗證測試 ---")
    debug_url = f"{api_url}/debug/ws"
    page.goto(debug_url, wait_until='domcontentloaded', timeout=10000)
    log.info(f"已導航至診斷頁面: {debug_url}")

    # 驗證連線成功
    status_div = page.locator("#status")
    expect(status_div).to_have_text("連線成功 (OPEN)", timeout=15000)
    log.info("✅ WebSocket 連線成功。")

    # 發送 Ping
    test_message = f"Hello from Playwright at {time.time()}"
    page.fill("#ping-message", test_message)
    page.click("#send-ping")
    log.info(f"已發送 Ping: '{test_message}'")

    # 驗證 Pong 回應
    log_container = page.locator("#log-container")
    # 等待包含 ECHO_RESPONSE 和我們的測試訊息的日誌條目
    response_entry = log_container.locator(f".log-entry:has-text('onmessage')").filter(
        has=page.locator(f".log-data:has-text('{test_message}')")
    )
    expect(response_entry).to_be_visible(timeout=10000)
    log.info("✅ 成功收到並驗證 Echo 回應！")
    return True

def test_transcription_output(page, expect):
    """執行一個完整的轉錄任務，並驗證其輸出內容。"""
    log.info("--- 開始執行轉錄輸出驗證測試 ---")

    # 1. 導航到轉錄分頁
    page.click("button:has-text('本機檔案轉錄')")
    log.info("已點擊 '本機檔案轉錄' 標籤。")

    # 2. 設定參數
    page.select_option('[data-testid="model-selector"]', "tiny")
    log.info("已選擇模型: tiny")
    page.fill("#beam-size-input", "1")
    log.info("已設定光束大小: 1")

    # 3. 上傳檔案
    file_path = ROOT_DIR / 'vue-app' / 'tests' / 'fixtures' / 'test-audio.txt'
    page.set_input_files('[data-testid="file-input"]', file_path)
    log.info(f"已選擇測試檔案: {file_path}")

    # 4. 新增至佇列並提交
    page.click('[data-testid="add-to-queue-button"]')
    log.info("已點擊 '新增至佇列' 按鈕。")
    page.click('[data-testid="submit-queue-button"]')
    log.info("已點擊 '提交佇列' 按鈕。")

    # 5. 等待任務完成並點擊預覽
    log.info("正在等待任務出現在 '已完成任務' 列表中...")
    completed_task_item = page.locator(".task-item:has-text('test-audio.txt')")
    expect(completed_task_item).to_be_visible(timeout=30000)
    log.info("任務已出現在「已完成」列表中。")

    preview_button = completed_task_item.locator("a.btn-preview:has-text('預覽')")
    preview_button.click()
    log.info("已點擊 '預覽' 按鈕。")

    # 6. 驗證預覽 Modal 中的內容
    log.info("正在驗證預覽 Modal 的內容...")
    modal = page.locator(".modal-content")
    expect(modal).to_be_visible(timeout=5000)

    expected_text = "這是 'test-audio.txt' 的模擬轉錄結果。"
    # 定位到 <pre> 標籤並驗證其文字內容
    transcription_output = modal.locator("pre")
    expect(transcription_output).to_have_text(expected_text, timeout=5000)

    log.info("✅ 驗證成功: 預覽 Modal 中的轉錄文字符合預期！")

    # 關閉 Modal
    modal.locator("button.modal-close-button").click()
    expect(modal).not_to_be_visible(timeout=5000)
    log.info("已關閉預覽 Modal。")
    return True

def test_model_download(page, expect):
    """測試模型下載功能。"""
    log.info("--- 開始執行模型下載驗證測試 ---")

    # 1. 導航到轉錄分頁
    page.click("button:has-text('本機檔案轉錄')")

    # 2. 選擇一個預期不存在的模型
    model_to_download = "base"
    page.select_option('[data-testid="model-selector"]', model_to_download)
    log.info(f"已選擇模型: {model_to_download}")

    # 3. 驗證下載按鈕的初始狀態
    download_button = page.locator('[data-testid="download-model-button"]')
    # 在執行 checkLocalModels 之後，按鈕文字會是 "下載模型"
    expect(download_button).to_have_text("📥 下載模型", timeout=10000)
    expect(download_button).to_be_enabled()
    log.info("✅ 驗證成功: 下載按鈕處於正確的初始狀態。")

    # 4. 點擊下載
    download_button.click()

    # 5. 等待按鈕狀態變為「已就緒」
    # 這隱含地測試了後端的下載和 WebSocket 廣播功能
    expect(download_button).to_have_text("✅ 模型已就緒", timeout=120000) # 給予足夠的下載時間 (2分鐘)
    log.info("✅ 驗證成功: 模型下載完成，按鈕狀態已更新。")

    # 6. 驗證 store 中的狀態
    available_models = page.evaluate("() => window.tasksStore.localModels.available")
    assert model_to_download in available_models
    log.info(f"✅ 驗證成功: '{model_to_download}' 模型已存在於前端 store 的可用列表中。")

    return True

def test_health_check_button(page, expect):
    """測試手動觸發的健康檢查按鈕。"""
    log.info("--- 開始執行手動健康檢查按鈕驗證測試 ---")

    # 1. 定位並點擊按鈕
    health_check_button = page.locator('[data-testid="health-check-button"]')
    expect(health_check_button).to_be_enabled(timeout=10000)
    health_check_button.click()
    log.info("已點擊 '執行通訊測試' 按鈕。")

    # 2. 驗證成功通知
    # 等待一個 class 為 'notification-success' 且包含特定文字的元素出現
    success_notification = page.locator(
        ".notification.notification-success:has-text('健康檢查成功！')"
    )
    expect(success_notification).to_be_visible(timeout=10000)
    log.info("✅ 驗證成功: 健康檢查成功的通知已顯示。")

    # 點擊關閉按鈕以清理UI，避免影響後續測試
    success_notification.locator("button.close-button").click()
    expect(success_notification).not_to_be_visible(timeout=5000)
    log.info("已關閉健康檢查通知。")
    return True

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
                # 新增：在健康檢查中加入 X-Forwarded-Proto 標頭，以模擬來自反向代理的 HTTPS 請求
                headers = {"X-Forwarded-Proto": "https"}
                response = requests.get(health_check_url, headers=headers, timeout=2)
                if response.status_code == 200:
                    log.info("✅ 健康檢查成功 (已模擬代理)！伺服器已準備就緒。")
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
                # 首先執行 WebSocket echo 測試
                if not test_websocket_echo(page, expect, api_url):
                    raise RuntimeError("WebSocket Echo 驗證測試失敗。")

                target_url = f"{api_url}/ui"
                log.info(f"導航至: {target_url}")
                page.goto(target_url, wait_until='domcontentloaded', timeout=20000)

                log.info("等待 Vue app 初始化 (等待 window.vue_app)...")
                page.wait_for_function('() => window.vue_app', timeout=15000)
                log.info("✅ Vue app 已找到！")

                # --- 驗證啟動時自動健康檢查 ---
                log.info("--- 正在驗證啟動時自動健康檢查 ---")
                startup_success_notification = page.locator(
                    ".notification.notification-success:has-text('啟動健康檢查成功！')"
                )
                expect(startup_success_notification).to_be_visible(timeout=15000) # Give it some time for retries
                log.info("✅ 驗證成功: 啟動時健康檢查成功的通知已顯示。")
                # Clean up the notification to not interfere with other tests
                startup_success_notification.locator("button.close-button").click()
                expect(startup_success_notification).not_to_be_visible(timeout=5000)

                log.info("正在驗證頁面標題...")
                expect(page).to_have_title("音訊轉錄儀", timeout=5000)
                log.info("✅ 驗證成功: 頁面標題符合預期。")

                # --- 執行新的手動健康檢查測試 ---
                if not test_health_check_button(page, expect):
                    raise RuntimeError("手動健康檢查按鈕驗證測試失敗。")

                log.info("架構已簡化，不再有獨立的工作者或硬體監控狀態，跳過相關驗證。")

                log.info("從測試腳本強制呼叫 checkLocalModels action 以確保狀態更新...")
                page.evaluate('window.tasksStore.checkLocalModels()')
                log.info("✅ 已呼叫 checkLocalModels。")

                # --- 執行新的、更詳細的轉錄輸出驗證 ---
                if not test_transcription_output(page, expect):
                    raise RuntimeError("轉錄輸出驗證測試失敗。")

                # --- 執行模型下載測試 ---
                if not test_model_download(page, expect):
                    raise RuntimeError("模型下載驗證測試失敗。")

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
