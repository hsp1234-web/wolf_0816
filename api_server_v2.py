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
    youtube_url: str
    mode: str
    apiKey: str

class MediaDownloadRequest(BaseModel):
    url: str
    download_type: str = "audio"

async def stream_subprocess_output(process: asyncio.subprocess.Process):
    while True:
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
            if task.get_name() == tasks[0].get_name():
                yield f"data: {line.decode('utf-8')}\n\n"
            else:
                yield f"data: {line.decode('utf-8')}\n\n"
        if process.returncode is not None and all(p.done() for p in tasks):
            break

@app.post("/api/execute")
async def execute_workflow(request: ReportGenerationRequest):
    async def workflow_generator():
        python_executable = sys.executable
        download_result = None
        report_id = str(uuid.uuid4())
        output_file_path = os.path.join(reports_dir, f"{report_id}.md")

        potential_path = Path(request.youtube_url)
        if potential_path.is_file() and str(potential_path.resolve()).startswith(str(youtube_downloads_dir.resolve())):
            yield f"data: {json.dumps({'type': 'status', 'message': '偵測到本地檔案，跳過下載步驟。'})}\n\n"
            download_result = {"type": "audio", "file_path": str(potential_path.resolve())}
        elif request.youtube_url == "USE_MOCK_FILES":
            yield f"data: {json.dumps({'type': 'status', 'message': '使用 Mock 檔案進行測試...'})}\n\n"
            mock_report_content = "# Mock 報告\n\n這是一個在 E2E 測試期間自動生成的模擬報告。"
            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write(mock_report_content)
            yield f"data: {json.dumps({'type': 'status', 'message': f'已生成模擬報告檔案: {report_id}.md'})}\n\n"
            await asyncio.sleep(1)
            final_message = json.dumps({"status": "complete", "report_id": report_id})
            yield f"data: {final_message}\n\n"
            return
        else:
            yield f"data: {json.dumps({'type': 'status', 'message': '正在啟動 YouTube 資源下載器...'})}\n\n"
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
            if process_download.returncode != 0:
                yield f"data: {json.dumps({'type': 'error', 'message': '下載步驟失敗', 'details': stderr_dl.decode()})}\n\n"
                return
            try:
                download_result = json.loads(stdout_dl.decode())
                yield f"data: {json.dumps({'type': 'status', 'message': '下載成功'})}\n\n"
            except (json.JSONDecodeError, KeyError) as e:
                yield f"data: {json.dumps({'type': 'error', 'message': '解析下載結果失敗', 'details': str(e)})}\n\n"
                return

        if not download_result:
            yield f"data: {json.dumps({'type': 'error', 'message': '未能獲取下載結果。'})}\n\n"
            return

        input_file_path = download_result["file_path"]
        yield f"data: {json.dumps({'type': 'status', 'message': f'已取得輸入檔案: {os.path.basename(input_file_path)}'})}\n\n"
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
        yield f"data: {json.dumps({'type': 'status', 'message': '正在串流 Gemini 報告生成過程...'})}\n\n"
        async for chunk in stream_subprocess_output(process_report):
            yield chunk
        await process_report.wait()
        if process_report.returncode == 0:
            final_message = json.dumps({"status": "complete", "report_id": report_id})
            yield f"data: {final_message}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'error', 'message': f'報告生成失敗 (返回碼: {process_report.returncode})'})}\n\n"

    return StreamingResponse(workflow_generator(), media_type="text/event-stream")

@app.post("/api/download_media")
async def download_media(request: MediaDownloadRequest):
    async def download_generator():
        if request.url == "USE_MOCK_DOWNLOAD":
            yield f"data: {json.dumps({'type': 'progress', 'status': 'downloading', 'percent': 50, 'description': '模擬下載中...'})}\n\n"
            await asyncio.sleep(1)
            yield f"data: {json.dumps({'type': 'progress', 'status': 'processing'})}\n\n"
            await asyncio.sleep(1)
            mock_result = {"type": "audio", "file_path": "/app/youtube_downloads/mock.m4a", "video_title": "Mock Download", "original_url": request.url}
            yield f"data: {json.dumps({'type': 'success', 'result': mock_result})}\n\n"
            return

        python_executable = sys.executable
        download_script = os.path.join(scripts_dir, "download_youtube.py")
        download_command = [
            python_executable, "-u", download_script,
            "--url", request.url, "--mode", request.download_type,
            "--output-dir", str(youtube_downloads_dir)
        ]

        process = await asyncio.create_subprocess_exec(
            *download_command,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=project_root
        )

        if process.stderr:
            while True:
                line = await process.stderr.readline()
                if not line: break
                try:
                    progress_data = json.loads(line.decode('utf-8'))
                    yield f"data: {json.dumps(progress_data)}\n\n"
                except json.JSONDecodeError: pass

        stdout_data, _ = await process.communicate()

        if process.returncode == 0:
            try:
                success_result = json.loads(stdout_data.decode('utf-8'))
                yield f"data: {json.dumps({'type': 'success', 'result': success_result})}\n\n"
            except json.JSONDecodeError:
                 yield f"data: {json.dumps({'type': 'error', 'message': '後端無法解析下載腳本的成功訊息。'})}\n\n"
        else:
            try:
                error_result = json.loads(stdout_data.decode('utf-8'))
                yield f"data: {json.dumps(error_result)}\n\n"
            except (json.JSONDecodeError, UnicodeDecodeError):
                 yield f"data: {json.dumps({'type': 'error', 'message': '下載腳本執行失敗，且無法解析其錯誤輸出。'})}\n\n"

    return StreamingResponse(download_generator(), media_type="text/event-stream")

@app.get("/api/get_report")
async def get_report(id: str):
    if not re.match(r'^[a-zA-Z0-9-]+$', id):
        raise HTTPException(status_code=400, detail="無效的報告 ID 格式。")
    report_filename = f"{id}.md"
    report_path = Path(reports_dir) / report_filename
    if not report_path.is_file() or not str(report_path.resolve()).startswith(str(Path(reports_dir).resolve())):
        raise HTTPException(status_code=404, detail="找不到報告。")
    return FileResponse(str(report_path), media_type="text/markdown; charset=utf-8")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server_v2:app", host="0.0.0.0", port=8000, reload=False)
