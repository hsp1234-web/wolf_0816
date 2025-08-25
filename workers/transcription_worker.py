import time
import traceback
import os
import sys
import subprocess
import json
import requests
from pathlib import Path
import argparse

def post_status_update(api_port: int, task_id: str, status: str, result: dict = None, error: str = None):
    """向主 API 伺服器發送任務狀態更新。"""
    api_url = f"http://127.0.0.1:{api_port}/api/internal/task_update"
    try:
        payload = {"task_id": task_id, "status": status, "result": result, "error": error}
        print(f"INFO: [Task ID: {task_id}] 正在向 {api_url} 回報狀態: {status}")
        response = requests.post(api_url, json=payload, timeout=5)
        # 關鍵偵錯：記錄下伺服器的回應，以確認我們是否真的呼叫了正確的端點
        print(f"INFO: [Task ID: {task_id}] 收到回報狀態的回應: "
              f"HTTP Status={response.status_code}, Response Text='{response.text[:200]}...'")
        response.raise_for_status() # 如果狀態碼不是 2xx，則引發錯誤
    except requests.exceptions.RequestException as e:
        print(f"ERROR: 工作者無法回報任務狀態 (ID: {task_id}) 至 {api_url}: {e}", file=sys.stderr)

def process_transcription(api_port: int, task_id: str, file_path: str, original_filename: str):
    print(f"--- [Task ID: {task_id}] 開始處理任務: {original_filename} ---")
    try:
        # 啟動回報 (Check-in)，將狀態更新為 'running'
        post_status_update(api_port, task_id, "running")

        print(f"INFO: [Task ID: {task_id}] 正在進行模擬轉錄...")
        time.sleep(10)
        result_text = f"這是 '{original_filename}' 的模擬轉錄結果。"

        print(f"SUCCESS: [Task ID: {task_id}] 轉錄完成")
        post_status_update(api_port, task_id, "completed", result={"transcription": result_text})
    except Exception as e:
        error_message = f"處理失敗: {str(e)}"
        print(f"ERROR: [Task ID: {task_id}] {error_message}\n{traceback.format_exc()}", file=sys.stderr)
        post_status_update(api_port, task_id, "failed", error=error_message)
    finally:
        print(f"--- [Task ID: {task_id}] 任務處理流程結束 ---")

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

def gemini_process_task(download_result_str: str, model: str, api_key: str, tasks: str, output_format: str):
    task_id = f"gemini_proc_{int(time.time())}"
    print(f"--- [Task ID: {task_id}] 開始處理 Gemini 分析任務 ---")
    try:
        # The download_result is passed as a JSON string from the command line
        download_result = json.loads(download_result_str)
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

if __name__ == "__main__":
    # 「遺言」機制：用一個全域的 try...except 包覆整個 Worker 的生命週期
    # 以捕捉任何未預期的錯誤，例如參數解析失敗或模組導入問題。
    task_id_for_last_will = None
    try:
        parser = argparse.ArgumentParser(description="轉錄工作者執行腳本")
        parser.add_argument("--task", required=True, help="要執行的任務函式名稱")
        parser.add_argument("--task-id", help="任務的唯一識別碼")
        parser.add_argument("--api-port", type=int, required=True, help="API 伺服器的埠號")

        args, unknown = parser.parse_known_args()

        if args.task_id:
            task_id_for_last_will = args.task_id

        kwargs = {'api_port': args.api_port}
        # 移除已解析的 --api-port
        if '--api-port' in unknown:
            port_index = unknown.index('--api-port')
            unknown.pop(port_index)
            if port_index < len(unknown):
                unknown.pop(port_index)

        # 重新組合剩餘的參數
        for i in range(0, len(unknown), 2):
            key = unknown[i].lstrip('-').replace('-', '_')
            value = unknown[i+1]
            kwargs[key] = value

        if 'task_id' not in kwargs and args.task_id:
             kwargs['task_id'] = args.task_id

        if args.task == "process_transcription":
            process_transcription(**kwargs)
        elif args.task == "download_model_task":
            download_model_task(**kwargs)
        elif args.task == "youtube_download_task":
            youtube_download_task(**kwargs)
        elif args.task == "gemini_process_task":
            gemini_process_task(**kwargs)
        else:
            print(f"錯誤：未知的任務 '{args.task}'")
            # 如果可能，回報失敗
            if task_id_for_last_will:
                post_status_update(task_id_for_last_will, "failed", error=f"未知的任務類型: {args.task}")
            sys.exit(1)

    except Exception as e:
        # 這就是「遺言」機制的核心
        error_message = f"Worker 發生了無法恢復的致命錯誤: {str(e)}"
        print(error_message, file=sys.stderr)
        traceback.print_exc()

        # 如果我們在崩潰前成功解析出了 task_id 和 api_port，就盡力回報 FAILED 狀態
        if task_id_for_last_will and 'api_port' in locals() and locals()['api_port']:
            post_status_update(locals()['api_port'], task_id_for_last_will, "failed", error=error_message)

        sys.exit(1)
