# 繁體中文註解：
# 這是 API 閘道器的主應用程式檔案。
# 它的職責是作為前端和後端服務之間的主要通訊橋樑。

import shutil
import uuid
from pathlib import Path
import sys
import os
import asyncio
import logging
from typing import List
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import subprocess
import threading
from contextlib import asynccontextmanager

from .config import settings
from datetime import datetime, timezone
from .schemas import (
    StagedFileResponse, YouTubeProcessRequest, BatchTasksRequest, Task,
    WebSocketRequest, TaskStatusUpdateRequest, AppStatusResponse, Features, FeatureStatus
)

from src.core.state_manager import state_manager, Task as StateTask, AppState, WorkerStatus
from workers.transcription_worker import process_transcription, download_model_task, youtube_download_task, gemini_process_task

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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

# --- Lifespan 管理器 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 應用程式啟動時執行的程式碼
    logger.info("應用程式啟動：正在初始化工作者狀態...")
    def initialize_workers(state: AppState):
        # 根據 CH_LOG.md 和前端的期望，我們將初始狀態設為 'READY'
        # 這樣前端就能正確顯示「就緒」狀態
        state.worker_statuses["transcription"] = WorkerStatus(status="READY")
        state.worker_statuses["youtube"] = WorkerStatus(status="READY")

    state_manager.update_state(initialize_workers)
    logger.info("工作者狀態初始化完畢。")
    yield
    # 應用程式關閉時執行的程式碼
    logger.info("應用程式正在關閉...")


