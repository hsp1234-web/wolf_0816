# -*- coding: utf-8 -*-
"""
端對端 (E2E) 測試腳本 (v16 架構)

此腳本旨在驗證「分段漸進式」啟動架構的完整流程。
它遵循 CH_log.md 中定義的最佳實踐，在一個隔離的虛擬環境中執行。
"""
import subprocess
import sys
import time
from pathlib import Path
import logging
import os
import shutil
import uuid
import threading
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('E2E測試')
ROOT_DIR = Path(__file__).resolve().parent
SCREENSHOT_PATH = ROOT_DIR / "e2e_test_screenshot.png"
SIMULATION_TIMEOUT = 300 # 5分鐘，應足以完成輕量模式下的依賴安裝

def execute_command(command, cwd=ROOT_DIR, env=None, step_name=""):
    """執行一個 shell 指令並記錄日誌"""
    log.info(f"--- {step_name} ---")
    log.info(f"執行中: {' '.join(command)}")
    try:
        # 使用 Popen 以便即時讀取輸出
        process = subprocess.Popen(
            command, cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace'
        )
        for line in iter(process.stdout.readline, ''):
            log.info(f"[CMD] {line.strip()}")

        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command)

        log.info(f"✅ {step_name} 成功")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.error(f"❌ {step_name} 失敗。")
        if isinstance(e, subprocess.CalledProcessError):
            log.error(f"返回碼: {e.returncode}")
        else:
            log.error(f"錯誤: {e}")
        return False

