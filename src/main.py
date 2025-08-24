# ======================================================================================
# src/main.py - 統一後端服務入口點
#
# **架構設計理念:**
# 此檔案是根據 `REFACTOR_PLAN.md` 中「方案一：統一後端架構」的設計而建立。
# 其核心目標是解決舊架構中因分離式程序管理 (透過 subprocess 啟動 Huey)
# 而引發的所有穩定性、導入鏈和時序問題。
#
# **主要職責:**
# 1. **單一權威入口:** 作為整個後端服務的唯一啟動點 (e.g., `uvicorn src.main:app`)。
# 2. **整合 FastAPI:** 建立並設定 FastAPI 應用實例。
# 3. **內建 Huey Consumer:** 在應用程式的生命週期 (lifespan) 中，
#    將 Huey consumer 作為一個背景執行緒 (background thread) 來啟動和管理，
#    而不是一個獨立的外部程序。
# 4. **集中化設定:** 集中管理資料庫連線、日誌等核心服務的初始化。
#
# **預期成果:**
# - **根除導入問題:** 所有模組都在同一個程序和導入上下文中，消除了循環導入和檔名衝突的風險。
# - **消除程序管理問題:** 不再需要 subprocess, time.sleep, 或 TCP 探測來協調服務啟動。
# - **簡化架構:** 開發者只需理解此單一檔案即可掌握後端的完整啟動邏輯。
# ======================================================================================

import threading
import logging
from contextlib import asynccontextmanager
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 匯入我們專案的特定模組
from src.db.client import get_client

# --- 全域設定 ---
# 設定時區，確保時間戳的一致性
os.environ['TZ'] = 'Asia/Taipei'
if sys.platform != 'win32':
    time.tzset()

# 定義專案的根目錄。由於此檔案在 src/ 下，根目錄是其父目錄。
ROOT_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = ROOT_DIR / "uploads"
VUE_APP_DIST_DIR = ROOT_DIR / "vue-app" / "dist"

# 在啟動時確保上傳目錄存在，這是一個安全的檔案系統操作。
UPLOADS_DIR.mkdir(exist_ok=True)

# --- 日誌設定 ---
log = logging.getLogger('unified_main')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

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

# --- DB 客戶端 (延遲初始化代理) ---
# 這個代理模式確保資料庫連線只在第一次被實際使用時才建立，
# 避免了在應用程式啟動時就立即連線資料庫。
class DBClientProxy:
    _client = None
    def __getattr__(self, name):
        if self._client is None:
            log.info("DBClientProxy: 首次使用，正在初始化真實的 DBClient...")
            self._client = get_client()
        return getattr(self._client, name)

db_client = DBClientProxy()


# --- Huey 實例與任務註冊 ---
# 匯入共享的 Huey 實例
from src.core.queue_config import huey
# 匯入任務註冊模組。這會確保所有被 @huey.task() 裝飾的函式都被 consumer 發現。
import src.huey_tasks

