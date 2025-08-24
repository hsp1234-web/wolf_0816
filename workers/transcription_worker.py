import time
import traceback
import os
import sys
import subprocess
import json
from pathlib import Path
from src.core.queue_config import huey
from .logging_worker import add_log

# 導入新的狀態管理器和 AppState 模型
from src.core.state_manager import state_manager, AppState

@huey.task()
def process_transcription(task_id: str, file_path: str, original_filename: str):
    """
    這是一個轉錄任務的真正實作。
    它會透過 state_manager 更新 AppState 中的任務狀態。
    """
    worker_name = "transcription_worker"
    add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 開始處理任務: {original_filename} ---")

    # 輔助函式，用於在 AppState 中尋找並更新任務
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
            # 任務失敗，移至 completed_tasks
            state.completed_tasks.append(state.pending_tasks.pop(task_index))
        elif status == "completed":
            task.result = result
            # 任務成功，移至 completed_tasks
            state.completed_tasks.append(state.pending_tasks.pop(task_index))
        # 其他狀態（如 processing）則保留在 pending_tasks 中

    try:
        # 1. 將任務狀態更新為 "processing"
        add_log(worker_name, "DEBUG", f"[Task ID: {task_id}] 更新狀態為 'processing'")
        state_manager.update_state(
            lambda state: update_task_in_state(state, status="processing")
        )

        # 2. 模擬耗時的 AI 處理
        add_log(worker_name, "INFO", f"[Task ID: {task_id}] 正在進行模擬轉錄...")
        time.sleep(10) # 模擬 10 秒的處理時間
        result_text = f"這是 '{original_filename}' 的模擬轉錄結果。"

        # 3. 處理成功，將任務狀態更新為 "completed"
        add_log(worker_name, "SUCCESS", f"[Task ID: {task_id}] 轉錄完成")
        state_manager.update_state(
            lambda state: update_task_in_state(state, status="completed", result={"transcription": result_text})
        )

    except Exception as e:
        error_message = f"處理失敗: {str(e)}"
        add_log(worker_name, "ERROR", f"[Task ID: {task_id}] {error_message}\n{traceback.format_exc()}")

        # 4. 處理失敗，將任務狀態更新為 "failed"
        state_manager.update_state(
            lambda state: update_task_in_state(state, status="failed", error=error_message)
        )
    finally:
        add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 任務處理流程結束 ---")

# 這部分不是必須的，因為我們將透過 huey_consumer.py 來啟動 worker。
# 但保留它可以方便單獨測試這個 worker。
if __name__ == '__main__':
    print("警告：此腳本不應直接執行。")
    print("請執行 `huey_consumer.py` 來啟動工作者。")


@huey.task()
def download_model_task(model_size: str):
    """
    這是一個新的 Huey 任務，負責下載 AI 模型。
    它取代了舊的、基於資料庫輪詢的 `process_download_model_task`。
    """
    worker_name = "download_model_worker"
    task_id = f"download_{model_size}_{int(time.time())}" # 為日誌建立一個唯一的任務 ID

    add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 開始下載模型: {model_size} ---")

    try:
        # 這裡我們重用了舊 worker 中的 subprocess 邏輯。
        # 理想情況下，這部分也應該被重構為純 Python 呼叫，但作為第一步遷移，這是可接受的。
        # TODO: 考慮將 `transcriber.py` 的功能重構為可直接匯入的函式。

        # 模擬模式的檢查也需要保留
        IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"

        # 引用 state_manager 來更新前端狀態
        from src.core.state_manager import state_manager

        # 更新狀態：下載中
        state_manager.update_state(
            lambda state: state.set_model_download_status(model_size, "downloading")
        )

        # 建立並執行下載指令
        ROOT_DIR = Path(__file__).resolve().parent
        tool_script_path = ROOT_DIR / "src" / "tools" / ("mock_transcriber.py" if IS_MOCK_MODE else "transcriber.py")
        cmd = [sys.executable, str(tool_script_path), "--command=download", f"--model_size={model_size}"]

        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=600)

        if process.returncode == 0:
            add_log(worker_name, "SUCCESS", f"[Task ID: {task_id}] 模型 '{model_size}' 下載成功。")
            # 更新狀態：已完成
            state_manager.update_state(
                lambda state: state.set_model_download_status(model_size, "downloaded")
            )
        else:
            error_message = f"模型下載腳本執行失敗: {process.stderr}"
            add_log(worker_name, "ERROR", f"[Task ID: {task_id}] {error_message}")
            # 更新狀態：失敗
            state_manager.update_state(
                lambda state: state.set_model_download_status(model_size, "failed", error_message)
            )

    except Exception as e:
        error_message = f"下載模型時發生未預期錯誤: {str(e)}"
        add_log(worker_name, "CRITICAL", f"[Task ID: {task_id}] {error_message}\n{traceback.format_exc()}")
        # 更新狀態：失敗
        state_manager.update_state(
            lambda state: state.set_model_download_status(model_size, "failed", error_message)
        )

