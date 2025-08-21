# api_server.py
import uuid
import shutil
import logging
import argparse
import json
import sys
import os
import time
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict, List
import redis
from contextlib import asynccontextmanager

# --- JULES 於 2025-08-21 的修改：設定應用程式全域時區 ---
os.environ['TZ'] = 'Asia/Taipei'
if sys.platform != 'win32':
    time.tzset()

# --- 路徑設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
UPLOADS_DIR = ROOT_DIR / "uploads"
VUE_APP_DIST_DIR = ROOT_DIR / "vue-app" / "dist"

# --- Redis 設定 ---
REDIS_SOCKET_PATH = os.getenv('REDIS_SOCKET_PATH', '/tmp/redis.sock')
TASK_QUEUE_KEY = "task_queue"

# --- 主日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
log = logging.getLogger('api_server')

# --- 全域資源 ---
redis_client: redis.Redis = None

# --- WebSocket 連線管理器 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(f"新用戶端連線。目前共 {len(self.active_connections)} 個連線。")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        log.info(f"一個用戶端離線。目前共 {len(self.active_connections)} 個連線。")

    async def broadcast_json(self, data: dict):
        for connection in self.active_connections:
            await connection.send_json(data)

manager = ConnectionManager()

# --- FastAPI Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    log.info("🚀 啟動 API 伺服器...")
    UPLOADS_DIR.mkdir(exist_ok=True)

    # 初始化 Redis 連線
    try:
        redis_client = redis.Redis(unix_socket_path=REDIS_SOCKET_PATH, decode_responses=True)
        redis_client.ping()
        log.info(f"✅ 成功透過 Unix Socket 連接至 Redis ({REDIS_SOCKET_PATH})。")
    except redis.exceptions.ConnectionError as e:
        log.critical(f"❌ 無法連接至 Redis: {e}")
        # 在真實部署中，我們可能希望重試而不是直接退出
        redis_client = None # 設置為 None 以便後續的健康檢查可以偵測到

    yield

    # 應用程式關閉時執行的程式碼
    log.info("👋 關閉 API 伺服器。")

# --- FastAPI 應用實例 ---
app = FastAPI(title="鳳凰音訊轉錄儀 API (v4 - Redis 架構)", version="4.0", lifespan=lifespan)

# --- 中介軟體 (Middleware) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 靜態檔案掛載 ---
app.mount("/assets", StaticFiles(directory=VUE_APP_DIST_DIR / "assets"), name="vue-assets")

# --- API 端點 ---

