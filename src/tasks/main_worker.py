# src/tasks/main_worker.py
import logging
import json
import os
import subprocess
import sys
import time
import requests
from pathlib import Path

# --- 路徑設定 ---
# 假設此檔案位於 src/tasks/，專案根目錄是其上兩層
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
# 將 src 目錄加入 sys.path 以便匯入 db 模組
sys.path.insert(0, str(ROOT_DIR / 'src'))

# --- 設定區 ---
LOOP_SLEEP_SECONDS = 2
API_PORT = os.environ.get("API_PORT", 8001)
INTERNAL_API_URL = f"http://127.0.0.1:{API_PORT}/api/internal"
IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"
# --- 設定區結束 ---

# --- 延遲匯入 ---
try:
    # JULES'S FIX (2025-08-21): 修正導入錯誤
    # 移除了對不存在的 `setup_logging_for_module` 的導入。
    # 日誌處理現在由父程序 (orchestrator) 統一設定，子程序只需獲取 logger 即可。
    from db.client import get_client
except ImportError as e:
    # 保留這個錯誤處理，以防未來出現其他匯入問題
    print(f"嚴重錯誤：無法匯入必要的模組。請確認 'src' 目錄路徑是否正確且環境已設定。錯誤: {e}", file=sys.stderr)
    sys.exit(1)

# --- 日誌與資料庫用戶端設定 ---
# JULES'S FIX (2025-08-21): 移除對已廢棄函式的呼叫
# setup_logging_for_module("main_worker")
log = logging.getLogger("main_worker") # 為 logger 指定一個清晰的名稱
db_client = get_client()

def notify_api_server(task_id: str, status: str, result: dict):
    """通知 API 伺服器任務狀態已更新，以便透過 WebSocket 廣播。"""
    try:
        url = f"{INTERNAL_API_URL}/notify_task_update"
        payload = {"task_id": task_id, "status": status, "result": result}
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        log.info(f"✅ 成功通知 API 伺服器任務 {task_id} 的更新。")
    except requests.exceptions.RequestException as e:
        log.error(f"❌ 通知 API 伺服器失敗 (任務 ID: {task_id}): {e}")

def process_download_model_task(task: dict):
    """處理 'download_model' 類型的任務。"""
    task_id = task['task_id']
    log.info(f"開始處理模型下載任務 {task_id}...")
    try:
        payload = json.loads(task['payload'])
        model_size = payload['model_size']

        tool_script_path = ROOT_DIR / "src" / "tools" / ("mock_transcriber.py" if IS_MOCK_MODE else "transcriber.py")
        cmd = [sys.executable, str(tool_script_path), "--command=download", f"--model_size={model_size}"]

        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=600)

        if process.returncode == 0:
            log.info(f"✅ 模型 '{model_size}' 下載成功 (任務 {task_id})。")
            result = {"status": "completed", "model_size": model_size}
            db_client.update_task_status(task_id, 'completed', json.dumps(result))
            notify_api_server(task_id, 'completed', result)
        else:
            error_message = f"模型下載腳本執行失敗: {process.stderr}"
            raise RuntimeError(error_message)

    except Exception as e:
        log.error(f"❌ 處理模型下載任務 {task_id} 時發生錯誤: {e}", exc_info=True)
        result = {"error": str(e)}
        db_client.update_task_status(task_id, 'failed', json.dumps(result))
        notify_api_server(task_id, 'failed', result)

def process_youtube_download_task(task: dict):
    """處理 'youtube_download' 和 'youtube_download_only' 類型的任務。"""
    task_id = task['task_id']
    task_type = task['type']
    log.info(f"開始處理 YouTube 下載任務 {task_id} (類型: {task_type})...")

    try:
        payload = json.loads(task['payload'])
        url = payload['url']

        downloader_script = "mock_youtube_downloader.py" if IS_MOCK_MODE else "youtube_downloader.py"
        tool_script_path = ROOT_DIR / "src" / "tools" / downloader_script

        cmd = [
            sys.executable, str(tool_script_path),
            "--url", url,
            "--output-dir", str(ROOT_DIR / "uploads")
        ]
        if payload.get("custom_filename"):
            cmd.extend(["--custom-filename", payload["custom_filename"]])
        if payload.get("download_type"):
            cmd.extend(["--download-type", payload["download_type"]])

        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=1800)

        if process.returncode == 0:
            log.info(f"✅ YouTube 下載成功 (任務 {task_id})。")
            result = json.loads(process.stdout)
            db_client.update_task_status(task_id, 'completed', json.dumps(result))
            notify_api_server(task_id, 'completed', result)
        else:
            raise RuntimeError(f"YouTube 下載腳本執行失敗: {process.stderr}")

    except Exception as e:
        log.error(f"❌ 處理 YouTube 下載任務 {task_id} 時發生錯誤: {e}", exc_info=True)
        result = {"error": str(e)}
        db_client.update_task_status(task_id, 'failed', json.dumps(result))
        notify_api_server(task_id, 'failed', result)

