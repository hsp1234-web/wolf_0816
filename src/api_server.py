# src/api_server.py
# 這是一個新的、統一的 API 伺服器，它將取代 facade_server 和 api_gateway。
# 它將使用 DBClient 與資料庫管理器通訊。

import logging
import uuid
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from src.db.client import get_client, DBClient

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)


# --- Pydantic 模型定義 ---
# 這些模型定義了 API 的資料傳輸物件 (DTOs)

class TaskBase(BaseModel):
    """任務的基本欄位"""
    type: str = Field("transcribe", description="任務類型")
    payload: Dict[str, Any] = Field({}, description="任務的具體內容")
    depends_on: Optional[str] = Field(None, description="此任務所依賴的另一個任務的 task_id")

class TaskCreate(TaskBase):
    """用於創建新任務的模型"""
    pass

class TaskResponse(TaskBase):
    """用於 API 回應的完整任務模型"""
    task_id: str
    status: str
    progress: int
    result: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # Pydantic v2 a.k.a. orm_mode

# --- WebSocket 連線管理器 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        log.info("WebSocket 連線管理器已初始化。")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(f"新的 WebSocket 連線: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        log.info(f"WebSocket 連線已斷開: {websocket.client}")

    async def broadcast_json(self, data: dict):
        log.info(f"正在廣播訊息給 {len(self.active_connections)} 個客戶端: {data}")
        for connection in self.active_connections:
            await connection.send_json(data)

websocket_manager = ConnectionManager()


# --- Lifespan 管理器 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 應用程式啟動時執行的程式碼
    log.info("🚀 新 API 伺服器啟動...")
    # 初始化 DBClient
    app.state.db_client = get_client()
    # 執行資料庫初始化檢查
    try:
        # 確保資料庫和資料表都存在
        app.state.db_client._send_request("initialize_database")
        log.info("✅ 資料庫初始化檢查完成。")
    except Exception as e:
        log.critical(f"❌ 無法連接或初始化資料庫，伺服器啟動失敗: {e}", exc_info=True)
    yield
    # 應用程式關閉時執行的程式碼
    log.info("🔥 新 API 伺服器關閉...")


# --- FastAPI 應用實例 ---
app = FastAPI(
    title="善狼專案統一 API 伺服器",
    version="17.0.0",
    description="負責處理所有前端請求、管理背景任務，並透過 WebSocket 回報即時狀態。",
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


# --- 輔助函式 ---
def parse_db_task(task_data: dict) -> dict:
    """解析從資料庫獲取的任務字典，將 JSON 字串轉換為字典。"""
    if task_data and isinstance(task_data.get('payload'), str):
        try:
            task_data['payload'] = json.loads(task_data['payload'])
        except json.JSONDecodeError:
            log.warning(f"無法解析 task {task_data.get('task_id')} 的 payload: {task_data['payload']}")
            task_data['payload'] = {"error": "invalid_json"}
    return task_data


# --- API 端點 ---

@app.get("/api/health", tags=["System"])
async def health_check():
    """一個簡單的健康檢查端點。"""
    return {"status": "ok", "message": "統一 API 伺服器運行中。"}

@app.get("/api/tasks", response_model=List[TaskResponse], tags=["Tasks"])
async def get_all_tasks():
    """獲取資料庫中所有任務的列表。"""
    db_client: DBClient = app.state.db_client
    tasks_from_db = db_client.get_all_tasks()
    # Pydantic 會自動處理 datetime 到 ISO 格式字串的轉換
    return [parse_db_task(task) for task in tasks_from_db]

@app.post("/api/tasks", response_model=TaskResponse, status_code=201, tags=["Tasks"])
async def create_task(task: TaskCreate):
    """
    創建一個新任務，並觸發 WebSocket 通知。
    """
    db_client: DBClient = app.state.db_client
    task_id = str(uuid.uuid4())

    # 將 payload 字典轉換為 JSON 字串以便存儲
    payload_str = json.dumps(task.payload)

    # 將任務添加到資料庫
    success = db_client.add_task(
        task_id=task_id,
        payload=payload_str,
        task_type=task.type,
        depends_on=task.depends_on
    )

    if not success:
        raise HTTPException(status_code=500, detail="無法將任務寫入資料庫。")

    # 廣播通知
    await websocket_manager.broadcast_json({"event": "tasks_changed", "task_id": task_id})

    # 獲取並返回剛創建的任務的完整資訊
    created_task_data = db_client.get_task_status(task_id)
    return parse_db_task(created_task_data)


@app.post("/api/internal/notify_update", include_in_schema=False)
async def notify_update(payload: Dict[str, Any]):
    """
    一個供內部服務（如 workers）呼叫的端點，以觸發 WebSocket 廣播。
    """
    log.info(f"收到內部通知請求，準備廣播: {payload}")
    await websocket_manager.broadcast_json(payload)
    return {"status": "ok", "message": "notification broadcasted"}


# --- WebSocket 端點 ---

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """處理主 WebSocket 連線，用於即時狀態更新。"""
    await websocket_manager.connect(websocket)
    db_client: DBClient = app.state.db_client

    try:
        # 1. 當客戶端第一次連線時，發送所有任務的完整列表
        initial_tasks_raw = db_client.get_all_tasks()
        initial_tasks_parsed = [parse_db_task(t) for t in initial_tasks_raw]
        await websocket.send_json({"type": "all_tasks", "payload": [TaskResponse.model_validate(t).model_dump(mode='json') for t in initial_tasks_parsed]})

        # 2. 保持連線，以接收未來的指令或廣播
        while True:
            # 在這個實作中，我們主要依賴伺服器端的廣播，
            # 但保留 receive_text() 可以保持連線並處理客戶端可能發送的訊息（例如 ping）。
            await websocket.receive_text()

    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as e:
        log.error(f"WebSocket 處理過程中發生錯誤: {e}", exc_info=True)
        if websocket in websocket_manager.active_connections:
            websocket_manager.disconnect(websocket)

# --- 前端靜態檔案服務 (必須在所有 API 路由之後掛載) ---
import os
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# 從環境變數讀取由 run_services.py 傳入的靜態檔案目錄絕對路徑
STATIC_DIR = os.environ.get("STATIC_DIR")

if STATIC_DIR and Path(STATIC_DIR).exists():
    log.info(f"正在從環境變數指定的目錄提供前端檔案: {STATIC_DIR}")
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    log.warning("環境變數 STATIC_DIR 未設定或指向的路徑不存在。")
    log.warning("前端介面將無法使用。")
