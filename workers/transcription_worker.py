# workers/transcription_worker.py
import time
import traceback
import json
import logging
import sys
import requests
from pathlib import Path

# --- 路徑設定，確保可以導入 src 目錄下的模組 ---
# 將專案根目錄添加到 sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from src.db.client import DBClient, get_client

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- Worker 設定 ---
WORKER_TYPE = "transcribe"
POLL_INTERVAL_SECONDS = 5 # 當沒有任務時，輪詢的間隔時間
API_PORT = 8000 # API 伺服器在 Colabpro.py 中被固定在 8000
WORKER_STATUS_URL = f"http://127.0.0.1:{API_PORT}/api/internal/worker_status"
NOTIFY_URL = f"http://127.0.0.1:{API_PORT}/api/internal/notify_update"

def notify_api_server(payload: dict):
    """向主 API 伺服器發送一個通知請求，以觸發 WebSocket 廣播。"""
    try:
        requests.post(NOTIFY_URL, json=payload, timeout=5)
    except requests.RequestException as e:
        log.error(f"無法發送通知到 API 伺服器: {e}")

def process_task(db_client: DBClient, task: dict):
    """
    處理單一轉錄任務的核心邏輯。
    """
    task_id = task['task_id']
    log.info(f"✅ [TID: {task_id}] 開始處理 '{WORKER_TYPE}' 類型任務。")

    try:
        # 1. 將狀態更新為 'running' 並發送通知
        db_client.update_task_status(task_id, 'running')
        notify_api_server({"event": "tasks_changed", "task_id": task_id})

        # 2. 解析 payload
        try:
            payload = json.loads(task['payload'])
            original_filename = payload.get('original_filename', '未知檔案')
            log.info(f"[TID: {task_id}] 任務 payload 解析成功，檔名: {original_filename}")
        except json.JSONDecodeError:
            raise ValueError("無效的 JSON payload")

        # 3. 執行模擬工作並更新進度
        log.info(f"[TID: {task_id}] 正在進行模擬轉錄... (將耗時 10 秒)")
        for i in range(10):
            progress = (i + 1) * 10
            db_client.update_task_progress(task_id, progress, f"部分結果 {i+1}...")
            # 每次進度更新都發送通知
            notify_api_server({"event": "tasks_changed", "task_id": task_id})
            time.sleep(1)

        result_text = f"這是 '{original_filename}' 的完整轉錄結果。"
        final_result = json.dumps({"transcription": result_text})

        # 4. 工作完成，更新狀態為 'completed' 並發送通知
        log.info(f"✅ [TID: {task_id}] 轉錄成功。")
        db_client.update_task_status(task_id, 'completed', result=final_result)
        notify_api_server({"event": "tasks_changed", "task_id": task_id})

    except Exception as e:
        error_message = f"處理任務時發生錯誤: {str(e)}"
        log.error(f"❌ [TID: {task_id}] {error_message}\n{traceback.format_exc()}")
        # 5. 如果發生錯誤，更新狀態為 'failed' 並發送通知
        db_client.update_task_status(task_id, 'failed', result=json.dumps({"error": error_message}))
        notify_api_server({"event": "tasks_changed", "task_id": task_id})

def main():
    """
    工作者的主迴圈。
    """
    log.info(f"🚀 '{WORKER_TYPE}' 工作者已啟動，開始輪詢資料庫...")
    # 確保 requests 套件已安裝
    try:
        import requests
    except ImportError:
        log.error("`requests` 套件未安裝。請執行 `pip install requests`。")
        sys.exit(1)

    # 在進入主迴圈之前，先向 API 伺服器回報「準備就緒」狀態
    try:
        log.info("正在回報 'ready' 狀態給 API 伺服器...")
        requests.post(
            f"http://127.0.0.1:{API_PORT}/api/internal/worker_status",
            json={"service": "transcription", "status": "ready"},
            timeout=5
        )
        log.info("✅ 'ready' 狀態回報成功。")
    except requests.RequestException as e:
        log.error(f"❌ 無法回報 'ready' 狀態給 API 伺服器: {e}")
        # 即使回報失敗，我們仍然可以繼續嘗試處理任務，因為核心功能依賴資料庫輪詢

    db_client = get_client()

    while True:
        try:
            # 1. 從資料庫獲取並鎖定一個待處理的任務
            task = db_client.fetch_and_lock_task_by_type(WORKER_TYPE)

            if task:
                # 2. 如果有任務，就處理它
                process_task(db_client, task)
            else:
                # 3. 如果沒有任務，就等待一段時間
                log.debug(f"佇列中無 '{WORKER_TYPE}' 任務，將在 {POLL_INTERVAL_SECONDS} 秒後重試。")
                time.sleep(POLL_INTERVAL_SECONDS)

        except Exception as e:
            # 捕獲主迴圈中的意外錯誤（例如與 DB Manager 的連線中斷）
            log.critical(f"工作者主迴圈發生嚴重錯誤: {e}", exc_info=True)
            log.info(f"將在 {POLL_INTERVAL_SECONDS * 2} 秒後嘗試重新連線和輪詢...")
            time.sleep(POLL_INTERVAL_SECONDS * 2)

if __name__ == "__main__":
    main()