# --- FastAPI 應用實例 ---
app = FastAPI(
    title="善狼專案 API 閘道器",
    version="1.0.0",
    description="負責接收前端請求、分派任務至背景程序，並透過 WebSocket 回報即時狀態。",
    lifespan=lifespan
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


@app.get("/api/v1/status", response_model=AppStatusResponse, tags=["System"])
async def get_application_status():
    """
    提供前端關於後端功能可用性的單一事實來源。
    """
    # 根據使用者文件硬式編碼功能狀態
    feature_statuses = Features(
        transcription=FeatureStatus(enabled=True, message="服務正常運作中"),
        youtube_processing=FeatureStatus(enabled=False, message="功能正在重構中，暫時無法使用。"),
        model_management=FeatureStatus(enabled=True, message="支援本地模型管理")
    )

    return AppStatusResponse(
        features=feature_statuses,
        app_version=settings.APP_VERSION,
        timestamp=datetime.now(timezone.utc)
    )

@app.post("/api/internal/task_update", include_in_schema=False)
async def task_update(update: TaskStatusUpdateRequest):
    """
    這是一個內部端點，供背景工作者回報任務進度。
    """
    logger.info(f"收到任務更新: ID={update.task_id}, 狀態={update.status}")

    def updater(state: StateTask):
        task_index = -1
        for i, task in enumerate(state.pending_tasks):
            if task.task_id == update.task_id:
                task_index = i
                break

        if task_index == -1:
            logger.warning(f"在 pending_tasks 中找不到要更新的任務，ID: {update.task_id}")
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

def log_worker_output(stream, task_id, logger_func):
    """在一個執行緒中讀取並記錄 Worker 的輸出。"""
    try:
        for line in iter(stream.readline, b''):
            if not line:
                break
            logger_func(f"[Worker-{task_id}] {line.decode('utf-8').strip()}")
        stream.close()
    except Exception as e:
        logger_func(f"讀取 Worker-{task_id} 輸出時發生錯誤: {e}")

@app.post("/api/batch-tasks", tags=["Tasks"])
async def batch_tasks(fastapi_req: Request, request: BatchTasksRequest):
    logger.info(f"收到批次任務請求，包含 {len(request.tasks)} 個任務。")

    # 這裡存在一個潛在的競爭條件，我們在迴圈外先複製一份任務列表
    tasks_to_process = list(request.tasks)

    # 從請求中獲取 API 伺服器正在監聽的埠號
    api_port = fastapi_req.url.port

    for task_model in tasks_to_process:
        if task_model.type == 'transcription':
            payload = task_model.payload

            # 修正：從 payload 中安全地獲取 file_path
            # 在這裡，我們假設 task_id 和 file_path 是由前端在 /api/stage-file 步驟後加入的
            task_id = payload.get('task_id')
            file_path = payload.get('file_path')
            original_filename = payload.get('original_filename')

            if not all([task_id, file_path, original_filename]):
                logger.error(f"錯誤：忽略無效的轉錄任務 payload，缺少 task_id 或 file_path: {payload}")
                continue

            # 1. 將任務新增至中央狀態
            new_task = StateTask(
                task_id=task_id,
                type='transcription',
                status='pending',
                payload=payload,
                created_at=datetime.now(timezone.utc).isoformat()
            )
            state_manager.update_state(lambda state: state.pending_tasks.append(new_task))

            # 2. 建立 Worker 指令，並傳入 API 埠號
            command = [
                sys.executable, "workers/transcription_worker.py",
                "--task", "process_transcription",
                "--task-id", str(task_id),
                "--file-path", str(file_path),
                "--original-filename", str(original_filename),
                "--api-port", str(api_port)
            ]
            logger.info(f"任務 {task_id}: 準備分派 Worker，指令: {' '.join(command)}")

            # 3. 啟動 Worker 並監聽其輸出
            # 獲取由 run.py 設定的依賴路徑
            deps_path = os.environ.get("DEPS_PATH")
            worker_env = os.environ.copy()
            if deps_path:
                # 這是關鍵修復：將依賴路徑設定為 Worker 的 PYTHONPATH
                worker_env["PYTHONPATH"] = deps_path
                logger.info(f"任務 {task_id}: 已為 Worker 設定 PYTHONPATH: {deps_path}")
            else:
                logger.warning(f"任務 {task_id}: 警告 - 未找到 DEPS_PATH 環境變數，Worker 可能會因缺少依賴而失敗。")

            worker_proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=worker_env
            )

            # 建立並啟動監聽執行緒
            stdout_thread = threading.Thread(target=log_worker_output, args=(worker_proc.stdout, task_id, logger.info))
            stderr_thread = threading.Thread(target=log_worker_output, args=(worker_proc.stderr, task_id, logger.error))
            stdout_thread.start()
            stderr_thread.start()

            logger.info(f"任務 {task_id}: Worker 程序已啟動，監聽執行緒已設定。")

            # 4. 更新任務狀態為 'dispatched'
            def set_dispatched(state: StateTask):
                for task in state.pending_tasks:
                    if task.task_id == task_id:
                        task.status = 'dispatched'
                        break

            state_manager.update_state(set_dispatched)
            logger.info(f"任務 {task_id}: 狀態已更新為 'dispatched'。")

    return JSONResponse(
        content={"message": f"已成功分派 {len(tasks_to_process)} 個背景任務。"},
        status_code=202
    )

# 此端點暫時禁用，因為其複雜的任務鏈邏輯需要更詳細的設計才能從 Huey 遷移。
# 為了完成當前的核心任務，我們暫時將其標記為未實現。
@app.post("/api/youtube/process", tags=["Tasks"], status_code=501)
async def process_youtube_url(request: YouTubeProcessRequest):
    # logger.info(f"收到 YouTube 處理請求: {request.dict()}，但此功能尚未實現任務分派。")
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
            # --- 新增：處理互動式 Ping/Pong 測試 ---
            if req.type == "ECHO_REQUEST":
                await manager.send_personal_json({
                    "type": "ECHO_RESPONSE",
                    "payload": req.payload,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }, websocket)
            elif req.type == "DOWNLOAD_MODEL":
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

@app.get("/debug/ws", include_in_schema=False)
async def get_websocket_debug_page():
    """提供一個獨立的 WebSocket 診斷頁面。"""
    debug_page_path = ROOT_DIR / "src" / "static" / "websocket_debug.html"
    if not debug_page_path.is_file():
        raise HTTPException(status_code=404, detail="診斷頁面不存在。")
    return FileResponse(debug_page_path)


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