@huey.task()
def youtube_download_task(url: str, custom_filename: str, download_type: str):
    """
    新的 Huey 任務，負責處理 YouTube 下載。
    取代了舊的 `process_youtube_download_task`。
    """
    worker_name = "youtube_download_worker"
    task_id = f"yt_dl_{int(time.time())}"
    add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 開始下載 YouTube 影片: {url} ---")

    try:
        IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"
        downloader_script = "mock_youtube_downloader.py" if IS_MOCK_MODE else "youtube_downloader.py"

        ROOT_DIR = Path(__file__).resolve().parent
        tool_script_path = ROOT_DIR / "src" / "tools" / downloader_script

        cmd = [
            sys.executable, str(tool_script_path),
            "--url", url,
            "--output-dir", str(ROOT_DIR / "uploads")
        ]
        if custom_filename:
            cmd.extend(["--custom-filename", custom_filename])
        if download_type:
            cmd.extend(["--download-type", download_type])

        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=1800)

        if process.returncode == 0:
            result = json.loads(process.stdout)
            add_log(worker_name, "SUCCESS", f"[Task ID: {task_id}] YouTube 下載成功。結果: {result}")
            # TODO: 將下載結果報告回前端，可能需要一個新的 state_manager 函式
            return result
        else:
            error_message = f"YouTube 下載腳本執行失敗: {process.stderr}"
            add_log(worker_name, "ERROR", f"[Task ID: {task_id}] {error_message}")
            # TODO: 將錯誤報告回前端
            # 任務失敗時，可以選擇拋出異常或回傳 None
            raise Exception(error_message)

    except Exception as e:
        error_message = f"下載 YouTube 影片時發生未預期錯誤: {str(e)}"
        add_log(worker_name, "CRITICAL", f"[Task ID: {task_id}] {error_message}\n{traceback.format_exc()}")
        # TODO: 將錯誤報告回前端

@huey.task()
def gemini_process_task(download_result: dict, model: str, api_key: str, tasks: str, output_format: str):
    """
    新的 Huey 任務，負責使用 Gemini 處理已下載的音訊檔案。
    """
    worker_name = "gemini_process_worker"
    task_id = f"gemini_proc_{int(time.time())}"
    add_log(worker_name, "INFO", f"--- [Task ID: {task_id}] 開始處理 Gemini 分析任務 ---")

    try:
        # 從 download_result 中獲取所需資訊
        audio_file_path = download_result['output_path']
        video_title = download_result.get('video_title', '無標題影片')

        IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"
        processor_script = "mock_gemini_processor.py" if IS_MOCK_MODE else "gemini_processor.py"

        ROOT_DIR = Path(__file__).resolve().parent
        tool_script_path = ROOT_DIR / "src" / "tools" / processor_script
        report_output_dir = ROOT_DIR / "uploads" / "reports"
        report_output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, str(tool_script_path),
            "--command=process",
            "--audio-file", audio_file_path,
            "--model", model,
            "--output-dir", str(report_output_dir),
            "--video-title", video_title,
            "--tasks", tasks,
            "--output-format", output_format
        ]

        env = os.environ.copy()
        if api_key:
            env["GOOGLE_API_KEY"] = api_key

        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=1800, env=env)

        if process.returncode == 0:
            result = json.loads(process.stdout)
            add_log(worker_name, "SUCCESS", f"[Task ID: {task_id}] Gemini 分析成功。結果: {result}")
            # TODO: 將結果報告回前端
        else:
            error_message = f"Gemini 分析腳本執行失敗: {process.stderr}"
            add_log(worker_name, "ERROR", f"[Task ID: {task_id}] {error_message}")
            # TODO: 將錯誤報告回前端

    except Exception as e:
        error_message = f"處理 Gemini 分析時發生未預期錯誤: {str(e)}"
        add_log(worker_name, "CRITICAL", f"[Task ID: {task_id}] {error_message}\n{traceback.format_exc()}")
        # TODO: 將錯誤報告回前端
