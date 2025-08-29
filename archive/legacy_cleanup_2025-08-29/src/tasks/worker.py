# worker.py
import time
import logging
import json
import subprocess
import sys
import argparse
import requests
import os
from pathlib import Path

# --- 路徑設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = ROOT_DIR / "src" / "tools"
TRANSCRIPTS_DIR = ROOT_DIR / "transcripts"

# --- 依賴匯入 ---
from db.client import get_client

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger('worker')

def setup_database_logging():
    """設定資料庫日誌處理器。"""
    try:
        from db.log_handler import DatabaseLogHandler
        root_logger = logging.getLogger()
        if not any(isinstance(h, DatabaseLogHandler) for h in root_logger.handlers):
            root_logger.addHandler(DatabaseLogHandler(source='worker'))
            log.info("資料庫日誌處理器設定完成 (source: worker)。")
    except Exception as e:
        log.error(f"整合資料庫日誌時發生錯誤: {e}", exc_info=True)

# --- DB 客戶端 ---
db_client = get_client()

def process_transcription_task(task: dict, use_mock: bool):
    """處理音訊轉錄任務。"""
    task_id = task['task_id']
    log.info(f"🚀 開始處理 'transcribe' 任務: {task_id}")
    try:
        payload = json.loads(task['payload'])
        input_file = Path(payload['input_file'])
        model_size = payload.get('model_size', 'tiny')
        language = payload.get('language')

        if use_mock:
            log.info(f"✅ (模擬) 處理任務: {task_id}")
            time.sleep(2)
            final_transcript = "這是一個模擬的轉錄結果。"
            TRANSCRIPTS_DIR.mkdir(exist_ok=True)
            output_file = TRANSCRIPTS_DIR / f"{task_id}.txt"
            output_file.write_text(final_transcript, encoding='utf-8')

            final_result = json.dumps({
                "transcript": final_transcript,
                "transcript_path": str(output_file),
                "tool_stdout": "Mock process completed successfully.",
            })
            db_client.update_task_status(task_id, 'completed', final_result)
            log.info(f"✅ (模擬) 任務 {task_id} 狀態已更新至資料庫。")

            try:
                api_port = os.environ.get('API_PORT', 42649)
                notify_url = f"http://127.0.0.1:{api_port}/api/internal/notify_task_update"
                frontend_payload = {
                    "task_id": task_id, "status": "completed", "result": json.loads(final_result)
                }
                requests.post(notify_url, json=frontend_payload, timeout=5)
                log.info(f"✅ (模擬) 已成功發送完成通知給 API Server: {task_id}")
            except requests.exceptions.RequestException as e:
                log.error(f"❌ (模擬) 發送完成通知給 API Server 失敗: {e}")
            return

        # Real mode logic is not part of this fix, assuming it's correct
        # ...

    except Exception as e:
        log.critical(f"💥 處理任務 {task_id} 時發生未預期的嚴重錯誤: {e}", exc_info=True)
        db_client.update_task_status(task_id, 'failed', json.dumps({"error": str(e)}))

def process_task(task: dict, use_mock: bool):
    """根據任務類型分派到不同的處理函式。"""
    task_type = task.get('type', 'transcribe')
    if task_type == 'transcribe':
        process_transcription_task(task, use_mock)
    else:
        # In a real scenario, handle other task types like 'download'
        log.error(f"❌ 未知的任務類型: '{task_type}' (Task ID: {task['task_id']})")
        db_client.update_task_status(task['task_id'], 'failed', json.dumps({"error": f"未知的任務類型: {task_type}"}))

def main_loop(use_mock: bool, poll_interval: int):
    """工人的主迴圈。"""
    log.info(f"🤖 Worker 已啟動。模式: {'模擬 (Mock)' if use_mock else '真實 (Real)'}。查詢間隔: {poll_interval} 秒。")
    try:
        while True:
            task = db_client.fetch_and_lock_task()
            if task:
                process_task(task, use_mock)
            else:
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        log.info("🛑 收到中斷信號，Worker 正在關閉...")
    except Exception as e:
        log.critical(f"🔥 Worker 主迴圈發生致命錯誤: {e}", exc_info=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="背景工作處理器。")
    parser.add_argument("--mock", action="store_true", help="如果設置此旗標，則使用 mock_transcriber.py 進行測試。")
    parser.add_argument("--poll-interval", type=int, default=2, help="輪詢間隔（秒）。")
    args = parser.parse_args()

    setup_database_logging()
    main_loop(args.mock, args.poll_interval)