def process_gemini_process_task(task: dict):
    """處理 'gemini_process' 類型的任務。"""
    task_id = task['task_id']
    log.info(f"開始處理 Gemini 分析任務 {task_id}...")
    try:
        payload = json.loads(task['payload'])

        # 依賴任務的結果 (包含下載的音訊檔案路徑)
        depends_on_id = task['depends_on']
        if not depends_on_id:
            raise ValueError("Gemini 分析任務缺少 `depends_on` 欄位。")

        parent_task = db_client.get_task_status(depends_on_id)
        if not parent_task or parent_task['status'] != 'completed':
            raise RuntimeError(f"父任務 {depends_on_id} 尚未完成，無法開始分析。")

        parent_result = json.loads(parent_task['result'])
        audio_file_path = parent_result['output_path']
        video_title = parent_result.get('video_title', '無標題影片')

        processor_script = "mock_gemini_processor.py" if IS_MOCK_MODE else "gemini_processor.py"
        tool_script_path = ROOT_DIR / "src" / "tools" / processor_script

        report_output_dir = ROOT_DIR / "uploads" / "reports"
        report_output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, str(tool_script_path),
            "--command=process",
            "--audio-file", audio_file_path,
            "--model", payload['model'],
            "--output-dir", str(report_output_dir),
            "--video-title", video_title,
            "--tasks", payload.get('tasks', 'summary,transcript'),
            "--output-format", payload.get('output_format', 'html')
        ]

        env = os.environ.copy()
        if payload.get('api_key'):
            env["GOOGLE_API_KEY"] = payload['api_key']

        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=1800, env=env)

        if process.returncode == 0:
            log.info(f"✅ Gemini 分析成功 (任務 {task_id})。")
            result = json.loads(process.stdout)
            db_client.update_task_status(task_id, 'completed', json.dumps(result))
            notify_api_server(task_id, 'completed', result)
        else:
            raise RuntimeError(f"Gemini 分析腳本執行失敗: {process.stderr}")

    except Exception as e:
        log.error(f"❌ 處理 Gemini 分析任務 {task_id} 時發生錯誤: {e}", exc_info=True)
        result = {"error": str(e)}
        db_client.update_task_status(task_id, 'failed', json.dumps(result))
        notify_api_server(task_id, 'failed', result)


TASK_HANDLERS = {
    "download_model": process_download_model_task,
    "youtube_download": process_youtube_download_task,
    "youtube_download_only": process_youtube_download_task,
    "gemini_process": process_gemini_process_task,
}

def run_worker():
    """工作者主迴圈，輪詢並處理任務。"""
    log.info("🚀 主要背景任務工作者已啟動，開始輪詢資料庫...")
    while True:
        try:
            task_found_in_loop = False
            # 迭代所有可處理的任務類型
            for task_type in TASK_HANDLERS.keys():
                task = db_client.fetch_and_lock_task_by_type(task_type)

                if task:
                    task_found_in_loop = True
                    log.info(f"從資料庫獲取到新任務: ID {task['task_id']}, 類型 {task_type}")
                    handler = TASK_HANDLERS[task_type]
                    handler(task)
                    # 處理完一個任務後，立即重新開始循環以獲取下一個任務，提高反應速度
                    break

            # 如果整個循環都沒有找到任務，則休眠
            if not task_found_in_loop:
                time.sleep(LOOP_SLEEP_SECONDS)

        except Exception as e:
            log.error(f"工作者主迴圈發生嚴重錯誤: {e}", exc_info=True)
            # 發生嚴重錯誤時，等待更長時間再重試，避免癱瘓系統
            time.sleep(10)

if __name__ == "__main__":
    run_worker()
