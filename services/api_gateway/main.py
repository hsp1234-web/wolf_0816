# 繁體中文註解：
# 這是 API 閘道器的主應用程式檔案。
# 它的職責是作為前端和後端服務之間的主要通訊橋樑。

import shutil
import uuid
from pathlib import Path
import sys
import asyncio
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .schemas import StagedFileResponse, YouTubeProcessRequest, BatchTasksRequest, Task, WebSocketRequest

# Huey 和任務相關的匯入
# 確保在應用啟動時，所有任務都已被註冊
import src.huey_tasks
from src.core.queue_config import huey
from workers.transcription_worker import youtube_download_task, process_transcription, gemini_process_task, download_model_task
from src.core.state_manager import state_manager

# --- 靜態檔案路徑設定 ---
# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
# Vue App 建置後的輸出目錄
STATIC_FILES_DIR = ROOT_DIR / "vue-app" / "dist"


# --- 連線管理器 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_json(self, data: dict, websocket: WebSocket):
        await websocket.send_json(data)

    async def broadcast_json(self, data: dict):
        for connection in self.active_connections:
            await connection.send_json(data)

manager = ConnectionManager()

# --- 狀態更新監聽器 ---
async def broadcast_patch(patch: List[dict]):
    """一個非同步函式，用於將狀態補丁廣播給所有 WebSocket 客戶端。"""
    if not patch:
        return
    await manager.broadcast_json({
        "type": "patch",
        "payload": patch
    })

# --- 應用程式生命週期管理器 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理應用程式的啟動與關閉事件。"""
    print("API 閘道器啟動中...")
    if not STATIC_FILES_DIR.is_dir():
        print(f"警告：靜態檔案目錄 {STATIC_FILES_DIR} 不存在。前端可能無法載入。")
    state_manager.add_patch_listener(broadcast_patch)
    print("狀態補丁監聽器已註冊。")
    yield
    print("API 閘道器正在關閉...")


# --- FastAPI 應用實例 ---
app = FastAPI(
    title="善狼專案 API 閘道器",
    version="1.0.0",
    description="負責接收前端請求、分派任務至 Huey 佇列，並透過 WebSocket 回報即時狀態。",
    lifespan=lifespan
)

# --- 中介軟體 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API 端點 ---
@app.get("/api/health", tags=["System"])
async def health_check():
    return {"status": "ok", "message": "API Gateway is running."}


@app.get("/api/settings", tags=["System"])
async def get_settings():
    return {
        "api_mode": settings.API_MODE,
        "is_mock_mode": settings.is_mock_mode
    }

@app.post("/api/batch-tasks", tags=["Tasks"])
async def batch_tasks(request: BatchTasksRequest):
    created_tasks_info = []
    for task_model in request.tasks:
        task_type = task_model.type
        payload = task_model.payload
        res = None
        if task_type == 'transcribe_file':
            if not all(k in payload for k in ['task_id', 'file_path', 'original_filename']):
                continue
            task_id = payload.pop('task_id')
            res = process_transcription.delay(task_id=task_id, **payload)
        if res:
            created_tasks_info.append({"submitted_task_id": task_id, "huey_task_id": res.id})
    return JSONResponse(
        content={"message": f"成功提交 {len(created_tasks_info)} 個任務。", "details": created_tasks_info},
        status_code=202
    )

@app.post("/api/youtube/process", tags=["Tasks"])
async def process_youtube_url(request: YouTubeProcessRequest):
    created_tasks = []
    for req_item in request.requests:
        if request.download_only:
            task = youtube_download_task.s(url=req_item.url, custom_filename=req_item.filename, download_type=request.download_type)
            res = task.delay()
            created_tasks.append({"url": req_item.url, "task_id": res.id})
        else:
            if not request.model or not request.api_key:
                raise HTTPException(status_code=400, detail="執行 AI 分析時必須提供 'model' 和 'api_key'。")
            download_task = youtube_download_task.s(url=req_item.url, custom_filename=req_item.filename, download_type='audio')
            process_task = gemini_process_task.s(model=request.model, api_key=request.api_key, tasks=request.tasks_to_run, output_format=request.output_format)
            pipeline = download_task.then(process_task)
            res = pipeline.delay()
            created_tasks.append({"url": req_item.url, "task_id": res.id, "task_type": "youtube_process_chain"})
    return JSONResponse(
        content={"message": f"已成功為 {len(created_tasks)} 個 URL 建立處理任務。", "tasks": created_tasks},
        status_code=202
    )

@app.post("/api/stage-file", response_model=StagedFileResponse, tags=["Tasks"])
async def stage_file(file: UploadFile = File(...)):
    upload_dir = Path(settings.UPLOADS_DIR)
    if not upload_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"上傳目錄 '{upload_dir}' 不存在或不是一個目錄。")
    try:
        file_extension = Path(file.filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = upload_dir / unique_filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return StagedFileResponse(file_path=str(file_path), original_filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"儲存檔案時發生錯誤: {e}")
    finally:
        await file.close()

# --- WebSocket 端點 ---
@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await manager.send_personal_json({"type": "full_state", "payload": state_manager.get_full_state()}, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            try:
                req = WebSocketRequest(**data)
            except Exception:
                print(f"收到無效的 WebSocket 訊息: {data}")
                continue
            if req.type == "DOWNLOAD_MODEL":
                model_size = req.payload.get("model")
                if model_size:
                    print(f"收到下載 '{model_size}' 模型的請求，正在分派任務...")
                    download_model_task.delay(model_size)
            else:
                await manager.send_personal_json({"type": "ECHO", "request_id": req.request_id, "payload": req.dict()}, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("一個客戶端已離線")
    except Exception as e:
        print(f"WebSocket 發生錯誤: {e}")
        manager.disconnect(websocket)

# --- 前端靜態檔案服務 ---
# 為了完全避免路由衝突，我們採取以下策略：
# 1. 在根路徑 ("/") 提供一個重新導向，將使用者指向前端應用的主路徑。
# 2. 將前端應用掛載到一個明確的子路徑 ("/ui") 上。

@app.get("/", include_in_schema=False)
async def root_redirect():
    """將根路徑重新導向至前端應用程式。"""
    return RedirectResponse(url="/ui")

# 關鍵修正：將 SPA 掛載到 "/ui" 子路徑下，並啟用 html=True 以支援前端路由。
# 這必須是應用程式中最後一個掛載的路由。
app.mount("/ui", StaticFiles(directory=STATIC_FILES_DIR, html=True), name="static-ui")

# --- 主程式啟動 (用於本地測試) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
