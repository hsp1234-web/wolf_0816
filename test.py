import subprocess
import sys
import re
import time
from pathlib import Path
import logging
import os
import socket
import asyncio
import threading
import json
from typing import List, Dict, Any

# --- Websocket 和測試相關的依賴 ---
# 我們將在 install_dependencies 中確保它們被安裝
import websockets
from deepdiff import DeepDiff
import jsonpatch

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('E2E_Test_V2')
ROOT_DIR = Path(__file__).resolve().parent
API_GATEWAY_DIR = ROOT_DIR / "services" / "api_gateway"
E2E_TIMEOUT = 90 # 增加超時時間以應對更複雜的測試流程

# --- WebSocket 測試客戶端 ---
class WebSocketTestClient:
    """一個在背景執行緒中運行的 WebSocket 客戶端，用於接收和驗證狀態更新。"""
    def __init__(self, uri):
        self.uri = uri
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.initial_state: Dict[str, Any] | None = None
        self.patches: List[List[Dict[str, Any]]] = []
        self.is_connected = threading.Event()
        self.initial_state_received = threading.Event()
        self._loop = None

    def start(self):
        self.thread.start()

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._listen())

    async def _listen(self):
        try:
            async with websockets.connect(self.uri) as websocket:
                log.info(f"[WebSocketClient] 成功連接至 {self.uri}")
                self.is_connected.set()
                while True:
                    message_str = await websocket.recv()
                    message = json.loads(message_str)
                    msg_type = message.get("type")
                    payload = message.get("payload")

                    if msg_type == "full_state":
                        log.info("[WebSocketClient] 收到 full_state")
                        self.initial_state = payload
                        self.initial_state_received.set()
                    elif msg_type == "patch":
                        log.info(f"[WebSocketClient] 收到 patch: {payload}")
                        self.patches.append(payload)
                    else:
                        log.warning(f"[WebSocketClient] 收到未知訊息類型: {msg_type}")
        except Exception as e:
            log.error(f"[WebSocketClient] 連線錯誤: {e}", exc_info=True)
            self.is_connected.clear() # 標示為未連線

    def stop(self):
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.thread.join(timeout=5)

    def get_current_state(self) -> Dict[str, Any]:
        """應用所有補丁以獲取當前狀態。"""
        if self.initial_state is None:
            return {}
        current_state = self.initial_state
        for patch_set in self.patches:
            current_state = jsonpatch.apply_patch(current_state, patch_set, inplace=False)
        return current_state

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def install_dependencies():
    log.info("--- [步驟 1/4] 安裝 E2E 測試依賴 ---")
    gateway_reqs = API_GATEWAY_DIR / "requirements.txt"
    test_deps = ["playwright", "pytz", "websockets", "deepdiff", "jsonpatch"]
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(gateway_reqs)], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q"] + test_deps, check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps"], check=True, capture_output=True, text=True)
        log.info("✅ 依賴安裝成功。")
        return True
    except Exception as e:
        log.error(f"❌ 依賴安裝失敗: {e}")
        return False

