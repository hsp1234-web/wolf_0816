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

import threading
import os
from pathlib import Path
from faster_whisper import WhisperModel

from src.db.client import get_client, DBClient

# --- 全域變數 ---
MODEL_NAMES = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]

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
    """增強的健康檢查端點，回報各個子系統的狀態，並包含詳細日誌。"""
    log.info("[Health Check] 收到健康檢查請求...")
    db_client: DBClient = app.state.db_client
    subsystems = {}

    # 1. 檢查資料庫連線
    log.info("[Health Check] 正在 Ping 資料庫管理器...")
    try:
        response = db_client.ping()
        if response == "pong":
            subsystems["database_connection"] = {"status": "ok", "message": "成功 Ping 到資料庫管理器。"}
            log.info("[Health Check] ✅ 資料庫連線檢查成功。")
        else:
            subsystems["database_connection"] = {"status": "error", "message": f"資料庫管理器回應異常: {response}"}
            log.error(f"[Health Check] ❌ 資料庫連線檢查失敗，回應異常: {response}")
    except Exception as e:
        subsystems["database_connection"] = {"status": "error", "message": f"無法連接到資料庫管理器: {e}"}
        log.error(f"[Health Check] ❌ 資料庫連線檢查失敗: {e}")

    # 總體狀態
    overall_status = "ok" if all(s["status"] == "ok" for s in subsystems.values()) else "error"

    response_payload = {
        "status": overall_status,
        "message": "API 伺服器運行中，各子系統狀態如下。",
        "subsystems": subsystems
    }
    log.info(f"[Health Check] 正在回傳健康檢查結果: {response_payload}")
    return response_payload

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

# NOTE: This is the endpoint the hardware monitor uses. It was lost in a refactor.
@app.post("/api/internal/system_update", include_in_schema=False)
async def system_update(payload: Dict[str, Any]):
    """
    一個供硬體監控等內部服務呼叫的端點，專門用於廣播系統狀態。
    """
    # 直接將收到的整個 payload 作為 WebSocket 訊息廣播出去
    # hardware_monitor_worker 已將其打包成 { "type": "SYSTEM_STATS", "payload": ... } 格式
    await websocket_manager.broadcast_json(payload)
    return {"status": "ok"}


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
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                payload = message.get("payload", {})
                request_id = payload.get("request_id")

                if msg_type == "HEALTH_CHECK_REQUEST":
                    # ... (health check logic remains the same)
                    log.info(f"[WS Health Check] 收到來自客戶端的健康檢查請求 (request_id: {request_id})")
                    subsystems = {}
                    try:
                        db_response = db_client.ping()
                        if db_response == "pong":
                            subsystems["database_connection"] = {"status": "ok"}
                        else:
                            subsystems["database_connection"] = {"status": "error", "message": f"回應異常: {db_response}"}
                    except Exception as e:
                        subsystems["database_connection"] = {"status": "error", "message": str(e)}
                    response_payload = {
                        "type": "HEALTH_CHECK_RESPONSE", "request_id": request_id,
                        "payload": {
                            "success": all(s["status"] == "ok" for s in subsystems.values()),
                            "backend_status": "ok", "backend_message": "所有後端子系統回應正常。",
                            "subsystems": subsystems
                        }
                    }
                    await websocket.send_json(response_payload)
                    log.info(f"[WS Health Check] 已回傳健康檢查結果 (request_id: {request_id})")

                elif msg_type == "CHECK_LOCAL_MODELS":
                    log.info(f"[WS] 正在處理 CHECK_LOCAL_MODELS 請求 (request_id: {request_id})")
                    available_models = []
                    # 手動檢查快取路徑，更穩健
                    cache_path = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface/hub"))
                    for model_name in MODEL_NAMES:
                        model_folder = f"models--Systran--faster-whisper-{model_name}"
                        if (cache_path / model_folder).exists():
                            available_models.append(model_name)

                    response = {"type": "LOCAL_MODELS_STATUS", "payload": {"models": available_models, "success": True}, "request_id": request_id}
                    await websocket.send_json(response)
                    log.info(f"[WS] 模型檢查完成，本地找到 {len(available_models)} 個模型。正在回傳...")

                elif msg_type == "DOWNLOAD_MODEL":
                    model_to_download = payload.get("model")
                    log.info(f"[WS] 收到下載模型請求: {model_to_download}")
                    if model_to_download in MODEL_NAMES:
                        def download_task():
                            log.info(f"背景下載執行緒：正在下載模型 '{model_to_download}'...")
                            try:
                                # 這將會下載模型到快取中
                                WhisperModel(f"Systran/faster-whisper-{model_to_download}", device="cpu", compute_type="int8")
                                log.info(f"背景下載執行緒：模型 '{model_to_download}' 下載完成。")
                                # 下載完成後，通知前端刷新模型列表
                                asyncio.run(websocket_manager.broadcast_json({"type": "REFRESH_LOCAL_MODELS"}))
                            except Exception as e:
                                log.error(f"背景下載執行緒：下載模型 '{model_to_download}' 時發生錯誤: {e}")

                        threading.Thread(target=download_task, daemon=True).start()
                        await websocket.send_json({"type": "INFO", "payload": {"message": f"已開始在背景下載模型 '{model_to_download}'..."}})
                    else:
                        await websocket.send_json({"type": "ERROR", "payload": {"message": f"無效的模型名稱: {model_to_download}"}})


            except json.JSONDecodeError:
                log.warning(f"從客戶端收到無效的 JSON 訊息: {data}")
            except Exception as e:
                log.error(f"處理客戶端 WebSocket 訊息時發生錯誤: {e}", exc_info=True)

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
from starlette.responses import RedirectResponse

# 解決根目錄衝突的關鍵修復
@app.get("/", include_in_schema=False)
async def root_redirect():
    """將根目錄請求重新導向到前端應用的入口。"""
    return RedirectResponse(url="/ui/")

# 從環境變數讀取由 run_services.py 傳入的靜態檔案目錄絕對路徑
STATIC_DIR = os.environ.get("STATIC_DIR")

if STATIC_DIR and Path(STATIC_DIR).exists():
    log.info(f"正在從環境變數指定的目錄提供前端檔案: {STATIC_DIR}")
    # 將前端掛載到 /ui 子路徑
    app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    log.warning("環境變數 STATIC_DIR 未設定或指向的路徑不存在。")
    log.warning("前端介面將無法使用。")
