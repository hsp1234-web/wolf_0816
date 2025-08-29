# -*- coding: utf-8 -*-
import subprocess
import sys
import os
import logging
from pathlib import Path
import shutil
import time

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('APIGatewayWSTest')
ROOT_DIR = Path(__file__).resolve().parent
VENV_DIR = ROOT_DIR / f"venv_test_api_ws_{int(time.time())}"

# --- 自我引導邏輯 ---
# 檢查我們是否已經在虛擬環境中運行
if os.environ.get("IN_TEST_VENV") != "1":
    log.info("不在虛擬環境中。正在設定...")

    # 1. 建立虛擬環境
    log.info(f"正在建立虛擬環境於: {VENV_DIR}")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)

    # 2. 在虛擬環境中安裝依賴
    venv_pip = str(VENV_DIR / "bin" / "pip")
    # 修正：使用輕量級的測試依賴，避免重量級 AI/ML 套件
    req_path = str(ROOT_DIR / "requirements-test-light.txt")
    log.info(f"正在從 {req_path} 安裝依賴至虛擬環境...")
    subprocess.run([venv_pip, "install", "-r", req_path], check=True, capture_output=True)
    log.info("✅ 依賴安裝完成。")

    # 3. 使用虛擬環境的 python 重新啟動此腳本
    log.info("正在虛擬環境中重新啟動測試腳本...")
    venv_python = str(VENV_DIR / "bin" / "python")
    env = os.environ.copy()
    env["IN_TEST_VENV"] = "1"

    try:
        # 將 stdout 和 stderr 導向父程序，以便我們能看到日誌
        process = subprocess.run([venv_python, __file__], env=env, check=True, capture_output=False)
        # 以子程序的退出碼退出
        shutil.rmtree(VENV_DIR) # 成功後清理
        sys.exit(process.returncode)
    except subprocess.CalledProcessError as e:
        log.error("在虛擬環境中執行腳本失敗。")
        shutil.rmtree(VENV_DIR) # 失敗後清理
        sys.exit(e.returncode)
    except Exception as e:
        log.error(f"重新啟動過程中發生未預期的錯誤: {e}")
        shutil.rmtree(VENV_DIR)
        sys.exit(1)

# =======================================================================
# == 如果我們到達此處，表示我們正在虛擬環境中運行 ==
# =======================================================================
log.info("✅ 已成功在虛擬環境中運行。")

# 現在我們可以安全地導入依賴
import asyncio
import json
import websockets

SIMULATION_TIMEOUT = 150

async def run_test():
    """主測試協程"""
    server_proc = None
    exit_code = 1
    API_PORT = 8002

    try:
        log.info(f"--- 正在啟動統一 API 伺服器於埠號 {API_PORT} ---")
        # 修正：指向新的、統一的 api_server
        server_command = [
            sys.executable, "-m", "uvicorn",
            "src.api_server:app",
            "--host", "0.0.0.0",
            "--port", str(API_PORT)
        ]

        # 啟動資料庫管理器作為背景進程
        db_manager_command = [sys.executable, str(ROOT_DIR / "src/db/manager.py")]
        db_proc = subprocess.Popen(db_manager_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log.info(f"資料庫管理器已啟動 (PID: {db_proc.pid})")
        await asyncio.sleep(5) # 等待資料庫管理器初始化

        server_proc = subprocess.Popen(
            server_command,
            cwd=ROOT_DIR,
            stdout=sys.stdout,
            stderr=sys.stderr
        )

        await asyncio.sleep(10)

        if server_proc.poll() is not None:
            raise RuntimeError(f"API 伺服器啟動失敗。退出碼: {server_proc.poll()}")
        log.info("✅ API 伺服器似乎正在運行。")

        target_ws_url = f"ws://127.0.0.1:{API_PORT}/ws/status"
        log.info(f"--- 正在嘗試連接 WebSocket: {target_ws_url} ---")

        try:
            async with websockets.connect(target_ws_url) as websocket:
                log.info("✅ WebSocket 連線成功！")
                log.info("--- 正在驗證自動回報機制 ---")
                message_str = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                message = json.loads(message_str)
                log.info(f"收到初始訊息: {message}")

                # 修正：根據 src/api_server.py 的實作，初始訊息類型應為 'all_tasks'
                assert message.get("type") == "all_tasks"
                # 修正：payload 應為一個列表
                assert isinstance(message.get("payload"), list)
                log.info("✅ 初始狀態訊息驗證成功！")
                log.info("✅✅✅ 測試通過！✅✅✅")
                exit_code = 0

        except websockets.exceptions.InvalidStatus as e:
            log.error(f"❌ 測試失敗：無法連接 WebSocket: {e}")
            exit_code = 1
        except Exception as e:
            log.error(f"❌ 測試過程中發生未預期的錯誤: {e}", exc_info=True)
            exit_code = 1

    finally:
        if server_proc and server_proc.poll() is None:
            log.info("正在關閉 API 伺服器...")
            server_proc.terminate()
        if 'db_proc' in locals() and db_proc.poll() is None:
            log.info("正在關閉資料庫管理器...")
            db_proc.terminate()

        # 等待進程結束
        if server_proc:
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()
        if 'db_proc' in locals():
             try:
                db_proc.wait(timeout=5)
             except subprocess.TimeoutExpired:
                db_proc.kill()

        log.info(f"測試執行完畢，退出碼: {exit_code}")
    return exit_code


if __name__ == "__main__":
    try:
        final_code = asyncio.run(asyncio.wait_for(run_test(), timeout=SIMULATION_TIMEOUT))
        sys.exit(final_code)
    except asyncio.TimeoutError:
        log.error(f"❌❌❌ 測試因超過 {SIMULATION_TIMEOUT} 秒總時長而強制中止！ ❌❌❌")
        sys.exit(1)