def run_and_verify():
    log.info(f"--- [步驟 2/4] 啟動 API Gateway (總超時: {E2E_TIMEOUT}秒) ---")
    proc = None
    ws_client = None
    start_time = time.monotonic()

    try:
        # 清理舊的資料庫檔案以確保測試的冪等性
        log.info("清理舊的資料庫檔案...")
        for db_file in ["queue.db", "logs.db"]:
            if (ROOT_DIR / db_file).exists():
                (ROOT_DIR / db_file).unlink()

        port = find_free_port()
        api_gateway_url = f"http://127.0.0.1:{port}"
        ws_url = f"ws://127.0.0.1:{port}/ws"
        log.info(f"將在動態埠號 {port} 上啟動服務...")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR)
        env["APP_ENV"] = "test"  # 設置測試模式環境變數
        command = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)]
        proc = subprocess.Popen(command, cwd=API_GATEWAY_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', env=env)

        log.info("監聽 API Gateway 啟動日誌...")
        for _ in range(40): # 等待最多 20 秒
            line = proc.stdout.readline()
            if "Uvicorn running on" in line:
                log.info(f"[API_Gateway]: {line.strip()}")
                log.info("✅ API Gateway 已成功啟動！")
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("API Gateway 啟動超時")

        # --- WebSocket Client 驗證 ---
        log.info(f"--- [步驟 3/4] 連接 WebSocket 並驗證初始狀態 ---")
        ws_client = WebSocketTestClient(ws_url)
        ws_client.start()
        if not ws_client.is_connected.wait(timeout=10):
            raise RuntimeError("WebSocket 客戶端連接超時")
        if not ws_client.initial_state_received.wait(timeout=10):
            raise RuntimeError("未能在超時內收到初始 full_state")

        log.info("✅ WebSocket 已連接並收到初始狀態。")
        assert ws_client.initial_state is not None
        assert ws_client.initial_state.get("pending_tasks") == []

        # --- Playwright 驗證 ---
        log.info(f"--- [步驟 4/4] 使用 Playwright 執行操作並驗證狀態同步 ---")
        from playwright.sync_api import sync_playwright, expect

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            try:
                log.info(f"[Playwright] 導航至: {api_gateway_url}")
                page.goto(api_gateway_url, wait_until="domcontentloaded", timeout=20000)

                # 驗證初始UI狀態
                # 定位到包含 "進行中任務" 標題的卡片，並檢查其中是否有 "暫無執行中任務" 的文字。
                pending_tasks_card = page.locator(".card:has-text('進行中任務')")
                expect(pending_tasks_card.locator("text=暫無執行中任務")).to_be_visible(timeout=10000)
                log.info("[Playwright] ✅ 初始UI狀態正確 (顯示'暫無執行中任務')。")

                # 模擬上傳檔案
                log.info("[Playwright] 模擬上傳檔案以觸發轉錄任務...")

                # 建立一個假的音訊檔案
                dummy_file_path = ROOT_DIR / "test_audio.mp3"
                dummy_file_path.write_text("This is a dummy audio file.")

                # 使用 set_input_files 來觸發上傳
                file_input = page.locator('input[type="file"]')
                file_input.set_input_files(dummy_file_path)

                # 等待 WebSocket 收到第一個補丁 (新增任務)
                time.sleep(5) # 等待後端處理請求和廣播

                log.info("驗證 WebSocket 狀態更新...")
                final_state = ws_client.get_current_state()

                assert len(final_state["pending_tasks"]) == 1, "狀態中應只有一個待處理任務"
                task = final_state["pending_tasks"][0]
                assert task["status"] == "processing", f"任務狀態應為 'processing'，但卻是 '{task['status']}'"
                assert task["payload"]["original_filename"] == "test_audio.mp3"
                log.info("✅ WebSocket 狀態已正確更新 (queued -> processing)。")

                # 等待任務完成
                log.info("等待任務完成 (最多 15 秒)...")
                time.sleep(15) # 等待模擬的10秒任務完成 + 緩衝

                final_state_completed = ws_client.get_current_state()
                assert len(final_state_completed["pending_tasks"]) == 0, "待處理任務列表應為空"
                assert len(final_state_completed["completed_tasks"]) == 1, "應只有一個已完成任務"
                completed_task = final_state_completed["completed_tasks"][0]
                assert completed_task["status"] == "completed", f"任務狀態應為 'completed'，但卻是 '{completed_task['status']}'"
                assert "transcription" in completed_task["result"], "結果中應包含轉錄內容"
                log.info("✅ WebSocket 狀態已正確更新 (processing -> completed)。")

                # 驗證最終UI
                log.info("[Playwright] 驗證最終 UI 狀態...")
                completed_tasks_card = page.locator(".card:has-text('已完成任務')")
                expect(completed_tasks_card.locator("text=test_audio.mp3")).to_be_visible(timeout=5000)
                log.info("[Playwright] ✅ 最終UI狀態正確 (已完成任務列表中顯示了正確的檔名)。")

                screenshot_path = ROOT_DIR / "final_e2e_success.png"
                page.screenshot(path=str(screenshot_path))
                log.info(f"✅ 成功擷取最終驗證畫面至: {screenshot_path}")

            except Exception as e:
                log.error(f"❌ Playwright 或狀態驗證失敗: {e}", exc_info=True)
                page.screenshot(path=str(ROOT_DIR / "final_e2e_failure.png"))
                return False
            finally:
                browser.close()
        return True
    finally:
        if ws_client: ws_client.stop()
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)

def main():
    log.info("====== 開始執行 V2 架構端對端驗證 ======")
    start_time = time.monotonic()
    if not install_dependencies():
        log.critical("====== 驗證失敗：無法安裝依賴 ======")
        sys.exit(1)
    try:
        if run_and_verify():
            elapsed = time.monotonic() - start_time
            log.info(f"✅✅✅ 驗證成功！在 {elapsed:.2f} 秒內完成。✅✅✅")
            print("\n[SUCCESS] The end-to-end test passed.")
            sys.exit(0)
        else:
            log.critical("❌❌❌ 驗證失敗！")
            print("\n[FAILURE] The end-to-end test failed.")
            sys.exit(1)
    except Exception as e:
        log.critical(f"❌ 測試過程中發生未預期的錯誤: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
