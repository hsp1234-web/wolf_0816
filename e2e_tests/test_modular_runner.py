# e2e_tests/test_modular_runner.py
import pytest
import subprocess
import sys
import time
import logging
import os
import re
import threading
from pathlib import Path
from playwright.sync_api import Page, expect

# --- 全域設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent
log = logging.getLogger('TestModularRunner')

@pytest.fixture(scope="session")
def modular_runner_server():
    """
    一個新的 Pytest fixture，專門用於測試模組化的啟動器。
    它會執行新的 `main_runner.py` 腳本，並預期從中獲取一個可用的伺服器 URL。
    """
    log.info("--- Setting up server via modular_runner.py for E2E test ---")
    runner_script_path = ROOT_DIR / "runner" / "main_runner.py"

    if not runner_script_path.exists():
        pytest.fail(f"預期的啟動器腳本不存在: {runner_script_path}")

    # 使用與 Colabpro.py 相同的環境來執行 runner
    # 我們預期 runner 會自行處理依賴安裝
    runner_proc = None
    try:
        command = [sys.executable, str(runner_script_path)]
        log.info(f"執行啟動命令: {' '.join(command)}")

        # 我們需要從 stdout 捕捉 URL
        runner_proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # 將 stderr 也導出，以便除錯
            text=True,
            encoding='utf-8',
            # preexec_fn=os.setsid # 在非Windows系統上，這有助於之後完全終止進程組
        )

        # 等待並從 stdout 中解析出 URL
        server_url = None
        url_pattern = re.compile(r"FINAL_URL:\s*(https?://[^\s]+)")

        # 設定一個合理的超時，例如 90 秒，以符合使用者對快速啟動的要求
        timeout = 90
        start_time = time.time()

        # 建立一個執行緒來處理 stderr，避免管道阻塞
        stderr_output = []
        def log_stderr():
            for line in iter(runner_proc.stderr.readline, ''):
                log.warning(f"[Runner stderr]: {line.strip()}")
                stderr_output.append(line)

        stderr_thread = threading.Thread(target=log_stderr)
        stderr_thread.daemon = True
        stderr_thread.start()

        for line in iter(runner_proc.stdout.readline, ''):
            log.info(f"[Runner stdout]: {line.strip()}")
            match = url_pattern.search(line)
            if match:
                server_url = match.group(1)
                log.info(f"✅ 從啟動器成功解析到 URL: {server_url}")
                break
            if time.time() - start_time > timeout:
                # 收集所有剩餘的輸出
                remaining_stdout, _ = runner_proc.communicate(timeout=5)
                log.error(f"[Runner stdout (timeout)]: {remaining_stdout}")
                pytest.fail(f"啟動器未能在 {timeout} 秒內輸出 FINAL_URL。")

        if not server_url:
            pytest.fail("啟動器執行完畢，但未能從其輸出中找到 FINAL_URL。")

        # 在提供 URL 之前，給伺服器一點時間完全暖機
        time.sleep(3)
        yield server_url

    finally:
        log.info("--- Tearing down modular runner server ---")
        if runner_proc and runner_proc.poll() is None:
            log.info(f"正在終止啟動器進程 (PID: {runner_proc.pid})...")
            try:
                # 溫和地終止
                runner_proc.terminate()
                runner_proc.wait(timeout=5)
                log.info("✅ 啟動器進程已終止。")
            except subprocess.TimeoutExpired:
                log.warning("啟動器進程未能正常終止，將強制擊殺 (kill)。")
                runner_proc.kill()
                log.warning("✅ 啟動器進程已被強制擊殺。")


@pytest.mark.usefixtures("page")
def test_runner_launches_and_is_accessible(page: Page, modular_runner_server: str):
    """
    使用新的模組化啟動器來啟動伺服器，並用 Playwright 驗證網頁是否可訪問。
    """
    target_url = modular_runner_server
    screenshot_path = ROOT_DIR / "e2e_tests" / "runner_test_output.png"

    log.info(f"正在導航至由啟動器提供的 URL: {target_url}")
    try:
        page.goto(target_url, timeout=20000)

        # 驗證頁面標題是否為 Vue 應用的標題
        # 根據 vue-app/index.html，標題應為 "音訊轉錄儀"
        expected_title = "音訊轉錄儀"
        expect(page).to_have_title(expected_title, timeout=10000)
        log.info(f"✅ 頁面標題 '{expected_title}' 驗證成功。")

        # 驗證一個關鍵的介面元素是否存在，例如主標題 "音訊轉錄儀 (Vue)"
        header_text = "音訊轉錄儀 (Vue)"
        header_element = page.get_by_role("heading", name=header_text)
        expect(header_element).to_be_visible()
        log.info(f"✅ 關鍵介面元素 '{header_text}' 驗證成功。")

        log.info(f"測試成功，正在儲存截圖至 {screenshot_path}")
        page.screenshot(path=screenshot_path)

    except Exception as e:
        log.error(f"❌ 測試模組化啟動器時發生錯誤: {e}", exc_info=True)
        page.screenshot(path=screenshot_path)
        log.error(f"📸 已儲存錯誤截圖至 {screenshot_path}")
        raise
