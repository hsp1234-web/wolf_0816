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
import subprocess
import threading
from contextlib import asynccontextmanager

from .config import settings
import datetime
from .schemas import StagedFileResponse, YouTubeProcessRequest, BatchTasksRequest, Task, WebSocketRequest, TaskStatusUpdateRequest

from src.core.state_manager import state_manager, Task as StateTask
from workers.transcription_worker import process_transcription, download_model_task, youtube_download_task, gemini_process_task

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

# --- FastAPI 應用實例 (已移除 Lifespan 管理) ---
app = FastAPI(
    title="善狼專案 API 閘道器",
    version="1.0.0",
    description="負責接收前端請求、分派任務至背景程序，並透過 WebSocket 回報即時狀態。"
)

# --- 將狀態更新與 WebSocket 廣播連接起來 ---
# 這是修復的核心：每當 state_manager 狀態有變時，
# 就會自動呼叫 broadcast_patch 將變更廣播出去。
state_manager.add_patch_listener(broadcast_patch)

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

@app.post("/api/internal/task_update", include_in_schema=False)
async def task_update(update: TaskStatusUpdateRequest):
    """
    這是一個內部端點，供背景工作者回報任務進度。
    """
    print(f"收到任務更新: ID={update.task_id}, 狀態={update.status}")

    def updater(state: StateTask):
        task_index = -1
        for i, task in enumerate(state.pending_tasks):
            if task.task_id == update.task_id:
                task_index = i
                break

        if task_index == -1:
            print(f"警告：在 pending_tasks 中找不到要更新的任務，ID: {update.task_id}")
            return

        # 直接更新列表中的任務物件
        state.pending_tasks[task_index].status = update.status
        if update.result:
            state.pending_tasks[task_index].result = update.result
        if update.error:
            state.pending_tasks[task_index].error = update.error

        # 如果任務已完成或失敗，將其從 pending_tasks 移至 completed_tasks
        if update.status in ["completed", "failed"]:
            task_to_move = state.pending_tasks.pop(task_index)
            state.completed_tasks.append(task_to_move)

    state_manager.update_state(updater)
    return {"status": "ok"}

@app.post("/api/batch-tasks", tags=["Tasks"])
async def batch_tasks(request: BatchTasksRequest):
    print(f"收到批次任務請求，包含 {len(request.tasks)} 個任務。")
    for task_model in request.tasks:
        if task_model.type == 'transcribe_file':
            payload = task_model.payload
            task_id = payload.get('task_id')
            if not all(k in payload for k in ['task_id', 'file_path', 'original_filename']):
                print(f"警告：忽略無效的轉錄任務 payload: {payload}")
                continue

            # 1. 將任務新增至中央狀態的 pending_tasks 列表
            new_task = StateTask(
                task_id=task_id,
                type='transcribe_file',
                status='pending',
                payload=payload,
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
            )
            state_manager.update_state(lambda state: state.pending_tasks.append(new_task))

            # 2. 建立並執行背景程序
            command = [
                sys.executable, "workers/transcription_worker.py",
                "--task", "process_transcription",
                "--task-id", task_id,
                "--file-path", payload['file_path'],
                "--original-filename", payload['original_filename']
            ]

            print(f"正在執行指令: {' '.join(command)}")
            subprocess.Popen(command)

    return JSONResponse(
        content={"message": f"已成功啟動 {len(request.tasks)} 個背景任務。"},
        status_code=202
    )

# 此端點暫時禁用，因為其複雜的任務鏈邏輯需要更詳細的設計才能從 Huey 遷移。
# 為了完成當前的核心任務，我們暫時將其標記為未實現。
@app.post("/api/youtube/process", tags=["Tasks"], status_code=501)
async def process_youtube_url(request: YouTubeProcessRequest):
    return JSONResponse(
        content={"message": "YouTube 處理功能正在重構中，暫時無法使用。"},
        status_code=501
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

# --- 前端靜態檔案服務 (SPA) ---
# 根據 CH_log.md (2025-08-25T07:40:38+08:00), 修正前端路由問題
# 將前端掛載至 /ui 子路徑，並從根目錄重新導向，以避免路由衝突。

@app.get("/", include_in_schema=False)
async def root_redirect_to_ui():
    """從根目錄重新導向至 /ui"""
    return RedirectResponse(url="/ui")

# 使用 html=True 的標準方式來服務單頁應用 (SPA)
# 這會自動處理所有未匹配的路由，並回傳 index.html
app.mount("/ui", StaticFiles(directory=STATIC_FILES_DIR, html=True), name="ui-static")

# --- 主程式啟動 (用於本地測試) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
