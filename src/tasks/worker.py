# worker.py
import time
import logging
import json
import subprocess
import sys
import argparse
import requests
from pathlib import Path

# 將專案根目錄加入 sys.path
# 因為此檔案現在位於 src/tasks/ 中，所以根目錄是其上上層目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
# sys.path hack 不再需要，因為我們現在使用 `pip install -e .`
# sys.path.insert(0, str(ROOT_DIR))

# JULES'S REFACTOR: Use the database client instead of direct access
# from db import database
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

# --- 路徑設定 ---
TOOLS_DIR = ROOT_DIR / "src" / "tools"
TRANSCRIPTS_DIR = ROOT_DIR / "transcripts"

# --- DB 客戶端 ---
db_client = get_client()

def process_download_task(task: dict, use_mock: bool):
    """處理模型下載任務。"""
    task_id = task['task_id']
    payload = json.loads(task['payload'])
    model_size = payload['model_size']
    log.info(f"🚀 開始處理 'download' 任務: {task_id} for model '{model_size}'")

    # 在模擬模式下，我們也假裝下載
    if use_mock:
        log.info("(模擬) 假裝下載模型...")
        time.sleep(3)
        db_client.update_task_status(task_id, 'completed', json.dumps({"message": "模型已成功下載 (模擬)"}))
        return

    # 真實模式下，呼叫工具的 download 命令
    tool_script_path = TOOLS_DIR / "transcriber.py"
    command = [sys.executable, str(tool_script_path), f"--command=download", f"--model_size={model_size}"]

    # 我們可以像轉錄一樣監聽進度，但 download_model 目前只在結束時輸出一次
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')

    for line in process.stdout:
        try:
            progress_data = json.loads(line)
            db_client.update_task_progress(task_id, progress_data.get("progress", 0), progress_data.get("log", ""))
        except json.JSONDecodeError:
            log.info(f"[下載工具 stdout] {line.strip()}")

    process.wait()
    if process.returncode == 0:
        db_client.update_task_status(task_id, 'completed', json.dumps({"message": f"模型 {model_size} 已成功下載"}))
    else:
        log.error(f"❌ 下載模型 {model_size} 失敗。")
        db_client.update_task_status(task_id, 'failed', json.dumps({"error": f"下載模型 {model_size} 失敗"}))


