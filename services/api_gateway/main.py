# api_server.py
import uuid
import shutil
import logging
import json
import subprocess
import sys
import threading
import asyncio
import os
import time
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Optional, Dict, List

# 匯入新的資料庫客戶端
# from db import database # REMOVED: No longer used directly
from src.db.client import get_client

# --- JULES 於 2025-08-09 的修改：設定應用程式全域時區 ---
# 為了確保所有日誌和資料庫時間戳都使用一致的時區，我們在應用程式啟動的
# 最早期階段就將時區環境變數設定為 'Asia/Taipei'。
os.environ['TZ'] = 'Asia/Taipei'
if sys.platform != 'win32':
    time.tzset()
# --- 時區設定結束 ---

# --- 模式設定 ---
# JULES: 改為透過環境變數來決定模擬模式，以便與 Circus 整合
# 預設為非模擬模式 (真實模式)
IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"

# --- 路徑設定 ---
# 以此檔案為基準，定義專案根目錄
# 因為此檔案現在位於 services/api_gateway/ 中，所以根目錄是其上上層目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# --- 主日誌設定 ---
# 主日誌器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()] # 輸出到控制台
)
log = logging.getLogger('api_gateway')

def setup_database_logging():
    """設定資料庫日誌處理器。"""
    try:
        from src.db.log_handler import DatabaseLogHandler
        root_logger = logging.getLogger()
        # 檢查是否已經有同類型的 handler，避免重複加入
        if not any(isinstance(h, DatabaseLogHandler) for h in root_logger.handlers):
            # JULES'S FIX: 更新日誌來源以匹配當前服務
            root_logger.addHandler(DatabaseLogHandler(source='api_gateway'))
            log.info("資料庫日誌處理器設定完成 (source: api_gateway)。")
    except Exception as e:
        log.error(f"整合資料庫日誌時發生錯誤: {e}", exc_info=True)


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

from contextlib import asynccontextmanager

# --- DB 客戶端 (延遲初始化代理) ---
class DBClientProxy:
    _client = None
    def __getattr__(self, name):
        if self._client is None:
            log.info("DBClientProxy: 首次使用，正在初始化真實的 DBClient...")
            # JULES'S FIX: 確保 get_client 是從 src.db.client 匯入
            self._client = get_client()
        return getattr(self._client, name)

db_client = DBClientProxy()


# --- FastAPI Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_database_logging()
    log.info("資料庫日誌處理器已透過 lifespan 事件設定。")
    yield

# --- FastAPI 應用實例 ---
app = FastAPI(title="鳳凰音訊轉錄儀 API (v4 - 統一網關)", version="4.0", lifespan=lifespan)

# --- 中介軟體 (Middleware) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 路徑設定 ---
UPLOADS_DIR = ROOT_DIR / "uploads"
VUE_APP_DIST_DIR = ROOT_DIR / "vue-app" / "dist"
UPLOADS_DIR.mkdir(exist_ok=True)

app.mount("/assets", StaticFiles(directory=VUE_APP_DIST_DIR / "assets"), name="vue-assets")

from urllib.parse import unquote
from fastapi.responses import FileResponse

# --- 核心實作函式 ---

def check_model_exists(model_size: str) -> bool:
    """檢查指定的 Whisper 模型是否已經被下載到本地快取。"""
    force_mock = os.environ.get("FORCE_MOCK_TRANSCRIBER") == "true"
    # JULES'S FIX: 確保工具路徑正確
    tool_script_path = ROOT_DIR / "src" / "tools" / ("mock_transcriber.py" if IS_MOCK_MODE or force_mock else "transcriber.py")
    check_command = [sys.executable, str(tool_script_path), "--command=check", f"--model_size={model_size}"]
    try:
        result = subprocess.run(check_command, capture_output=True, text=True, check=True)
        return result.stdout.strip().lower() == "exists"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

async def _validate_api_key_impl(api_key: str) -> Dict:
    """驗證 Google API 金鑰的核心實作。"""
    if not api_key: return {"valid": False, "detail": "未提供 API 金鑰。"}
    if IS_MOCK_MODE: return {"valid": True}
    tool_script_path = ROOT_DIR / "src" / "tools" / "gemini_processor.py"
    cmd = [sys.executable, str(tool_script_path), "--command=validate_key"]
    env = os.environ.copy(); env["GOOGLE_API_KEY"] = api_key
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=env, check=False)
    if result.returncode == 0: return {"valid": True}
    error_message = result.stderr.strip()
    detail = "API 金鑰無效。請檢查您的金鑰是否正確。" if "API key not valid" in error_message else "金鑰驗證失敗，可能是網路問題或金鑰權限不足。"
    return {"valid": False, "detail": detail}

