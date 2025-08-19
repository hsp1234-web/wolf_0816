import pytest
import requests
import json
import time
import websocket
from threading import Thread

# --- 測試設定 ---
# 增加一個全域超時，以防測試因 WebSocket 問題而永久掛起
TEST_TIMEOUT_SECONDS = 45

# --- 測試裝置 (Fixtures) ---

# 我們將使用在 conftest.py 中定義的共享 live_server fixture。
# 它會處理伺服器的啟動和關閉。

# --- 輔助函式與類別 ---

class WebSocketClient:
    """一個簡單的 WebSocket 客戶端，用於在背景執行緒中監聽訊息。"""
    def __init__(self, url):
        self.ws_url = url
        self.ws = None
        self.thread = None
        self.received_messages = []
        self.is_connected = False
        self.error = None

    def connect(self):
        """建立連線並在單獨的執行緒中開始監聽。"""
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        self.thread = Thread(target=self.ws.run_forever, daemon=True)
        self.thread.start()
        # 等待連線建立
        timeout = 10
        start_time = time.time()
        while not self.is_connected and time.time() - start_time < timeout:
            if self.error:
                raise self.error
            time.sleep(0.1)
        if not self.is_connected:
            raise ConnectionError("WebSocket 連線超時。")

    def _on_open(self, ws):
        print("WebSocket 連線已開啟。")
        self.is_connected = True

    def _on_message(self, ws, message):
        """將收到的訊息（已解析為 JSON）加入佇列。"""
        print(f"收到 WebSocket 訊息: {message}")
        try:
            self.received_messages.append(json.loads(message))
        except json.JSONDecodeError:
            print(f"警告：收到非 JSON 格式的 WebSocket 訊息: {message}")

    def _on_error(self, ws, error):
        print(f"WebSocket 發生錯誤: {error}")
        self.error = error

    def _on_close(self, ws, close_status_code, close_msg):
        print(f"WebSocket 連線已關閉。狀態碼: {close_status_code}, 訊息: {close_msg}")
        self.is_connected = False

    def send(self, message: dict):
        """發送一個 JSON 訊息。"""
        if not self.is_connected:
            raise ConnectionError("WebSocket 未連線。")
        self.ws.send(json.dumps(message))

    def close(self):
        """關閉連線。"""
        if self.ws:
            self.ws.close()
        if self.thread:
            self.thread.join(timeout=5)

    def get_messages_by_type(self, msg_type: str, timeout: int = 10):
        """等待並回傳所有符合指定類型的訊息。"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            matching_messages = [
                msg for msg in self.received_messages if msg.get("type") == msg_type
            ]
            if matching_messages:
                return matching_messages
            time.sleep(0.2)
        return [] # 超時後回傳空列表

    def get_message_for_task(self, task_id: str, status: str, timeout: int = 15):
        """等待並回傳特定任務和狀態的訊息。"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            for msg in self.received_messages:
                payload = msg.get("payload", {})
                if payload.get("task_id") == task_id and payload.get("status") == status:
                    return msg
            time.sleep(0.2)
        return None # 超時


# --- 測試案例 ---

def test_full_transcription_workflow(live_server, tmp_path):
    """
    這是一個端對端的測試，它驗證了從上傳檔案到接收轉錄完成的
    WebSocket 通知為止的整個流程。

    這個測試目前預期會失敗，因為後端在完成任務後，無法成功地
    將 `TRANSCRIPTION_STATUS` 的 `completed` 訊息廣播回來。
    """
    base_url = live_server
    api_url = f"{base_url}/api"
    ws_url = f"{base_url.replace('http', 'ws')}/api/ws"

    # 1. 建立一個 WebSocket 客戶端來監聽事件
    ws_client = WebSocketClient(ws_url)
    ws_client.connect()
    assert ws_client.is_connected, "WebSocket 客戶端應成功連線。"

    # 2. 準備並上傳一個假的音訊檔案
    fake_audio_content = b"this is a test audio file"
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(fake_audio_content)

    files = {'file': ('test.mp3', audio_file.open('rb'), 'audio/mpeg')}
    data = {'model_size': 'tiny'}

    # 3. 透過 API 建立轉錄任務
    response = requests.post(f"{api_url}/transcribe", files=files, data=data, timeout=10)
    assert response.status_code == 202, f"建立轉錄任務時 API 應回傳 202 Accepted。回應: {response.text}"
    task_info = response.json()
    assert "task_id" in task_info, "API 回應中應包含 task_id。"
    task_id = task_info["task_id"]

    # 4. 透過 WebSocket 發送訊息以觸發任務執行
    ws_client.send({
        "type": "START_TRANSCRIPTION",
        "payload": {"task_id": task_id}
    })

    # 5. [失敗點] 等待並驗證 WebSocket 是否收到了 "completed" 狀態更新
    # 我們給予一個較長的超時時間，以確保任務有足夠的時間在背景完成。
    # 在當前的故障狀態下，這個步驟將會超時並回傳 None。
    completed_message = ws_client.get_message_for_task(task_id, "completed", timeout=TEST_TIMEOUT_SECONDS)

    # --- 斷言 ---
    # 這個斷言是測試的核心，目前預期會失敗
    assert completed_message is not None, f"應在 {TEST_TIMEOUT_SECONDS} 秒內收到 task '{task_id}' 的 'completed' WebSocket 訊息。"

    # 如果測試通過了上面的斷言（即我們修復了 bug），我們還需要驗證訊息的內容
    payload = completed_message.get("payload", {})
    assert payload.get("status") == "completed", "訊息的狀態應為 'completed'。"
    assert "result" in payload, "完成的訊息中應包含 'result' 欄位。"
    assert "transcript" in payload["result"], "結果中應包含 'transcript'。"
    assert "模擬的轉錄系統" in payload["result"]["transcript"], "結果應為模擬轉錄器的中文輸出。"

    # 6. 驗證最終的資料庫狀態
    # 在流程結束後，再次查詢 /api/tasks，確認該任務已被移至已完成列表
    time.sleep(1) # 等待資料庫寫入操作完成
    final_tasks_response = requests.get(f"{api_url}/tasks", timeout=10)
    assert final_tasks_response.status_code == 200
    all_tasks = final_tasks_response.json()

    completed_tasks = [t for t in all_tasks if t['status'] == 'completed']
    is_task_completed = any(t['task_id'] == task_id for t in completed_tasks)
    assert is_task_completed, f"任務 {task_id} 最終應出現在 /api/tasks 的已完成列表中。"

    # 7. 清理
    ws_client.close()
