# services/api_gateway/main.py
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
import asyncio
from contextlib import asynccontextmanager
from pydantic import BaseModel
import uuid
from datetime import datetime
from typing import List, Dict, Any
import logging

# --- 標準日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- 核心模組導入 ---
from src.core.log_manager import initialize_log_database
from src.core.queue_config import huey
from src.core.background_tasks import install_and_launch_workers
from src.core.state_manager import state_manager, Task, AppState

# --- WebSocket 連線管理器 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(f"新用戶端連線: {websocket.client}. 目前連線數: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        log.info(f"用戶端斷線: {websocket.client}. 目前連線數: {len(self.active_connections)}")

    async def send_full_state(self, websocket: WebSocket):
        full_state = state_manager.get_full_state()
        await websocket.send_json({"type": "full_state", "payload": full_state})
        log.info(f"已向 {websocket.client} 發送完整初始狀態。")

    async def broadcast_patch(self, patch: List[Dict]):
        message = {"type": "patch", "payload": patch}
        log.debug(f"正在廣播補丁給 {len(self.active_connections)} 個用戶端: {patch}")
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

import shutil
from pathlib import Path

# --- 全域路徑設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STAGED_FILES_DIR = ROOT_DIR / "staged_files"

# --- FastAPI 生命週期事件 (使用標準日誌) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("--- [API 閘道] 正在啟動 ---")

    # 0. 清理並建立暫存檔案目錄
    if STAGED_FILES_DIR.exists():
        shutil.rmtree(STAGED_FILES_DIR)
        log.info(f"已清理舊的暫存目錄: {STAGED_FILES_DIR}")
    STAGED_FILES_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"已建立暫存檔案目錄: {STAGED_FILES_DIR}")

    # 1. 初始化日誌資料庫
    initialize_log_database()
    log.info("日誌資料庫初始化完成。")

    # 2. 註冊狀態補丁監聽器
    log.info("正在註冊狀態補丁監聽器...")
    state_manager.add_patch_listener(manager.broadcast_patch)

    # 3. 啟動背景工作者
    asyncio.create_task(install_and_launch_workers())
    log.info("工作者啟動任務已觸發。")

    yield

    log.info("--- [API 閘道] 正在關閉 ---")

# --- Huey 任務定義 (簽章) ---
@huey.task()
def process_transcription(task_id: str, file_path: str, original_filename: str):
    pass

@huey.task()
def process_youtube_video(task_id: str, url: str):
    pass

# --- Pydantic 模型 ---
class YouTubeRequest(BaseModel):
    youtube_url: str

class BatchTaskPayload(BaseModel):
    # 定義每個任務的具體內容
    # 為了彈性，我們允許任意的鍵值對
    type: str
    name: str
    payload: Dict[str, Any]

class BatchRequest(BaseModel):
    tasks: List[BatchTaskPayload]

app = FastAPI(title="API 閘道 (整合版)", version="0.4.0", lifespan=lifespan)

# --- WebSocket 端點 ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await manager.send_full_state(websocket)
        while True:
            await websocket.receive_text() # 保持連線
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- API 端點 ---
@app.post("/upload_for_transcription", summary="上傳檔案並觸發非同步轉錄", status_code=202)
async def upload_and_transcribe(file: UploadFile = File(...)):
    task_id = str(uuid.uuid4())
    saved_file_path = f"/tmp/{file.filename}"
    with open(saved_file_path, "wb") as buffer:
        buffer.write(await file.read())

    new_task = Task(
        task_id=task_id,
        type="transcription",
        status="queued",
        payload={"original_filename": file.filename, "file_path": saved_file_path},
        created_at=datetime.utcnow().isoformat()
    )
    state_manager.update_state(lambda state: state.pending_tasks.append(new_task))
    process_transcription(task_id=task_id, file_path=saved_file_path, original_filename=file.filename)
    return {"message": "任務已成功排入佇列。", "task_id": task_id}

@app.post("/stage-file", summary="上傳單一檔案至暫存區", status_code=201)
async def stage_file(file: UploadFile = File(...)):
    # 產生一個唯一的檔案ID，並保留原始副檔名
    file_extension = Path(file.filename).suffix
    file_id = f"{uuid.uuid4()}{file_extension}"
    file_path = STAGED_FILES_DIR / file_id

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        log.info(f"檔案 '{file.filename}' 已成功暫存至 '{file_path}'")
    except Exception as e:
        log.error(f"檔案暫存失敗: {e}")
        raise HTTPException(status_code=500, detail="檔案儲存時發生內部錯誤。")

    return {"file_id": file_id}


@app.post("/api/batch-tasks", summary="提交一批次的任務進行處理", status_code=202)
async def create_batch_tasks(request: BatchRequest):
    new_tasks = []
    for task_payload in request.tasks:
        task_id = str(uuid.uuid4())
        task_type = task_payload.type

        # 根據任務類型建立 Task 物件和 Huey 任務
        if task_type == "transcription":
            file_id = task_payload.payload.get("file_id")
            if not file_id:
                raise HTTPException(status_code=400, detail=f"轉錄任務缺少 file_id: {task_payload.name}")

            file_path = STAGED_FILES_DIR / file_id
            if not file_path.exists():
                raise HTTPException(status_code=404, detail=f"找不到暫存檔案: {file_id}")

            new_task = Task(
                task_id=task_id,
                type=task_type,
                status="queued",
                payload=task_payload.payload, # 包含 model, language 等
                created_at=datetime.utcnow().isoformat()
            )
            process_transcription(task_id=task_id, file_path=str(file_path), original_filename=task_payload.payload.get("original_filename", file_id))

        elif task_type == "youtube":
            url = task_payload.payload.get("url")
            if not url:
                raise HTTPException(status_code=400, detail=f"YouTube 任務缺少 url: {task_payload.name}")

            new_task = Task(
                task_id=task_id,
                type=task_type,
                status="queued",
                payload=task_payload.payload, # 包含 model, tasks 等
                created_at=datetime.utcnow().isoformat()
            )
            process_youtube_video(task_id=task_id, url=url)

        else:
            log.warning(f"收到未知的任務類型: {task_type}")
            continue # 跳過未知類型的任務

        new_tasks.append(new_task)

    # 一次性更新狀態
    if new_tasks:
        state_manager.update_state(lambda state: state.pending_tasks.extend(new_tasks))

    return {"message": f"{len(new_tasks)} 個任務已成功排入佇列。", "task_ids": [t.task_id for t in new_tasks]}


@app.post("/transcribe_youtube", summary="提供 YouTube 網址並觸發非同步下載與轉錄", status_code=202)
async def transcribe_from_youtube(request: YouTubeRequest):
    task_id = str(uuid.uuid4())
    new_task = Task(
        task_id=task_id,
        type="youtube",
        status="queued",
        payload={"youtube_url": request.youtube_url},
        created_at=datetime.utcnow().isoformat()
    )
    state_manager.update_state(lambda state: state.pending_tasks.append(new_task))
    process_youtube_video(task_id=task_id, url=request.youtube_url)
    return {"message": "YouTube 處理任務已成功排入佇列。", "task_id": task_id}

# --- 靜態檔案服務 ---
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = ROOT_DIR / "vue-app" / "dist"

if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

@app.get("/{full_path:path}", response_class=FileResponse, include_in_schema=False)
async def serve_spa(full_path: str):
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return "Frontend not built. Please run `npm run build` in `vue-app` directory.", 404

    requested_path = STATIC_DIR / full_path
    if ".." not in full_path and requested_path.is_file():
        return FileResponse(requested_path)

    return FileResponse(index_path)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