async def _get_youtube_models_impl(api_key: str) -> Dict:
    """獲取可用 Gemini 模型列表的核心實作。"""
    if not api_key: return {"success": False, "detail": "請求中未提供 API 金鑰。"}
    try:
        env = os.environ.copy(); env["GOOGLE_API_KEY"] = api_key
        tool_script_path = ROOT_DIR / "src" / "tools" / "gemini_processor.py"
        cmd = [sys.executable, str(tool_script_path), "--command=list_models"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8', env=env)
        return {"success": True, "models": json.loads(result.stdout)}
    except subprocess.CalledProcessError as e:
        detail = f"無法使用提供的 API 金鑰獲取模型列表: {e.stderr.strip()}"
        return {"success": False, "detail": detail}
    except Exception as e:
        return {"success": False, "detail": f"獲取模型列表時發生內部錯誤: {e}"}

# --- WebSocket 端點 ---
KNOWN_WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            payload = message.get("payload", {})
            request_id = payload.get("request_id")

            if msg_type == "CHECK_LOCAL_MODELS":
                available_models = [m for m in KNOWN_WHISPER_MODELS if check_model_exists(m)]
                await websocket.send_json({"type": "LOCAL_MODELS_STATUS", "payload": {"models": available_models}})

            elif msg_type == "DOWNLOAD_MODEL":
                model_size = payload.get("model")
                if model_size in KNOWN_WHISPER_MODELS:
                    task_id = str(uuid.uuid4())
                    db_client.add_task(task_id, json.dumps({"model_size": model_size}), task_type='download_model')
                    await websocket.send_json({"type": "ACK", "payload": f"已為 '{model_size}' 建立下載任務。"})
                else:
                    await websocket.send_json({"type": "ERROR", "payload": "無效的模型大小"})

            elif msg_type == "VALIDATE_API_KEY":
                result = await _validate_api_key_impl(payload.get("api_key"))
                await websocket.send_json({"type": "API_KEY_VALIDATION_RESULT", "request_id": request_id, "payload": result})

            elif msg_type == "FETCH_GEMINI_MODELS":
                result = await _get_youtube_models_impl(payload.get("api_key"))
                await websocket.send_json({"type": "GEMINI_MODELS_RESULT", "request_id": request_id, "payload": result})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        log.error(f"WebSocket 發生未預期錯誤: {e}", exc_info=True)
        if websocket in manager.active_connections:
            manager.disconnect(websocket)

# --- HTTP API 端點 (保留用於相容性或特定目的) ---

@app.post("/api/youtube/process", status_code=202)
async def process_youtube_urls(request: Request):
    payload = await request.json()
    requests_list = payload.get("requests", [])
    model = payload.get("model")
    api_key = payload.get("api_key")
    tasks_to_run = payload.get("tasks", "summary,transcript")
    output_format = payload.get("output_format", "html")
    download_only = payload.get("download_only", False)
    download_type = payload.get("download_type", "audio")

    if not requests_list: raise HTTPException(400, "請求中必須包含 'requests'。")
    if not download_only and not api_key: raise HTTPException(400, "執行 AI 分析時必須提供 'api_key'。")

    tasks = []
    for req_item in requests_list:
        url = req_item.get("url")
        if not url: continue

        task_id = str(uuid.uuid4())
        if download_only:
            task_payload = {"url": url, "output_dir": str(UPLOADS_DIR), "custom_filename": req_item.get("filename"), "download_type": download_type}
            db_client.add_task(task_id, json.dumps(task_payload), task_type='youtube_download_only')
        else:
            process_task_id = str(uuid.uuid4())
            dl_payload = {"url": url, "output_dir": str(UPLOADS_DIR), "custom_filename": req_item.get("filename"), "download_type": download_type}
            proc_payload = {"model": model, "api_key": api_key, "output_dir": "transcripts", "tasks": tasks_to_run, "output_format": output_format}
            db_client.add_task(task_id, json.dumps(dl_payload), task_type='youtube_download')
            db_client.add_task(process_task_id, json.dumps(proc_payload), task_type='gemini_process', depends_on=task_id)

        tasks.append({"url": url, "task_id": task_id})

    return JSONResponse(content={"message": f"已為 {len(tasks)} 個 URL 建立處理任務。", "tasks": tasks})

@app.post("/api/transcribe", status_code=202)
async def create_transcription_task(file: UploadFile = File(...), model_size: str = Form("tiny"), language: Optional[str] = Form(None), beam_size: int = Form(5)):
    task_id = str(uuid.uuid4())
    saved_file_path = UPLOADS_DIR / f"{task_id}{Path(file.filename).suffix or '.tmp'}"
    with open(saved_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    payload = {"input_file": str(saved_file_path), "original_filename": file.filename, "model_size": model_size, "language": language, "beam_size": beam_size}
    db_client.add_task(task_id, json.dumps(payload), task_type='transcribe')
    return {"task_id": task_id, "message": "轉錄任務已建立"}


# --- 靜態檔案和 SPA 服務 ---
@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_vue_app(request: Request, full_path: str):
    index_path = VUE_APP_DIST_DIR / "index.html"
    if not index_path.is_file():
        return HTMLResponse(content="<h1>500: Frontend Not Built</h1><p>Vue app not found. Please run `bun install && bun run build` in the `vue-app` directory.</p>", status_code=500)
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