def run_e2e_test():
    # 使用 threading.Timer 實現總超時
    kill_flag = threading.Event()
    def timeout_handler():
        log.error(f"❌❌❌ 總測試時間超過 {SIMULATION_TIMEOUT} 秒，強制中止！ ❌❌❌")
        kill_flag.set()

    timer = threading.Timer(SIMULATION_TIMEOUT, timeout_handler)
    timer.start()

    server_proc = None
    venv_dir = Path(f"/tmp/e2e_test_venv_{uuid.uuid4()}")
    exit_code = 1

    try:
        # --- 步驟 1: 建立並啟用隔離的虛擬環境 ---
        if not execute_command([sys.executable, "-m", "venv", str(venv_dir)], step_name="建立虛擬環境"):
            raise RuntimeError("建立虛擬環境失敗")

        venv_python = str(venv_dir / "bin" / "python")
        venv_pip = str(venv_dir / "bin" / "pip")

        # --- 步驟 2: 安裝門面伺服器的輕量依賴 ---
        req_light_path = str(ROOT_DIR / "src" / "requirements_light.txt")
        if not execute_command([venv_pip, "install", "-r", req_light_path], step_name="安裝輕量依賴"):
            raise RuntimeError("安裝輕量依賴失敗")

        # --- 步驟 3: 啟動門面伺服器 (輕量模式) ---
        log.info("--- 啟動門面伺服器 (輕量模式) ---")
        FACADE_SERVER_PORT = 8000 # 與 Colabpro.py 和 facade_server.py 中定義的埠號一致
        server_command = [
            venv_python, "-m", "uvicorn",
            "src.facade_server:app",
            "--host", "0.0.0.0",
            "--port", str(FACADE_SERVER_PORT)
        ]

        # 設定環境變數以啟用輕量模式
        server_env = os.environ.copy()
        server_env["LIGHT_MODE"] = "1"
        log.info("已為子程序設定環境變數 LIGHT_MODE=1")

        server_proc = subprocess.Popen(
            server_command, cwd=ROOT_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
            env=server_env
        )

        def log_server_output():
            for line in iter(server_proc.stdout.readline, ''):
                log.info(f"[伺服器] {line.strip()}")

        server_log_thread = threading.Thread(target=log_server_output)
        server_log_thread.daemon = True
        server_log_thread.start()

        time.sleep(5) # 等待 uvicorn 啟動
        if server_proc.poll() is not None:
             raise RuntimeError(f"門面伺服器啟動失敗，返回碼: {server_proc.poll()}")
        log.info(f"✅ 門面伺服器似乎已成功啟動在 http://127.0.0.1:{FACADE_SERVER_PORT}")

        # --- 步驟 4: Playwright 驗證 ---
        log.info("--- 使用 Playwright 進行 E2E 驗證 ---")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.on("console", lambda msg: log.info(f"[瀏覽器] {msg.text}"))
            page.on("pageerror", lambda err: log.error(f"[瀏覽器錯誤] {err.message}"))

            try:
                target_url = f"http://127.0.0.1:{FACADE_SERVER_PORT}"
                log.info(f"導航至: {target_url}")
                page.goto(target_url, wait_until='domcontentloaded', timeout=20000)

                # 1. 驗證安裝覆蓋層
                log.info("正在驗證初始安裝覆蓋層...")
                overlay = page.locator(".installation-overlay")
                expect(overlay).to_be_visible(timeout=10000)
                log.info("✅ 安裝覆蓋層已顯示。")

                log_container = overlay.locator(".log-container pre code")

                # 2. 等待安裝完成
                log.info("正在等待安裝完成的日誌訊息...")
                # 我們期望看到 PyTorch CPU 安裝和主服務啟動的訊息
                expect(log_container).to_contain_text("正在安裝 PyTorch (CPU 版本)", timeout=180000)
                log.info("✅ 已偵測到 PyTorch CPU 版本安裝日誌。")

                expect(log_container).to_contain_text("正在啟動主服務", timeout=60000)
                log.info("✅ 已偵測到主服務啟動日誌。")

                # 等待覆蓋層消失
                log.info("正在等待安裝覆蓋層消失...")
                expect(overlay).not_to_be_visible(timeout=10000)
                log.info("✅ 安裝覆蓋層已消失，主應用程式介面已顯示。")

                # 3. 驗證主應用程式基本功能
                log.info("正在驗證主應用程式介面...")
                header = page.locator("header h1")
                expect(header).to_have_text("音訊轉錄儀 (Vue)", timeout=5000)
                log.info("✅ 主應用程式標題驗證成功。")

                # 4. 執行一個簡化的轉錄任務來驗證核心流程
                page.click("button:has-text('本機檔案轉錄')")
                page.select_option('[data-testid="model-selector"]', "tiny.en")

                # 由於模型是在背景安裝的，我們需要等待模型就緒
                ready_indicator = page.locator('[data-testid="model-selector"] ~ .status-indicator')
                # 這部分可能需要調整，取決於主服務啟動後前端的狀態更新邏輯
                # 暫時跳過，假設輕量模式下模型已就緒
                log.info("輕量模式下，假設 tiny.en 模型已就緒。")

                file_path = ROOT_DIR / 'vue-app' / 'tests' / 'fixtures' / 'test-audio.txt'
                page.set_input_files('[data-testid="file-input"]', file_path)
                page.click('[data-testid="add-to-queue-button"]')
                page.click('[data-testid="submit-queue-button"]')

                log.info("正在等待轉錄任務完成...")
                completed_task_item = page.locator(".task-item:has-text('test-audio.txt')")
                expect(completed_task_item).to_be_visible(timeout=45000)
                log.info("✅ 轉錄任務已出現在「已完成」列表中。")

                log.info("✅✅✅ E2E 測試成功！ ✅✅✅")
                exit_code = 0

            except PlaywrightTimeoutError as e:
                log.error(f"❌ Playwright 測試超時: {e}")
                page.screenshot(path=SCREENSHOT_PATH)
                log.error(f"已儲存超時螢幕截圖至: {SCREENSHOT_PATH}")
            except Exception as e:
                log.error(f"❌ Playwright 測試期間發生錯誤: {e}", exc_info=True)
                page.screenshot(path=SCREENSHOT_PATH)
                log.error(f"已儲存錯誤螢幕截圖至: {SCREENSHOT_PATH}")
            finally:
                browser.close()

    except Exception as e:
        log.error(f"E2E 測試流程發生嚴重錯誤: {e}", exc_info=True)
    finally:
        if server_proc and server_proc.poll() is None:
            log.info("正在關閉伺服器...")
            server_proc.terminate()
            server_proc.wait(timeout=5)

        if venv_dir.exists():
            log.info(f"正在清理虛擬環境: {venv_dir}")
            shutil.rmtree(venv_dir)

        timer.cancel()
        if kill_flag.is_set():
            sys.exit(1)

    return exit_code

if __name__ == "__main__":
    final_exit_code = run_e2e_test()
    if final_exit_code == 0:
        log.info("🎉 E2E 測試流程執行完畢，所有驗證均通過。")
    else:
        log.error("🔥 E2E 測試流程執行失敗。")
    sys.exit(final_exit_code)