def process_transcription_task(task: dict, use_mock: bool):
    """處理音訊轉錄任務。"""
    task_id = task['task_id']
    log.info(f"🚀 開始處理 'transcribe' 任務: {task_id}")
    try:
        payload = json.loads(task['payload'])
        input_file = Path(payload['input_file'])
        model_size = payload.get('model_size', 'tiny')
        language = payload.get('language')

        if not input_file.exists():
            raise FileNotFoundError(f"輸入檔案不存在: {input_file}")

        # 1. 決定要使用的工具
        tool_script_name = "mock_transcriber.py" if use_mock else "transcriber.py"
        tool_script_path = TOOLS_DIR / tool_script_name
        if not tool_script_path.exists():
             raise FileNotFoundError(f"工具腳本不存在: {tool_script_path}")

        # 2. 準備輸出路徑
        TRANSCRIPTS_DIR.mkdir(exist_ok=True)
        output_file = TRANSCRIPTS_DIR / f"{task_id}.txt"

        # 3. 構建並執行命令
        command = [
            sys.executable,
            str(tool_script_path),
            f"--command=transcribe", # 明確指定命令
            f"--audio_file={input_file}",
            f"--output_file={output_file}",
            f"--model_size={model_size}"
        ]
        if language:
            command.append(f"--language={language}")

        log.info(f"🔧 執行命令: {' '.join(command)}")

        # 改用 Popen 進行非阻塞式讀取
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')

        # 4. 即時讀取 stdout 來更新進度
        full_stdout = []
        full_stderr = []

        # 使用緒來避免阻塞
        def read_stderr():
            for line in process.stderr:
                full_stderr.append(line)
                log.warning(f"[工具 stderr] {line.strip()}")

        import threading
        stderr_thread = threading.Thread(target=read_stderr)
        stderr_thread.start()

        for line in process.stdout:
            full_stdout.append(line)
            try:
                # 解析 JSON 進度
                progress_data = json.loads(line)
                progress = progress_data.get("progress")
                text = progress_data.get("text")
                if progress is not None:
                    log.info(f"📈 任務 {task_id} 進度: {progress}% - {text[:30]}...")
                    db_client.update_task_progress(task_id, progress, text)
            except json.JSONDecodeError:
                # 不是 JSON 格式的日誌，直接印出
                log.info(f"[工具 stdout] {line.strip()}")

        process.wait()
        stderr_thread.join()

        # 5. 處理最終結果
        if process.returncode == 0:
            log.info(f"✅ 工具成功完成任務: {task_id}")
            final_transcript = output_file.read_text(encoding='utf-8').strip()
            final_result = json.dumps({
                "transcript": final_transcript,
                "transcript_path": str(output_file), # 新增此行，為下載 API 提供路徑
                "tool_stdout": "".join(full_stdout),
            })
            db_client.update_task_status(task_id, 'completed', final_result)
            log.info(f"✅ 任務 {task_id} 狀態已更新至資料庫。")

            # 步驟 6: 通知 API Server 任務已完成，以便廣播給前端
            try:
                # JULES'S FIX: 從環境變數讀取動態 API port，如果不存在則回退到預設值
                api_port = os.environ.get('API_PORT', 42649)
                notify_url = f"http://127.0.0.1:{api_port}/api/internal/notify_task_update"

                # 我們只傳送前端 UI 更新所需的最小資訊
                frontend_payload = {
                    "task_id": task_id,
                    "status": "completed",
                    # 傳送結果，讓前端可以直接使用，例如顯示下載按鈕
                    "result": json.loads(final_result)
                }

                requests.post(notify_url, json=frontend_payload, timeout=5)
                log.info(f"✅ 已成功發送完成通知給 API Server: {task_id}")
            except requests.exceptions.RequestException as e:
                log.error(f"❌ 發送完成通知給 API Server 失敗: {e}")

        else:
            log.error(f"❌ 工具執行任務失敗: {task_id}。返回碼: {process.returncode}")
            error_message = "".join(full_stderr) or "".join(full_stdout) or "未知錯誤"
            final_result = json.dumps({
                "error": error_message,
                "tool_stdout": "".join(full_stdout),
                "tool_stderr": "".join(full_stderr)
            })
            db_client.update_task_status(task_id, 'failed', final_result)

    except Exception as e:
        log.critical(f"💥 處理任務 {task_id} 時發生未預期的嚴重錯誤: {e}", exc_info=True)
        db_client.update_task_status(task_id, 'failed', json.dumps({"error": str(e)}))


def process_task(task: dict, use_mock: bool):
    """
    根據任務類型分派到不同的處理函式。
    """
    task_type = task.get('type', 'transcribe') # 預設為舊的轉錄任務
    if task_type == 'download':
        process_download_task(task, use_mock)
    elif task_type == 'transcribe':
        process_transcription_task(task, use_mock)
    else:
        log.error(f"❌ 未知的任務類型: '{task_type}' (Task ID: {task['task_id']})")
        db_client.update_task_status(task['task_id'], 'failed', json.dumps({"error": f"未知的任務類型: {task_type}"}))

def main_loop(use_mock: bool, poll_interval: int):
    """
    工人的主迴圈，持續從佇列中拉取並處理任務。
    """
    log.info(f"🤖 Worker 已啟動。模式: {'模擬 (Mock)' if use_mock else '真實 (Real)'}。查詢間隔: {poll_interval} 秒。")
    try:
        while True:
            task = db_client.fetch_and_lock_task()
            if task:
                process_task(task, use_mock)
            else:
                # 佇列為空，稍作等待
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        log.info("🛑 收到中斷信號，Worker 正在關閉...")
    except Exception as e:
        log.critical(f"🔥 Worker 主迴圈發生致命錯誤: {e}", exc_info=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="背景工作處理器。")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="如果設置此旗標，則使用 mock_transcriber.py 進行測試。"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=5,
        help="當佇列為空時，輪詢資料庫的間隔時間（秒）。"
    )
    args = parser.parse_args()

    # JULES'S REFACTOR: The worker no longer initializes the database directly.
    # The db_manager service is responsible for this.
    # database.initialize_database()

    # 然後設定日誌
    setup_database_logging()

    main_loop(args.mock, args.poll_interval)
