import time
import traceback
import os
import sys
import subprocess
import json
import requests
from pathlib import Path
from src.core.queue_config import huey

API_PORT = os.environ.get("API_PORT", 8000)
API_URL = f"http://127.0.0.1:{API_PORT}/api/internal/task_update"

def post_status_update(task_id: str, status: str, result: dict = None, error: str = None):
    """向主 API 伺服器發送任務狀態更新。"""
    try:
        payload = {"task_id": task_id, "status": status, "result": result, "error": error}
        requests.post(API_URL, json=payload, timeout=5)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: 工作者無法回報任務狀態 (ID: {task_id}): {e}", file=sys.stderr)

@huey.task()
def process_transcription(task_id: str, file_path: str, original_filename: str):
    print(f"--- [Task ID: {task_id}] 開始處理任務: {original_filename} ---")
    try:
        post_status_update(task_id, "processing")

        print(f"INFO: [Task ID: {task_id}] 正在進行模擬轉錄...")
        time.sleep(10)
        result_text = f"這是 '{original_filename}' 的模擬轉錄結果。"

        print(f"SUCCESS: [Task ID: {task_id}] 轉錄完成")
        post_status_update(task_id, "completed", result={"transcription": result_text})
    except Exception as e:
        error_message = f"處理失敗: {str(e)}"
        print(f"ERROR: [Task ID: {task_id}] {error_message}\n{traceback.format_exc()}", file=sys.stderr)
        post_status_update(task_id, "failed", error=error_message)
    finally:
        print(f"--- [Task ID: {task_id}] 任務處理流程結束 ---")

@huey.task()
def download_model_task(model_size: str):
    task_id = f"download_{model_size}_{int(time.time())}"
    print(f"--- [Task ID: {task_id}] 開始下載模型: {model_size} ---")
    try:
        IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"
        ROOT_DIR = Path(__file__).resolve().parent.parent
        tool_script_path = ROOT_DIR / "src" / "tools" / ("mock_transcriber.py" if IS_MOCK_MODE else "transcriber.py")
        cmd = [sys.executable, str(tool_script_path), "--command=download", f"--model_size={model_size}"]
        subprocess.run(cmd, check=True, text=True, encoding='utf-8', timeout=600)
        print(f"SUCCESS: [Task ID: {task_id}] 模型 '{model_size}' 下載成功。")
    except Exception as e:
        print(f"ERROR: [Task ID: {task_id}] 下載模型時發生錯誤: {e}\n{traceback.format_exc()}", file=sys.stderr)

@huey.task()
def youtube_download_task(url: str, custom_filename: str, download_type: str):
    task_id = f"yt_dl_{int(time.time())}"
    print(f"--- [Task ID: {task_id}] 開始下載 YouTube 影片: {url} ---")
    try:
        IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"
        downloader_script = "mock_youtube_downloader.py" if IS_MOCK_MODE else "youtube_downloader.py"
        ROOT_DIR = Path(__file__).resolve().parent.parent
        tool_script_path = ROOT_DIR / "src" / "tools" / downloader_script
        cmd = [sys.executable, str(tool_script_path), "--url", url, "--output-dir", str(ROOT_DIR / "uploads")]
        if custom_filename:
            cmd.extend(["--custom-filename", custom_filename])
        if download_type:
            cmd.extend(["--download-type", download_type])
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=1800, check=True)
        result = json.loads(process.stdout)
        print(f"SUCCESS: [Task ID: {task_id}] YouTube 下載成功。結果: {result}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"ERROR: [Task ID: {task_id}] YouTube 下載腳本執行失敗: {e.stderr}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"CRITICAL: [Task ID: {task_id}] 下載 YouTube 影片時發生未預期錯誤: {e}\n{traceback.format_exc()}", file=sys.stderr)
        raise

@huey.task()
def gemini_process_task(download_result: dict, model: str, api_key: str, tasks: str, output_format: str):
    task_id = f"gemini_proc_{int(time.time())}"
    print(f"--- [Task ID: {task_id}] 開始處理 Gemini 分析任務 ---")
    try:
        audio_file_path = download_result['output_path']
        video_title = download_result.get('video_title', '無標題影片')
        IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"
        processor_script = "mock_gemini_processor.py" if IS_MOCK_MODE else "gemini_processor.py"
        ROOT_DIR = Path(__file__).resolve().parent.parent
        tool_script_path = ROOT_DIR / "src" / "tools" / processor_script
        report_output_dir = ROOT_DIR / "uploads" / "reports"
        report_output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(tool_script_path), "--command=process", "--audio-file", audio_file_path, "--model", model, "--output-dir", str(report_output_dir), "--video-title", video_title, "--tasks", tasks, "--output-format", output_format]
        env = os.environ.copy()
        if api_key:
            env["GOOGLE_API_KEY"] = api_key
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=1800, check=True, env=env)
        result = json.loads(process.stdout)
        print(f"SUCCESS: [Task ID: {task_id}] Gemini 分析成功。結果: {result}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"ERROR: [Task ID: {task_id}] Gemini 分析腳本執行失敗: {e.stderr}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"CRITICAL: [Task ID: {task_id}] 處理 Gemini 分析時發生未預期錯誤: {e}\n{traceback.format_exc()}", file=sys.stderr)
        raise
