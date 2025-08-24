import time
import traceback
import os
import sys
import subprocess
import json
from pathlib import Path
from src.core.queue_config import huey
from .logging_worker import add_log
from src.core.state_manager import state_manager, AppState

@huey.task()
def process_transcription(task_id: str, file_path: str, original_filename: str):
    worker_name = "transcription_worker"
    add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 開始處理任務: {original_filename} ---")
    def update_task_in_state(state: AppState, status: str, result: dict = None, error: str = None):
        task_index = -1
        for i, t in enumerate(state.pending_tasks):
            if t.task_id == task_id:
                task_index = i
                break
        if task_index == -1:
            add_log(worker_name, "ERROR", f"[Task ID: {task_id}] 在 pending_tasks 中找不到任務！")
            return
        task = state.pending_tasks[task_index]
        task.status = status
        if error:
            task.result = {"error": error}
            state.completed_tasks.append(state.pending_tasks.pop(task_index))
        elif status == "completed":
            task.result = result
            state.completed_tasks.append(state.pending_tasks.pop(task_index))
    try:
        add_log(worker_name, "DEBUG", f"[Task ID: {task_id}] 更新狀態為 'processing'")
        state_manager.update_state(lambda state: update_task_in_state(state, status="processing"))
        add_log(worker_name, "INFO", f"[Task ID: {task_id}] 正在進行模擬轉錄...")
        time.sleep(10)
        result_text = f"這是 '{original_filename}' 的模擬轉錄結果。"
        add_log(worker_name, "SUCCESS", f"[Task ID: {task_id}] 轉錄完成")
        state_manager.update_state(lambda state: update_task_in_state(state, status="completed", result={"transcription": result_text}))
    except Exception as e:
        error_message = f"處理失敗: {str(e)}"
        add_log(worker_name, "ERROR", f"[Task ID: {task_id}] {error_message}\n{traceback.format_exc()}")
        state_manager.update_state(lambda state: update_task_in_state(state, status="failed", error=error_message))
    finally:
        add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 任務處理流程結束 ---")

@huey.task()
def download_model_task(model_size: str):
    worker_name = "download_model_worker"
    task_id = f"download_{model_size}_{int(time.time())}"
    add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 開始下載模型: {model_size} ---")
    try:
        IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"
        from src.core.state_manager import state_manager
        state_manager.update_state(lambda state: state.set_model_download_status(model_size, "downloading"))
        ROOT_DIR = Path(__file__).resolve().parent
        tool_script_path = ROOT_DIR / "src" / "tools" / ("mock_transcriber.py" if IS_MOCK_MODE else "transcriber.py")
        cmd = [sys.executable, str(tool_script_path), "--command=download", f"--model_size={model_size}"]
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=600)
        if process.returncode == 0:
            add_log(worker_name, "SUCCESS", f"[Task ID: {task_id}] 模型 '{model_size}' 下載成功。")
            state_manager.update_state(lambda state: state.set_model_download_status(model_size, "downloaded"))
        else:
            error_message = f"模型下載腳本執行失敗: {process.stderr}"
            add_log(worker_name, "ERROR", f"[Task ID: {task_id}] {error_message}")
            state_manager.update_state(lambda state: state.set_model_download_status(model_size, "failed", error_message))
    except Exception as e:
        error_message = f"下載模型時發生未預期錯誤: {str(e)}"
        add_log(worker_name, "CRITICAL", f"[Task ID: {task_id}] {error_message}\n{traceback.format_exc()}")
        state_manager.update_state(lambda state: state.set_model_download_status(model_size, "failed", error_message))

@huey.task()
def youtube_download_task(url: str, custom_filename: str, download_type: str):
    worker_name = "youtube_download_worker"
    task_id = f"yt_dl_{int(time.time())}"
    add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 開始下載 YouTube 影片: {url} ---")
    try:
        IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"
        downloader_script = "mock_youtube_downloader.py" if IS_MOCK_MODE else "youtube_downloader.py"
        ROOT_DIR = Path(__file__).resolve().parent
        tool_script_path = ROOT_DIR / "src" / "tools" / downloader_script
        cmd = [sys.executable, str(tool_script_path), "--url", url, "--output-dir", str(ROOT_DIR / "uploads")]
        if custom_filename:
            cmd.extend(["--custom-filename", custom_filename])
        if download_type:
            cmd.extend(["--download-type", download_type])
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=1800)
        if process.returncode == 0:
            result = json.loads(process.stdout)
            add_log(worker_name, "SUCCESS", f"[Task ID: {task_id}] YouTube 下載成功。結果: {result}")
            return result
        else:
            error_message = f"YouTube 下載腳本執行失敗: {process.stderr}"
            add_log(worker_name, "ERROR", f"[Task ID: {task_id}] {error_message}")
            raise Exception(error_message)
    except Exception as e:
        error_message = f"下載 YouTube 影片時發生未預期錯誤: {str(e)}"
        add_log(worker_name, "CRITICAL", f"[Task ID: {task_id}] {error_message}\n{traceback.format_exc()}")

@huey.task()
def gemini_process_task(download_result: dict, model: str, api_key: str, tasks: str, output_format: str):
    worker_name = "gemini_process_worker"
    task_id = f"gemini_proc_{int(time.time())}"
    add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 開始處理 Gemini 分析任務 ---")
    try:
        audio_file_path = download_result['output_path']
        video_title = download_result.get('video_title', '無標題影片')
        IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"
        processor_script = "mock_gemini_processor.py" if IS_MOCK_MODE else "gemini_processor.py"
        ROOT_DIR = Path(__file__).resolve().parent
        tool_script_path = ROOT_DIR / "src" / "tools" / processor_script
        report_output_dir = ROOT_DIR / "uploads" / "reports"
        report_output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(tool_script_path), "--command=process", "--audio-file", audio_file_path, "--model", model, "--output-dir", str(report_output_dir), "--video-title", video_title, "--tasks", tasks, "--output-format", output_format]
        env = os.environ.copy()
        if api_key:
            env["GOOGLE_API_KEY"] = api_key
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=1800, env=env)
        if process.returncode == 0:
            result = json.loads(process.stdout)
            add_log(worker_name, "SUCCESS", f"[Task ID: {task_id}] Gemini 分析成功。結果: {result}")
        else:
            error_message = f"Gemini 分析腳本執行失敗: {process.stderr}"
            add_log(worker_name, "ERROR", f"[Task ID: {task_id}] {error_message}")
    except Exception as e:
        error_message = f"處理 Gemini 分析時發生未預期錯誤: {str(e)}"
        add_log(worker_name, "CRITICAL", f"[Task ID: {task_id}] {error_message}\n{traceback.format_exc()}")