def enqueue_task(task_type: str, payload: dict) -> str:
    """
    將一個新任務加入 Redis 佇列，並設定其初始狀態。
    返回任務 ID。
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis 服務不可用。")

    task_id = str(uuid.uuid4())
    task_data = {
        "id": task_id,
        "type": task_type,
        "status": "pending",
        "created_at": time.time(),
        "payload": payload
    }

    # 將任務的完整資料存入一個 hash 中，以便後續查詢
    redis_client.hset(f"task:{task_id}", mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in task_data.items()})

    # 將任務的主要訊息推入待處理佇列，供調度器監聽
    # 我們只推入 ID 和類型，調度器再根據 ID 回頭查詢完整資料
    queue_message = {"id": task_id, "type": task_type}
    redis_client.lpush(TASK_QUEUE_KEY, json.dumps(queue_message))

    log.info(f"✅ 任務已入隊: ID={task_id}, 類型={task_type}")
    return task_id

@app.post("/api/transcribe", status_code=202)
async def create_transcription_task(
    file: UploadFile = File(...),
    model_size: str = Form("tiny"),
    language: str = Form("en")
):
    """
    接收上傳的音訊檔案，並建立一個「轉錄」任務。
    """
    saved_file_path = UPLOADS_DIR / f"{str(uuid.uuid4())}_{file.filename}"
    try:
        with open(saved_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        log.info(f"檔案已儲存至: {saved_file_path}")
    except Exception as e:
        log.error(f"❌ 儲存檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"無法儲存上傳的檔案: {e}")
    finally:
        await file.close()

    task_payload = {
        "audio_path": str(saved_file_path),
        "original_filename": file.filename,
        "model_size": model_size,
        "language": language
    }

    task_id = enqueue_task("transcribe", task_payload)
    return {"task_id": task_id, "message": "轉錄任務已成功建立。"}

@app.post("/api/youtube/process", status_code=202)
async def process_youtube_urls(request: Request):
    """
    接收 YouTube URL，並根據參數建立對應的任務。
    """
    payload = await request.json()
    requests_list = payload.get("requests", [])

    # 新的彈性參數
    tasks_to_run = payload.get("tasks", "summary,transcript")
    download_only = payload.get("download_only", False)

    if not requests_list:
        raise HTTPException(status_code=400, detail="請求中必須包含 'requests'。")

    created_tasks = []
    for req_item in requests_list:
        url = req_item.get("url")
        if not url or not url.strip():
            continue

        task_payload = {
            "url": url,
            "report_options": tasks_to_run.split(',') if isinstance(tasks_to_run, str) else tasks_to_run,
            "api_key_provided": "api_key" in payload # 只記錄金鑰是否提供，不儲存金鑰本身
        }

        # 根據前端的請求決定要建立哪種類型的任務
        if download_only:
            task_type = "youtube_download"
        elif "transcript" in tasks_to_run and len(tasks_to_run) == 1:
            task_type = "transcribe" # 如果只要求逐字稿，就用 Whisper
        else:
            task_type = "audio_to_report" # 否則，使用 Gemini 進行一步到位的分析

        task_id = enqueue_task(task_type, task_payload)
        created_tasks.append({"url": url, "task_id": task_id})

    return JSONResponse(content={"message": f"已為 {len(created_tasks)} 個 URL 建立處理任務。", "tasks": created_tasks})

@app.get("/api/task_status/{task_id}")
async def get_task_status_endpoint(task_id: str):
    """
    根據任務 ID，從 Redis 查詢任務狀態和結果。
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis 服務不可用。")

    task_data = redis_client.hgetall(f"task:{task_id}")
    if not task_data:
        raise HTTPException(status_code=404, detail="找不到指定的任務 ID。")

    # 將 payload 和 result 欄位從 JSON 字串轉回物件
    if 'payload' in task_data:
        task_data['payload'] = json.loads(task_data['payload'])
    if 'result' in task_data:
        task_data['result'] = json.loads(task_data['result'])

    return JSONResponse(content=task_data)

@app.get("/api/health")
async def health_check():
    """提供一個簡單的健康檢查端點，並檢查 Redis 連線。"""
    if redis_client and redis_client.ping():
        return {"status": "ok", "redis_connection": "ok"}
    else:
        return JSONResponse(status_code=503, content={"status": "error", "redis_connection": "failed"})

# --- WebSocket 端點 (目前僅用於廣播，未來可擴充) ---
@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # 保持連線開啟，但目前不處理來自客戶端的訊息
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        log.info("WebSocket 用戶端已離線。")

# --- 靜態檔案與 SPA 回退路由 ---
@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_vue_app(request: Request, full_path: str):
    """根端點，提供 Vue.js 前端操作介面。"""
    vue_index_path = VUE_APP_DIST_DIR / "index.html"
    if not vue_index_path.is_file():
        log.error(f"找不到 Vue 前端入口檔案: {vue_index_path}")
        return HTMLResponse(content="<h1>500: Frontend Not Built</h1><p>Vue app not found. Please run `bun install && bun run build` in the `vue-app` directory.</p>", status_code=500)
    return HTMLResponse(content=vue_index_path.read_text(encoding="utf-8"), status_code=200)

# --- 主程式啟動 (用於本地開發) ---
if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser(description="新架構 API 伺服器")
    parser.add_argument("--port", type=int, default=8001, help="伺服器監聽的埠號")
    args, _ = parser.parse_known_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
