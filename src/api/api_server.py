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
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Optional, Dict, List
from contextlib import asynccontextmanager
from urllib.parse import unquote
import psutil

from db.client import get_client

os.environ['TZ'] = 'Asia/Taipei'
if sys.platform != 'win32':
    time.tzset()

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])
log = logging.getLogger('api_server')

def setup_database_logging():
    try:
        from db.log_handler import DatabaseLogHandler
        root_logger = logging.getLogger()
        if not any(isinstance(h, DatabaseLogHandler) for h in root_logger.handlers):
            root_logger.addHandler(DatabaseLogHandler(source='api_server'))
    except Exception as e:
        log.error(f"整合資料庫日誌時發生錯誤: {e}", exc_info=True)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    async def broadcast_json(self, data: dict):
        for connection in self.active_connections:
            await connection.send_json(data)

manager = ConnectionManager()
db_client = get_client()

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_database_logging()
    yield

app = FastAPI(title="鳳凰音訊轉錄儀 API (v3 - 重構)", version="3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

UPLOADS_DIR = ROOT_DIR / "uploads"
VUE_APP_DIST_DIR = ROOT_DIR / "vue-app" / "dist"
UPLOADS_DIR.mkdir(exist_ok=True)
if VUE_APP_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=VUE_APP_DIST_DIR / "assets"), name="vue-assets")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend(request: Request):
    vue_index_path = VUE_APP_DIST_DIR / "index.html"
    if not vue_index_path.is_file():
        return HTMLResponse(content="<h1>500: Frontend not built</h1>", status_code=500)
    return HTMLResponse(content=vue_index_path.read_text(encoding="utf-8"))

def check_model_exists(model_size: str) -> bool:
    is_mock = os.environ.get("API_MODE", "real") == "mock"
    tool_script_path = ROOT_DIR / "src" / "tools" / ("mock_transcriber.py" if is_mock else "transcriber.py")
    check_command = [sys.executable, str(tool_script_path), "--command=check", f"--model_size={model_size}"]
    try:
        result = subprocess.run(check_command, capture_output=True, text=True, check=True)
        return result.stdout.strip().lower() == "exists"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

@app.post("/api/transcribe", status_code=202)
async def create_transcription_task(file: UploadFile = File(...), model_size: str = Form("tiny"), language: Optional[str] = Form(None), beam_size: int = Form(5)):
    is_mock = os.environ.get("API_MODE", "real") == "mock"
    model_is_present = True if is_mock else check_model_exists(model_size)

    transcribe_task_id = str(uuid.uuid4())
    saved_file_path = UPLOADS_DIR / f"{transcribe_task_id}{Path(file.filename).suffix or '.tmp'}"
    with open(saved_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    transcription_payload = {
        "input_file": str(saved_file_path),
        "original_filename": file.filename,
        "model_size": model_size,
        "language": language,
        "beam_size": beam_size
    }

    if model_is_present:
        db_client.add_task(transcribe_task_id, json.dumps(transcription_payload), task_type='transcribe')
        return {"task_id": transcribe_task_id, "type": "transcribe"}
    else:
        download_task_id = str(uuid.uuid4())
        db_client.add_task(download_task_id, json.dumps({"model_size": model_size}), task_type='download')
        db_client.add_task(transcribe_task_id, json.dumps(transcription_payload), task_type='transcribe', depends_on=download_task_id)
        return JSONResponse(content={"tasks": [{"task_id": download_task_id, "type": "download"}, {"task_id": transcribe_task_id, "type": "transcribe"}]})

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/internal/notify_task_update", status_code=200)
async def notify_task_update(payload: Dict):
    await manager.broadcast_json({"type": "TRANSCRIPTION_STATUS", "payload": payload})
    return {"status": "notification_sent"}

@app.get("/api/health")
async def health_check():
    return JSONResponse(content={"status": "ok"})

# Other endpoints from original file are omitted for brevity, assuming they are not part of the core fix.

if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser(description="API Server")
    parser.add_argument("--port", type=int, default=8001)
    args, _ = parser.parse_known_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port, access_log=True)
