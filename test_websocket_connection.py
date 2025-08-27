# -*- coding: utf-8 -*-
"""
輕量級 E2E 測試：專門用於診斷 WebSocket 連線

目的：
- 快速 (60秒內) 啟動伺服器。
- 驗證瀏覽器是否能成功與後端的 WebSocket 端點建立連線。
- 作為一個 POC 工具，用於重現 403 錯誤，並在應用修復後驗證其有效性。
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
import queue

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('WebSocket測試')
ROOT_DIR = Path(__file__).resolve().parent
SIMULATION_TIMEOUT = 90 # 給予 90 秒的總測試時間

def run_websocket_test():
    """主測試函數"""
    kill_flag = threading.Event()
    def timeout_handler():
        log.error(f"❌❌❌ 總測試時間超過 {SIMULATION_TIMEOUT} 秒，強制中止！ ❌❌❌")
        kill_flag.set()

    timer = threading.Timer(SIMULATION_TIMEOUT, timeout_handler)
    timer.start()

    server_proc = None
    venv_dir = Path(f"/tmp/ws_test_venv_{uuid.uuid4()}")
    exit_code = 1 # 預設為失敗

    # 使用 queue 來從日誌執行緒中獲取結果
    log_queue = queue.Queue()

    try:
        # --- 步驟 1: 建立虛擬環境並安裝依賴 ---
        log.info("--- 步驟 1: 設定虛擬環境 ---")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, capture_output=True)
        venv_python = str(venv_dir / "bin" / "python")
        req_light_path = str(ROOT_DIR / "src" / "requirements_light.txt")
        try:
            subprocess.run(
                [venv_python, "-m", "pip", "install", "-r", req_light_path],
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            log.info("✅ 虛擬環境與輕量依賴安裝完成。")
        except subprocess.CalledProcessError as e:
            log.error("🔥🔥🔥 `pip install` 步驟失敗！ 🔥🔥🔥")
            log.error(f"返回碼: {e.returncode}")
            log.error("--- PIP STDOUT ---")
            log.error(e.stdout)
            log.error("--- PIP STDERR ---")
            log.error(e.stderr)
            log.error("--------------------")
            raise  # 重新拋出異常以中止測試

        # --- 步驟 2: 啟動門面伺服器 ---
        log.info("--- 步驟 2: 啟動門面伺服器 ---")
        FACADE_SERVER_PORT = 8001 # 使用一個不同的埠號以避免衝突
        server_command = [
            venv_python, "-m", "uvicorn",
            "src.facade_server:app",
            "--host", "0.0.0.0",
            "--port", str(FACADE_SERVER_PORT)
        ]
        server_env = os.environ.copy()
        server_env["LIGHT_MODE"] = "1"

        server_proc = subprocess.Popen(
            server_command, cwd=ROOT_DIR,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
            env=server_env
        )

        def log_server_output(q):
            for line in iter(server_proc.stdout.readline, ''):
                stripped_line = line.strip()
                log.info(f"[伺服器] {stripped_line}")
                # 將關鍵日誌放入佇列
                # 修正：直接監聽 uvicorn 的標準成功日誌，而不是依賴應用程式的 print 語句
                if '"WebSocket /ws/status" [accepted]' in stripped_line:
                    q.put("SUCCESS")
                elif "connection rejected (403 Forbidden)" in stripped_line:
                    q.put("FAILURE_403")

        server_log_thread = threading.Thread(target=log_server_output, args=(log_queue,))
        server_log_thread.daemon = True
        server_log_thread.start()

        time.sleep(5) # 等待 uvicorn 啟動
        if server_proc.poll() is not None:
             raise RuntimeError(f"門面伺服器啟動失敗，返回碼: {server_proc.poll()}")
        log.info(f"✅ 門面伺服器似乎已在 http://127.0.0.1:{FACADE_SERVER_PORT} 啟動")

        # --- 步驟 3: Playwright 驗證 ---
        log.info("--- 步驟 3: 使用 Playwright 嘗試連線 ---")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # 導航到一個不存在的頁面，這足以觸發 JS 執行和 WebSocket 連線
            target_url = f"http://127.0.0.1:{FACADE_SERVER_PORT}"
            log.info(f"Playwright 正在導航至: {target_url}")
            page.goto(target_url, timeout=10000)
            log.info("Playwright 頁面已載入，前端 JS 應已嘗試建立 WebSocket 連線。")
            browser.close()

        # --- 步驟 4: 分析結果 ---
        log.info("--- 步驟 4: 分析伺服器日誌以判斷結果 ---")
        try:
            # 等待最多 15 秒，看日誌執行緒是否捕獲到了關鍵訊息
            result = log_queue.get(timeout=15)
            if result == "SUCCESS":
                log.info("✅✅✅ 測試通過：在伺服器日誌中偵測到 'WebSocket 連線已接受'。")
                exit_code = 0
            elif result == "FAILURE_403":
                log.error("🔥🔥🔥 測試失敗：在伺服器日誌中偵測到 '403 Forbidden'。")
                exit_code = 1

        except queue.Empty:
            log.error("🔥🔥🔥 測試失敗：在 15 秒內未偵測到任何 WebSocket 連線成功或失敗的日誌。")
            exit_code = 1

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
            sys.exit(1) # 確保因超時而退出時返回非零碼

    return exit_code

if __name__ == "__main__":
    final_exit_code = run_websocket_test()
    if final_exit_code == 0:
        log.info("🎉 WebSocket 連線測試成功。")
    else:
        log.error("🔥 WebSocket 連線測試失敗。")
    sys.exit(final_exit_code)
