import os
import sys
import subprocess
import logging
import time
import json
import requests
from pathlib import Path

# --- 設定區 ---
IDLE_TIMEOUT_SECONDS = 300
LOOP_SLEEP_SECONDS = 2
API_PORT = os.environ.get("API_PORT", 8001)
INTERNAL_API_URL = f"http://127.0.0.1:{API_PORT}/api/internal"
# --- 設定區結束 ---

# --- 延遲匯入和設定 ---
src_path = str(Path(__file__).resolve().parent / 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    from db.log_handler import setup_logging_for_module
    from db.client import get_client
except ImportError as e:
    print(f"嚴重錯誤：無法匯入必要的模組。請確認 'src' 目錄路徑是否正確且環境已設定。錯誤: {e}", file=sys.stderr)
    sys.exit(1)

# --- 日誌系統設定 ---
setup_logging_for_module("model_management_worker")
log = logging.getLogger(__name__)
db_client = get_client()

def notify_api_server(task_id, status, result):
    """通知 API 伺服器任務狀態已更新。"""
    try:
        url = f"{INTERNAL_API_URL}/notify_task_update"
        payload = {"task_id": task_id, "status": status, "result": result}
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        log.info(f"✅ 成功通知 API 伺服器任務 {task_id} 的更新。")
    except requests.exceptions.RequestException as e:
        log.error(f"❌ 通知 API 伺服器失敗: {e}")

def process_download_task(task):
    """處理單個下載任務。"""
    task_id = task['task_id']
    try:
        payload = json.loads(task['payload'])
        model_size = payload['model_size']
    except (json.JSONDecodeError, KeyError) as e:
        log.error(f"任務 {task_id} 的 payload 格式無效: {e}")
        db_client.update_task_status(task_id, 'failed', json.dumps({"error": "無效的 payload"}))
        return

    log.info(f"開始處理下載任務 {task_id}，模型: {model_size}")

    is_mock_mode = os.environ.get("API_MODE", "real") == "mock"
    root_dir = Path(__file__).resolve().parent
    tool_script_path = root_dir / "src" / "tools" / ("mock_transcriber.py" if is_mock_mode else "transcriber.py")
    cmd = [sys.executable, str(tool_script_path), "--command=download", f"--model_size={model_size}"]

    try:
        # 這裡我們不即時串流進度，因為這個 worker 是在背景執行的。
        # 進度條的即時更新由 api_server 中的 trigger_model_download 處理，
        # 而那個函數是由 WebSocket 直接觸發的。
        # 這個輪詢工作者是作為一個備用和更穩定的機制。
        # 為了保持一致，我們還是讓它也觸發即時進度。
        # 最好的方法是讓此工作者也發送 WebSocket 訊息，但這需要重構。
        # 折衷方案：讓此工作者呼叫 trigger_model_download，但这會造成循環依賴。
        # 正確的作法：讓 trigger_model_download 成為一個共享的工具函數。
        # 為了快速修復，我們暫時不從這裡發送即時進度，只在結束時更新狀態。

        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=600)

        if process.returncode == 0:
            log.info(f"✅ 模型 '{model_size}' 下載成功 (任務 {task_id})。")
            result = {"status": "completed", "model": model_size}
            db_client.update_task_status(task_id, 'completed', json.dumps(result))
            notify_api_server(task_id, 'completed', result)
        else:
            error_message = f"下載腳本執行失敗: {process.stderr}"
            log.error(f"❌ {error_message} (任務 {task_id})")
            result = {"error": error_message}
            db_client.update_task_status(task_id, 'failed', json.dumps(result))
            notify_api_server(task_id, 'failed', result)

    except subprocess.TimeoutExpired:
        error_message = "模型下載超時 (600秒)。"
        log.error(f"❌ {error_message} (任務 {task_id})")
        result = {"error": error_message}
        db_client.update_task_status(task_id, 'failed', json.dumps(result))
        notify_api_server(task_id, 'failed', result)
    except Exception as e:
        error_message = f"執行下載任務時發生未預期錯誤: {e}"
        log.error(f"❌ {error_message}", exc_info=True)
        result = {"error": error_message}
        db_client.update_task_status(task_id, 'failed', json.dumps(result))
        notify_api_server(task_id, 'failed', result)

def run_worker():
    """工作者主迴圈。"""
    log.info("模型管理工作者已啟動，開始輪詢 'download' 類型的任務...")
    while True:
        try:
            task = db_client.fetch_and_lock_task_by_type('download')
            if task:
                process_download_task(task)
            else:
                # 如果沒有任務，則休眠
                time.sleep(LOOP_SLEEP_SECONDS)
        except Exception as e:
            log.error(f"工作者主迴圈發生錯誤: {e}", exc_info=True)
            time.sleep(10) # 發生錯誤時，等待更長時間再重試

if __name__ == "__main__":
    run_worker()
