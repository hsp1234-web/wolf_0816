# 檔案: api_server_v2.py
# 說明: 核心後端伺服器，負責協調下載與報告生成的工作流。
import asyncio
import sys
import os
import json
import uuid
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

async def stream_subprocess_output(process: asyncio.subprocess.Process):
    """一個最簡單、最健壯的串流處理器。"""
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        yield line

    while True:
        line = await process.stderr.readline()
        if not line:
            break
        yield b"[STDERR] " + line

@app.post("/api/execute")
async def execute_workflow(request: ReportGenerationRequest):

    async def workflow_generator():
        python_executable = sys.executable
        download_result = None

        # --- 步驟 1: 下載資源 (或使用 Mock) ---
        if request.youtube_url == "USE_MOCK_FILES":
            yield "--- [工作流 1/2] 使用 Mock 檔案進行測試... ---\n".encode('utf-8')
            if request.mode == "subtitle":
                mock_path = os.path.abspath("dummy_subtitle.txt")
                download_result = {"type": "subtitle", "file_path": mock_path}
            else: # audio
                mock_path = os.path.abspath("dummy_audio.m4a")
                download_result = {"type": "audio", "file_path": mock_path}
            yield "--- [工作流 1/2] Mock 檔案準備完成 ---\n".encode('utf-8')
        else:
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

        # --- 步驟 2: 生成報告 ---
        if not download_result:
            yield "--- [工作流中止] 未能獲取下載結果。 ---\n".encode('utf-8')
            return

        input_file_path = download_result["file_path"]
        yield f"--- [工作流 2/2] 已取得輸入檔案: {os.path.basename(input_file_path)} ---\n".encode('utf-8')

        report_script = os.path.join(scripts_dir, "generate_gemini_report.py")
        output_file_path = os.path.join(reports_dir, f"{uuid.uuid4()}.md")
        report_command = [
            python_executable, "-u", report_script,
            "--generate", "--input-file", input_file_path, "--output-file", output_file_path
        ]

        process_report = await asyncio.create_subprocess_exec(
            *report_command,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=project_root, env=os.environ.copy()
        )

        yield "--- [工作流 2/2] 正在串流 Gemini 報告生成過程... ---\n".encode('utf-8')
        async for chunk in stream_subprocess_output(process_report):
            yield chunk

        await process_report.wait()
        if process_report.returncode == 0:
            yield "\n報告已生成並儲存於伺服器。".encode('utf-8')
        else:
            yield f"\n報告生成失敗 (返回碼: {process_report.returncode})。".encode('utf-8')

    return StreamingResponse(workflow_generator(), media_type="text/plain; charset=utf-8")

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
    uvicorn.run("api_server_v2:app", host="0.0.0.0", port=0)
