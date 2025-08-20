# db/client.py
import socket
import json
import logging
import time
from pathlib import Path

# --- 日誌設定 ---
log = logging.getLogger('DBClient')

# --- 客戶端設定 ---
PORT_FILE = Path(__file__).parent / "db_manager.port"
RETRY_TIMEOUT = 10  # 秒

class DBClient:
    """
    與 DBManagerServer 進行通訊的客戶端。
    """
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = self._get_server_port()

    def _get_server_port(self) -> int:
        """
        從 .port 檔案讀取伺服器埠號，並包含重試機制。
        """
        start_time = time.time()
        while time.time() - start_time < RETRY_TIMEOUT:
            if PORT_FILE.exists():
                try:
                    port = int(PORT_FILE.read_text())
                    log.info(f"從 {PORT_FILE} 成功讀取到 DB Manager 埠號: {port}")
                    return port
                except (ValueError, IOError) as e:
                    log.warning(f"讀取埠號檔案時發生錯誤: {e}，正在重試...")
            else:
                log.info(f"埠號檔案 {PORT_FILE} 尚不存在，正在等待...")
            time.sleep(0.5)
        raise RuntimeError(f"在 {RETRY_TIMEOUT} 秒內未能找到 DB Manager 的埠號檔案。")

    def _send_request(self, action: str, params: dict = None) -> dict:
        """
        一個私有的輔助方法，用於發送請求並接收回應。
        """
        if params is None:
            params = {}

        request_data = {
            "action": action,
            "params": params
        }

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((self.host, self.port))
                request_bytes = json.dumps(request_data).encode('utf-8')
                request_header = len(request_bytes).to_bytes(4, 'big')
                sock.sendall(request_header + request_bytes)

                response_header = sock.recv(4)
                if not response_header:
                    raise ConnectionError("與伺服器的連線已中斷，未能收到回應標頭。")
                response_len = int.from_bytes(response_header, 'big')

                response_chunks = []
                bytes_received = 0
                while bytes_received < response_len:
                    chunk = sock.recv(min(response_len - bytes_received, 4096))
                    if not chunk:
                        raise ConnectionError("與伺服器的連線已中斷，資料接收不完整。")
                    response_chunks.append(chunk)
                    bytes_received += len(chunk)
                response_bytes = b"".join(response_chunks)
                response = json.loads(response_bytes.decode('utf-8'))

                if response.get("status") == "error":
                    error_message = response.get("message", "未知錯誤")
                    log.error(f"伺服器在處理 action '{action}' 時回傳錯誤: {error_message}")
                    raise RuntimeError(f"DB Manager Server Error: {error_message}")
                return response.get("data")
        except ConnectionRefusedError:
            log.error(f"連線被拒絕。請確保 DB 管理者伺服器正在 {self.host}:{self.port} 上運行。")
            raise
        except Exception as e:
            log.error(f"與 DB 管理者伺服器通訊時發生未預期錯誤: {e}", exc_info=True)
            raise

    def add_task(self, task_id: str, payload: str, task_type: str = 'transcribe', depends_on: str = None) -> bool:
        return self._send_request("add_task", {"task_id": task_id, "payload": payload, "task_type": task_type, "depends_on": depends_on})
    def fetch_and_lock_task(self) -> dict | None:
        return self._send_request("fetch_and_lock_task")
    def fetch_and_lock_task_by_type(self, task_type: str) -> dict | None:
        return self._send_request("fetch_and_lock_task_by_type", {"task_type": task_type})
    def update_task_progress(self, task_id: str, progress: int, partial_result: str):
        return self._send_request("update_task_progress", {"task_id": task_id, "progress": progress, "partial_result": partial_result})
    def update_task_status(self, task_id: str, status: str, result: str = None):
        return self._send_request("update_task_status", {"task_id": task_id, "status": status, "result": result})
    def get_task_status(self, task_id: str) -> dict | None:
        return self._send_request("get_task_status", {"task_id": task_id})
    def are_tasks_active(self) -> bool:
        return self._send_request("are_tasks_active")
    def get_all_tasks(self) -> list[dict]:
        return self._send_request("get_all_tasks")
    def get_system_logs(self, levels: list[str] = None, sources: list[str] = None) -> list[dict]:
        return self._send_request("get_system_logs", {"levels": levels or [], "sources": sources or []})

    def add_system_log(self, source: str, level: str, message: str) -> bool:
        return self._send_request("add_system_log", {"source": source, "level": level, "message": message})

    def add_system_logs_batch(self, logs: list) -> bool:
        """將一批日誌發送到伺服器。"""
        return self._send_request("add_system_logs_batch", {"logs": logs})

    def find_dependent_task(self, parent_task_id: str) -> str | None:
        return self._send_request("find_dependent_task", {"parent_task_id": parent_task_id})
    def get_app_state(self, key: str) -> str | None:
        return self._send_request("get_app_state", {"key": key})
    def set_app_state(self, key: str, value: str) -> bool:
        return self._send_request("set_app_state", {"key": key, "value": value})
    def check_tables_exist(self) -> tuple[bool, str]:
        return self._send_request("check_tables_exist")
    def delete_task(self, task_id: str) -> bool:
        return self._send_request("delete_task", {"task_id": task_id})

_client_instance = None
def get_client():
    global _client_instance
    if _client_instance is None:
        log.info("正在建立一個新的 DBClient 實例...")
        _client_instance = DBClient()
    return _client_instance