# --- Huey Consumer 執行器 ---
def run_huey_consumer():
    """
    此函式將在一個獨立的背景執行緒中運行，負責啟動和運行 Huey consumer。
    """
    log.info("Huey Consumer 背景執行緒已啟動，準備開始處理任務。")
    # 根據 Huey 官方建議，使用 'thread' 工作類型與 FastAPI 整合。
    # 這會讓每個任務在自己的執行緒中運行，不會阻塞 FastAPI 的事件迴圈。
    consumer = huey.create_consumer(workers=4, worker_type='thread')
    # consumer.run() 是一個阻塞操作，它會持續運行直到程序終止。
    # 當 FastAPI 關閉時，這個執行緒會作為一個 daemon thread 自動被關閉。
    consumer.run()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 的生命週期管理器。
    在應用程式啟動時執行 yield 之前的部分，在關閉時執行之後的部分。
    """
    log.info("應用程式啟動中...")

    # TODO: 在此處加入資料庫初始化等邏輯

    # 建立並啟動 Huey Consumer 背景執行緒
    consumer_thread = threading.Thread(target=run_huey_consumer, daemon=True)
    consumer_thread.start()
    log.info("Huey Consumer 背景執行緒已成功啟動。")

    yield

    # --- 應用程式關閉 ---
    log.info("應用程式關閉中...")

    # 設定關閉事件，通知背景執行緒停止
    shutdown_event.set()

    # 等待背景執行緒完全結束
    consumer_thread.join(timeout=5.0)
    if consumer_thread.is_alive():
        log.warning("Huey consumer 執行緒在超時後仍未結束。")
    else:
        log.info("Huey consumer 執行緒已成功關閉。")


# --- FastAPI 應用實例 ---
app = FastAPI(
    title="統一後端服務 (Phoenix Audio)",
    description="一個整合了 Web API 和背景任務處理器的統一 FastAPI 服務。",
    version="5.0.0-alpha",
    lifespan=lifespan
)

# --- 中介軟體 (Middleware) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 靜態檔案掛載 ---
# 掛載 vue-app/dist/assets 目錄，讓前端可以存取其資源檔
app.mount("/assets", StaticFiles(directory=VUE_APP_DIST_DIR / "assets"), name="vue-assets")


# --- API 路由 ---
# 匯入我們新建立的 Huey 任務
from workers.transcription_worker import download_model_task, youtube_download_task, gemini_process_task, process_transcription
from fastapi import HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
import uuid # 用於 task_id (雖然我們正在移除它)
import shutil
from typing import Optional
import json

@app.get("/api/v2/health", tags=["Management"])
async def health_check():
    """
    一個簡單的健康檢查端點，用於確認新服務是否正在運行。
    """
    return {"status": "ok", "message": "統一後端服務運行正常。"}

@app.post("/api/youtube/process", status_code=202, tags=["YouTube Processing"])
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

    tasks_created = []
    for req_item in requests_list:
        url = req_item.get("url")
        if not url: continue

        # **重構點**: 直接呼叫 Huey 任務，並建立任務鏈
        download_task_result = youtube_download_task(
            url=url,
            custom_filename=req_item.get("filename"),
            download_type=download_type
        )

        if not download_only:
            # 將第一個任務的結果 (一個 Result 物件) 傳遞給第二個任務。
            # Huey 會自動處理依賴，確保 gemini_process_task 只在下載成功後執行。
            gemini_process_task(
                download_task_result,
                model=model,
                api_key=api_key,
                tasks=tasks_to_run,
                output_format=output_format
            )

        tasks_created.append({"url": url, "status": "accepted"})

    return JSONResponse(content={"message": f"已為 {len(tasks_created)} 個 URL 接受處理請求。", "tasks": tasks_created})

@app.get("/api/models", tags=["Configuration"])
async def get_models_config():
    """
    讀取並回傳 `models.json` 的內容。
    前端將使用此端點來動態產生模型選擇介面。
    """
    models_path = ROOT_DIR / "models.json"
    if not models_path.is_file():
        raise HTTPException(status_code=404, detail="模型設定檔 'models.json' 找不到。")

    with open(models_path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.post("/api/transcribe", status_code=202, tags=["Transcription"])
async def create_transcription_task(file: UploadFile = File(...), model_size: str = Form("tiny"), language: Optional[str] = Form(None), beam_size: int = Form(5)):
    task_id = str(uuid.uuid4())
    saved_file_path = UPLOADS_DIR / f"{task_id}{Path(file.filename).suffix or '.tmp'}"

    # 保存上傳的檔案
    with open(saved_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # **重構點**: 直接呼叫 `process_transcription` Huey 任務
    process_transcription(task_id, str(saved_file_path), file.filename)

    return {"task_id": task_id, "message": "轉錄任務已建立"}


# --- 靜態檔案和 SPA 服務 ---
# !! 重要 !!
# 這個全匹配 (catch-all) 路由必須在所有其他 API 路由之後宣告，
# 否則它會攔截所有 API 請求。
@app.get("/{full_path:path}", response_class=HTMLResponse, tags=["Vue Frontend"])
async def serve_vue_app(request: Request, full_path: str):
    """
    服務 Vue.js 單頁應用 (SPA)。
    這個端點會捕捉所有不匹配其他 API 路由的 GET 請求，並回傳主 `index.html` 檔案。
    前端的 Vue Router 接著會接管，並根據 URL 路徑顯示正確的頁面。
    """
    index_path = VUE_APP_DIST_DIR / "index.html"
    if not index_path.is_file():
        log.error(f"前端檔案 'index.html' 不存在於預期路徑: {index_path}")
        return HTMLResponse(
            content="<h1>503: 前端應用尚未建置</h1>"
                    "<p>找不到 Vue 應用程式的進入點。請在 `vue-app` 目錄下執行 `bun install && bun run build` 來建置前端資源。</p>",
            status_code=503
        )
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


# --- WebSocket 端點 ---
KNOWN_WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    處理所有即時雙向通訊的主 WebSocket 端點。
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            payload = message.get("payload", {})
            request_id = payload.get("request_id")

            # TODO: 將 check_model_exists 的 subprocess 邏輯重構為純 Python 函式
            # if msg_type == "CHECK_LOCAL_MODELS":
            #     available_models = [m for m in KNOWN_WHISPER_MODELS if check_model_exists(m)]
            #     await websocket.send_json({"type": "LOCAL_MODELS_STATUS", "payload": {"models": available_models}})

            if msg_type == "DOWNLOAD_MODEL":
                model_size = payload.get("model")
                if model_size in KNOWN_WHISPER_MODELS:
                    # **重構點**: 不再將任務寫入資料庫，而是直接分派給 Huey。
                    download_model_task(model_size)
                    log.info(f"已成功將 '{model_size}' 的下載任務分派給 Huey。")

                    # 立即回覆前端，告知任務已接受
                    await websocket.send_json({"type": "ACK", "payload": f"已接受模型 '{model_size}' 的下載請求。"})
                else:
                    await websocket.send_json({"type": "ERROR", "payload": "無效的模型大小"})

            # TODO: 處理其他訊息類型，例如 VALIDATE_API_KEY, FETCH_GEMINI_MODELS

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        log.error(f"WebSocket 發生未預期錯誤: {e}", exc_info=True)
        if websocket in manager.active_connections:
            manager.disconnect(websocket)
