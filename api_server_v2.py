import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
import os
import sys

# 假設此腳本在專案的根目錄下
project_root = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.join(project_root, "scripts")

app = FastAPI()

class ScriptExecutionRequest(BaseModel):
    """定義 /api/execute 的請求體格式"""
    script: str
    args: list[str] = []

async def stream_subprocess_output(process: asyncio.subprocess.Process):
    """
    非同步地、交錯地串流子程序的 stdout 和 stderr，確保即時性。
    """
    q = asyncio.Queue()

    async def reader(stream):
        """從一個串流中讀取所有行，並放入佇列。"""
        while True:
            line = await stream.readline()
            if not line:
                break
            await q.put(line)
        # 發送一個信號表示此串流已結束
        await q.put(None)

    # 平行啟動 stdout 和 stderr 的讀取器
    stdout_task = asyncio.create_task(reader(process.stdout))
    stderr_task = asyncio.create_task(reader(process.stderr))

    finished_streams = 0
    while finished_streams < 2:
        # 從佇列中獲取下一個輸出行
        line = await q.get()
        if line is None:
            # 如果收到 None，表示一個串流已結束
            finished_streams += 1
        else:
            yield line

    # 等待子程序完全結束
    await process.wait()

@app.post("/api/execute")
async def execute_script(request: ScriptExecutionRequest):
    """
    安全地執行指定腳本並即時串流其輸出。
    """
    # 安全性檢查：確保腳本在預期的 scripts/ 目錄下，防止路徑遍歷攻擊
    script_path = os.path.normpath(os.path.join(scripts_dir, request.script))
    if not script_path.startswith(os.path.abspath(scripts_dir)):
        error_msg = f"錯誤：禁止存取此路徑 '{request.script}'。\n".encode('utf-8')
        return StreamingResponse(iter([error_msg]), media_type="text/plain; charset=utf-8", status_code=403)

    if not os.path.exists(script_path):
        error_msg = f"錯誤：找不到腳本 '{request.script}'。\n".encode('utf-8')
        return StreamingResponse(iter([error_msg]), media_type="text/plain; charset=utf-8", status_code=404)

    # 使用與目前環境相同的 Python 解譯器，確保環境一致性
    python_executable = sys.executable
    command = [python_executable, script_path] + request.args

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_root  # 將工作目錄設定為專案根目錄，以利腳本中的相對路徑
        )
        return StreamingResponse(stream_subprocess_output(process), media_type="text/plain; charset=utf-8")
    except Exception as e:
        error_msg = f"執行腳本時發生內部錯誤: {e}\n".encode('utf-8')
        return StreamingResponse(iter([error_msg]), media_type="text/plain; charset=utf-8", status_code=500)

# 靜態文件服務：這個 catch-all 路由必須放在 API 路由之後
@app.get("/{full_path:path}")
async def serve_static_files(full_path: str):
    """
    提供根目錄下的靜態文件。如果請求路徑為空（即根目錄），則提供 index.html。
    """
    path = full_path if full_path else "index.html"
    file_path = os.path.join(project_root, path)

    # 再次進行安全性檢查
    if not os.path.normpath(file_path).startswith(os.path.abspath(project_root)):
        raise HTTPException(status_code=403, detail="禁止存取")

    if os.path.isfile(file_path):
        return FileResponse(file_path)

    # 對於單頁應用 (SPA)，如果找不到請求的檔案，通常會回退到 index.html
    index_path = os.path.join(project_root, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)

    raise HTTPException(status_code=404, detail="找不到檔案")

# 如果直接執行此檔案，則啟動 uvicorn 伺服器
if __name__ == "__main__":
    import uvicorn
    # Colabpro.py 將會從 uvicorn 的啟動日誌中解析出實際使用的埠號。
    # 設定 port=0 會讓 uvicorn 自動選擇一個可用的埠號。
    uvicorn.run("api_server_v2:app", host="0.0.0.0", port=0)
