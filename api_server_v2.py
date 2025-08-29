# 檔案: api_server_v2.py
# 說明: 核心後端伺服器，負責協調下載與報告生成的工作流。
import asyncio
import sys
import os
import json
import uuid
import re
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

# 專案根目錄設定
project_root = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.join(project_root, "scripts")
reports_dir = os.path.join(project_root, "ai_reports")
youtube_downloads_dir = os.path.join(project_root, "youtube_downloads")
Path(reports_dir).mkdir(exist_ok=True)
Path(youtube_downloads_dir).mkdir(exist_ok=True)

app = FastAPI()

class ReportGenerationRequest(BaseModel):
    """定義 /api/execute 的請求體格式"""
    youtube_url: str
    mode: str
    apiKey: str

class MediaDownloadRequest(BaseModel):
    """定義 /api/download_media 的請求體格式"""
    url: str
    download_type: str = "audio" # 'audio' or 'video'

async def stream_subprocess_output(process: asyncio.subprocess.Process):
    """一個健壯的串流處理器，同時處理 stdout 和 stderr。"""
    while True:
        # 使用 asyncio.wait 來同時監聽 stdout 和 stderr
        tasks = [
            asyncio.create_task(process.stdout.readline()),
            asyncio.create_task(process.stderr.readline())
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()

        for task in done:
            line = task.result()
            if not line:
                continue

            # 判斷來源並加上前綴
            if task.get_name() == tasks[0].get_name(): # stdout
                yield line
            else: # stderr
                yield b"[STDERR] " + line

        if process.returncode is not None and all(p.done() for p in tasks):
            break


@app.post("/api/execute")
async def execute_workflow(request: ReportGenerationRequest):

    async def workflow_generator():
        python_executable = sys.executable
        download_result = None
        report_id = str(uuid.uuid4())
        output_file_path = os.path.join(reports_dir, f"{report_id}.md")

        # --- 工作流 ---
        if request.youtube_url == "USE_MOCK_FILES":
            # --- Mock 工作流 ---
            yield "--- [工作流 Mock] 使用 Mock 檔案進行測試... ---\n".encode('utf-8')
            mock_report_content = "# Mock 報告\n\n這是一個在 E2E 測試期間自動生成的模擬報告。"

            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write(mock_report_content)

            yield f"--- [工作流 Mock] 已生成模擬報告檔案: {report_id}.md ---\n".encode('utf-8')
            await asyncio.sleep(1) # 模擬處理延遲

            final_message = json.dumps({"status": "complete", "report_id": report_id})
            yield f"\n{final_message}\n".encode('utf-8')

        else:
            # --- 真實工作流 ---
            download_result = None
            # 步驟 1: 下載資源
            yield "--- [工作流 1/2] 正在啟動 YouTube 資源下載器... ---\n".encode('utf-8')
            download_script = os.path.join(scripts_dir, "download_youtube.py")
            download_command = [
                python_executable, "-u", download_script,
                "--url", request.youtube_url, "--mode", request.mode
            ]
            process_download = await asyncio.create_subprocess_exec(
                *download_command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=project_root
            )
            stdout_dl, stderr_dl = await process_download.communicate()
            if stderr_dl:
                yield "[下載器 STDERR]\n".encode('utf-8') + stderr_dl
            if process_download.returncode != 0:
                yield "--- [工作流中止] 下載步驟失敗。 ---\n".encode('utf-8')
                return
            try:
                download_result = json.loads(stdout_dl.decode())
                yield "--- [工作流 1/2] 下載成功 ---\n".encode('utf-8')
            except (json.JSONDecodeError, KeyError) as e:
                yield f"--- [工作流中止] 解析下載結果失敗: {e} ---\n".encode('utf-8')
                yield f"收到的原始輸出: {stdout_dl.decode()}\n".encode('utf-8')
                return

            # 步驟 2: 生成報告
            if not download_result:
                yield "--- [工作流中止] 未能獲取下載結果。 ---\n".encode('utf-8')
                return

            input_file_path = download_result["file_path"]
            yield f"--- [工作流 2/2] 已取得輸入檔案: {os.path.basename(input_file_path)} ---\n".encode('utf-8')

            report_script = os.path.join(scripts_dir, "generate_gemini_report.py")
            report_command = [
                python_executable, "-u", report_script,
                "--generate", "--input-file", input_file_path, "--output-file", output_file_path,
                "--api-key", request.apiKey
            ]
            process_report = await asyncio.create_subprocess_exec(
                *report_command,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=project_root
            )

            yield "--- [工作流 2/2] 正在串流 Gemini 報告生成過程... ---\n".encode('utf-8')
            async for chunk in stream_subprocess_output(process_report):
                yield chunk

            await process_report.wait()
            if process_report.returncode == 0:
                final_message = json.dumps({"status": "complete", "report_id": report_id})
                yield f"\n{final_message}\n".encode('utf-8')
            else:
                yield f"\n報告生成失敗 (返回碼: {process_report.returncode})。".encode('utf-8')

    return StreamingResponse(workflow_generator(), media_type="text/plain; charset=utf-8")

@app.post("/api/download_media")
async def download_media(request: MediaDownloadRequest):
    """接收媒體 URL 並觸發下載，然後串流回傳進度。"""
    async def download_generator():
        # 新增：模擬模式
        if request.url == "USE_MOCK_DOWNLOAD":
            yield "--- [媒體下載器 Mock] 正在模擬下載... ---\n".encode('utf-8')
            await asyncio.sleep(2) # 模擬延遲
            yield "\n--- [媒體下載器] 下載成功完成。 ---\n".encode('utf-8')
            return

        python_executable = sys.executable
        download_script = os.path.join(scripts_dir, "download_youtube.py")

        mode = "audio" if request.download_type == "audio" else "video"

        yield f"--- [媒體下載器] 準備下載: {request.url} ({mode} 模式) ---\n".encode('utf-8')

        download_command = [
            python_executable, "-u", download_script,
            "--url", request.url, "--mode", mode,
            "--output-dir", str(youtube_downloads_dir) # 確保路徑是字串
        ]

        process = await asyncio.create_subprocess_exec(
            *download_command,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=project_root
        )

        async for chunk in stream_subprocess_output(process):
            yield chunk

        await process.wait()

        if process.returncode == 0:
            yield "\n--- [媒體下載器] 下載成功完成。 ---\n".encode('utf-8')
        else:
            yield f"\n--- [媒體下載器] 下載失敗 (返回碼: {process.returncode})。 ---\n".encode('utf-8')

    return StreamingResponse(download_generator(), media_type="text/plain; charset=utf-8")


@app.get("/api/get_report")
async def get_report(id: str):
    """根據報告 ID 安全地提供報告檔案。"""
    if not re.match(r'^[a-zA-Z0-9-]+$', id):
        raise HTTPException(status_code=400, detail="無效的報告 ID 格式。")

    report_filename = f"{id}.md"
    report_path = Path(reports_dir) / report_filename

    # 安全性檢查：確保請求的路徑在 `reports_dir` 目錄下
    if not report_path.is_file() or not str(report_path.resolve()).startswith(str(Path(reports_dir).resolve())):
        raise HTTPException(status_code=404, detail="找不到報告。")

    return FileResponse(str(report_path), media_type="text/markdown; charset=utf-8")


# 靜態文件服務
@app.get("/{full_path:path}")
async def serve_static_files(full_path: str):
    path = full_path if full_path else "index.html"
    file_path = os.path.join(project_root, path)
    if not os.path.normpath(file_path).startswith(os.path.abspath(project_root)):
        raise HTTPException(status_code=403, detail="禁止存取")
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    index_path = os.path.join(project_root, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="找不到檔案")

# 伺服器啟動
if __name__ == "__main__":
    import uvicorn
    # 使用 --port 0 來讓作業系統自動選擇一個可用的埠號
    # 這對於測試環境特別有用，可以避免埠號衝突
    uvicorn.run("api_server_v2:app", host="0.0.0.0", port=8000, reload=False)
