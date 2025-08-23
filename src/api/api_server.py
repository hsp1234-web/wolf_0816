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
from db.client import get_client

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
# 因為此檔案現在位於 src/api/ 中，所以根目錄是其上上層目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# --- 主日誌設定 ---
# 主日誌器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()] # 輸出到控制台
)
log = logging.getLogger('api_server')

def setup_database_logging():
    """設定資料庫日誌處理器。"""
    try:
        from db.log_handler import DatabaseLogHandler
        root_logger = logging.getLogger()
        # 檢查是否已經有同類型的 handler，避免重複加入
        if not any(isinstance(h, DatabaseLogHandler) for h in root_logger.handlers):
            root_logger.addHandler(DatabaseLogHandler(source='api_server'))
            log.info("資料庫日誌處理器設定完成 (source: api_server)。")
    except Exception as e:
        log.error(f"整合資料庫日誌時發生錯誤: {e}", exc_info=True)


# Frontend action logging is now handled by the centralized database logger.


# --- WebSocket 連線管理器 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(f"新用戶端連線。目前共 {len(self.active_connections)} 個連線。")

        # JULES'S FIX (2025-08-19): 解決前端狀態不同步問題。
        # 當一個新用戶端連線時，立即將所有工作者的當前狀態發送給它。
        # 這確保了即使用戶端錯過了先前的廣播，也能獲得最新的狀態。
        try:
            initial_status_payload = {
                worker: {"status": data["status"], "last_error": data["last_error"]}
                for worker, data in WORKER_STATUS.items()
            }
            initial_message = {
                "type": "ALL_WORKERS_STATUS_UPDATE",
                "payload": initial_status_payload
            }
            # 直接使用 websocket 物件的 send_json 方法，只發送給當前的 websocket
            await websocket.send_json(initial_message)
            log.info(f"已將所有工作者的初始狀態傳送給新連線的用戶端。")
        except Exception as e:
            log.error(f"發送初始工作者狀態時發生錯誤: {e}", exc_info=True)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        log.info(f"一個用戶端離線。目前共 {len(self.active_connections)} 個連線。")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    async def broadcast_json(self, data: dict):
        for connection in self.active_connections:
            await connection.send_json(data)

manager = ConnectionManager()


# --- 工作者狀態管理器 (Worker Status Manager) ---
# 定義已知的工作者及其對應的啟動腳本
# 這將作為我們追蹤所有工作者狀態的中心註冊表
WORKER_SCRIPTS = {
    "youtube": ROOT_DIR / "run_youtube_worker.py",
    "transcription": ROOT_DIR / "run_transcription_worker.py",
    "ai_report": ROOT_DIR / "run_ai_report_worker.py",
    "model_management": ROOT_DIR / "run_model_management_worker.py",
}

# 全域工作者狀態註冊表
# 狀態可以是: NOT_STARTED, INSTALLING, READY, FAILED, RUNNING
WORKER_STATUS = {
    name: {"status": "NOT_STARTED", "process": None, "last_error": None}
    for name in WORKER_SCRIPTS
}

log.info(f"工作者管理器已初始化，將追蹤: {list(WORKER_STATUS.keys())}")
# --- 工作者狀態管理器結束 ---


from contextlib import asynccontextmanager

# --- DB 客戶端 (延遲初始化代理) ---
# 為了避免在應用程式啟動時因等待 DB 管理者而阻塞，
# 我們使用一個代理類別來延遲 DBClient 的實例化，直到它第一次被使用。
class DBClientProxy:
    _client = None
    def __getattr__(self, name):
        if self._client is None:
            log.info("DBClientProxy: 首次使用，正在初始化真實的 DBClient...")
            self._client = get_client()
        return getattr(self._client, name)

db_client = DBClientProxy()


# --- FastAPI Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在應用程式啟動時執行的程式碼
    setup_database_logging()
    log.info("資料庫日誌處理器已透過 lifespan 事件設定。")
    yield
    # 可以在此處加入應用程式關閉時執行的程式碼

# --- FastAPI 應用實例 ---
app = FastAPI(title="鳳凰音訊轉錄儀 API (v3 - 重構)", version="3.0", lifespan=lifespan)

# --- 中介軟體 (Middleware) ---
# JULES: 新增 CORS 中介軟體以允許來自瀏覽器腳本的跨來源請求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允許所有來源
    allow_credentials=True,
    allow_methods=["*"],  # 允許所有方法
    allow_headers=["*"],  # 允許所有標頭
)

# --- 路徑設定 (VUE APP MIGRATION) ---
UPLOADS_DIR = ROOT_DIR / "uploads"
VUE_APP_DIST_DIR = ROOT_DIR / "vue-app" / "dist"

# 確保目錄存在
UPLOADS_DIR.mkdir(exist_ok=True)

# JULES'S FIX (2025-08-18): 掛載 Vue.js 應用程式的靜態資源目錄
# 這解決了瀏覽器無法載入 JS/CSS 模組 (MIME 類型錯誤) 的問題，
# 因為伺服器先前會對 /assets/* 的請求回傳 index.html。
app.mount("/assets", StaticFiles(directory=VUE_APP_DIST_DIR / "assets"), name="vue-assets")


# JULES'S FIX (2025-08-13): 根據計畫，新增此端點來處理複雜檔名
from urllib.parse import unquote
from fastapi.responses import FileResponse


# --- JULES'S NEW FEATURE: App State API Endpoints ---

@app.get("/api/app_state", response_class=JSONResponse)
async def get_app_state_endpoint():
    """
    獲取應用程式的 UI 狀態。
    """
    try:
        # 我們將所有 UI 狀態儲存在一個鍵 'ui_settings' 下
        state_json = db_client.get_app_state(key='ui_settings')
        if state_json:
            # 如果資料庫中有資料，解析並回傳
            return JSONResponse(content=json.loads(state_json))
        # 如果資料庫中沒有，回傳一個空的預設物件
        return JSONResponse(content={})
    except Exception as e:
        log.error(f"獲取 app_state 時 API 發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法獲取應用程式狀態")

@app.post("/api/app_state", status_code=200)
async def set_app_state_endpoint(request: Request):
    """
    儲存應用程式的 UI 狀態。
    """
    try:
        new_state = await request.json()
        # 將收到的 JSON 物件轉換為字串以便儲存
        state_json = json.dumps(new_state)
        db_client.set_app_state(key='ui_settings', value=state_json)
        return {"status": "success", "message": "應用程式狀態已儲存"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="無效的 JSON 格式。")
    except Exception as e:
        log.error(f"儲存 app_state 時 API 發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法儲存應用程式狀態")

@app.get("/media/{file_path:path}")
async def serve_media_files(file_path: str):
    """
    一個新的API端點，專門用來安全地提供媒體檔案。
    它會手動處理URL解碼，以解決複雜檔名的問題。
    """
    try:
        # URL 解碼，將 %20 轉為空格，處理中文等
        decoded_path = unquote(file_path)
        # 建立一個安全的路徑，避免路徑遍歷攻擊
        safe_path = os.path.normpath(os.path.join(UPLOADS_DIR, decoded_path))

        # 再次確認路徑是在 UPLOADS_DIR 下
        if not safe_path.startswith(str(UPLOADS_DIR)):
             raise HTTPException(status_code=403, detail="禁止存取。")

        if os.path.exists(safe_path) and os.path.isfile(safe_path):
            return FileResponse(safe_path)
        else:
            log.warning(f"請求的媒體檔案不存在: {safe_path}")
            return JSONResponse(status_code=404, content={"detail": "File not found"})
    except Exception as e:
        log.error(f"服務媒體檔案時發生錯誤: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": str(e)})


def convert_to_media_url(absolute_path_str: str) -> str:
    """將絕對檔案系統路徑轉換為可公開存取的 /media URL。"""
    try:
        absolute_path = Path(absolute_path_str)
        # Find the path relative to the UPLOADS_DIR
        relative_path = absolute_path.relative_to(UPLOADS_DIR)
        # Join with /media/ and convert backslashes to forward slashes for URL
        return f"/media/{relative_path.as_posix()}"
    except (ValueError, TypeError):
        log.warning(f"無法將路徑 {absolute_path_str} 轉換為媒體 URL。回傳原始路徑。")
        return absolute_path_str


# --- API 端點 ---

def check_model_exists(model_size: str) -> bool:
    """
    檢查指定的 Whisper 模型是否已經被下載到本地快取。
    """
    # JULES'S FIX: 增加一個環境變數來強制使用模擬轉錄器，以支援混合模式測試
    force_mock = os.environ.get("FORCE_MOCK_TRANSCRIBER") == "true"
    tool_script_path = ROOT_DIR / "src" / "tools" / ("mock_transcriber.py" if IS_MOCK_MODE or force_mock else "transcriber.py")
    log.info(f"使用 '{tool_script_path}' 檢查模型 '{model_size}' 是否存在...")

    # 我們透過呼叫一個輕量級的工具腳本來檢查。
    check_command = [sys.executable, str(tool_script_path), "--command=check", f"--model_size={model_size}"]
    try:
        # 在模擬模式下，mock_transcriber.py 會永遠回傳 "exists"
        result = subprocess.run(check_command, capture_output=True, text=True, check=True)
        output = result.stdout.strip().lower()
        log.info(f"模型 '{model_size}' 檢查結果: {output}")
        # 必須完全匹配 "exists"，避免 "not_exists" 被錯誤判斷為 True
        return output == "exists"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.error(f"檢查模型 '{model_size}' 時發生錯誤: {e}")
        return False

KNOWN_WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]


@app.post("/api/transcribe", status_code=202)
async def create_transcription_task(
    file: UploadFile = File(...),
    model_size: str = Form("tiny"),
    language: Optional[str] = Form(None),
    beam_size: int = Form(5)
):
    """
    接收音訊檔案，並建立處理任務。
    如果所需模型不存在，將自動建立一個先導的下載任務。
    """
    # 1. 保存上傳的檔案
    # 我們為轉錄任務預先產生一個 ID，無論是立即執行還是稍後執行
    transcribe_task_id = str(uuid.uuid4())
    file_extension = Path(file.filename).suffix or ".wav"
    saved_file_path = UPLOADS_DIR / f"{transcribe_task_id}{file_extension}"
    try:
        with open(saved_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        log.info(f"檔案已儲存至: {saved_file_path}")
    except Exception as e:
        log.error(f"❌ 儲存檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"無法儲存上傳的檔案: {e}")
    finally:
        await file.close()

    # 2. 準備轉錄任務的 payload，這部分是固定的
    transcription_payload = {
        "input_file": str(saved_file_path),
        "original_filename": file.filename,
        "output_dir": "transcripts",
        "model_size": model_size,
        "language": language,
        "beam_size": beam_size
    }

    # 3. 根據新的手動下載流程，我們不再自動建立下載任務。
    #    我們假設模型已經存在，如果不存在，轉錄工作者會在執行時失敗。
    log.info(f"✅ 建立轉錄任務: {transcribe_task_id} (模型: {model_size})")
    db_client.add_task(transcribe_task_id, json.dumps(transcription_payload), task_type='transcribe')
    return {"task_id": transcribe_task_id, "type": "transcribe", "message": "任務已建立，將透過 WebSocket 觸發執行。"}


@app.get("/api/status/{task_id}")
async def get_task_status_endpoint(task_id: str):
    """
    根據任務 ID，從資料庫查詢任務狀態。
    """
    log.debug(f"🔍 正在查詢任務狀態: {task_id}")
    status_info = db_client.get_task_status(task_id)

    if not status_info:
        log.warning(f"❓ 找不到任務 ID: {task_id}")
        raise HTTPException(status_code=404, detail="找不到指定的任務 ID")

    # DBClient 回傳的已經是 dict，無需轉換
    response_data = status_info

    # 嘗試解析 JSON 結果
    if response_data.get("result"):
        try:
            response_data["result"] = json.loads(response_data["result"])
        except json.JSONDecodeError:
            # 如果不是合法的 JSON，就以原始字串形式回傳
            log.warning(f"任務 {task_id} 的結果不是有效的 JSON 格式。")
            pass

    log.info(f"✅ 回傳任務 {task_id} 的狀態: {response_data['status']}")
    return JSONResponse(content=response_data)


@app.post("/api/log/action", status_code=200)
async def log_action_endpoint(payload: Dict):
    """
    接收前端發送的操作日誌，並透過資料庫日誌處理器記錄。
    """
    action = payload.get("action", "unknown_action")
    # 獲取一個專門的 logger 來標識這些日誌的來源為 'frontend_action'
    # DatabaseLogHandler 會擷取這個日誌，並將其與 logger 名稱一起存入資料庫
    action_logger = logging.getLogger('frontend_action')
    action_logger.info(action)

    log.info(f"📝 已將前端操作記錄到資料庫: {action}") # 同時在主控台也顯示日誌
    return {"status": "logged"}


import psutil

@app.get("/api/application_status")
async def get_application_status():
    """
    獲取核心應用的狀態，例如模型是否已載入。
    """
    # TODO: 這部分將在後續與 worker 狀態同步
    return {
        "model_loaded": False,
        "active_model": None,
        "message": "等待使用者操作"
    }

@app.get("/api/system_stats")
async def get_system_stats():
    """
    獲取並回傳當前的系統資源使用狀態（CPU, RAM, GPU）。
    """
    # CPU
    cpu_usage = psutil.cpu_percent(interval=0.1)

    # RAM
    ram = psutil.virtual_memory()
    ram_usage = ram.percent

    # GPU (透過 nvidia-smi)
    gpu_usage = None
    gpu_name = None
    gpu_detected = False
    try:
        # 執行 nvidia-smi 命令，一次查詢多個屬性
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=gpu_name,utilization.gpu', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, check=True, encoding='utf-8'
        )
        # 解析輸出, e.g., "NVIDIA GeForce RTX 4090, 15"
        output = result.stdout.strip().split(',')
        if len(output) == 2:
            gpu_name = output[0].strip()
            gpu_usage = float(output[1].strip())
            gpu_detected = True
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        # nvidia-smi 不存在或執行失敗
        log.debug(f"無法獲取 GPU 資訊: {e}")
        gpu_usage = None
        gpu_name = None
        gpu_detected = False
    except (ValueError, IndexError) as e:
        # 解析 nvidia-smi 輸出失敗
        log.error(f"解析 nvidia-smi 輸出時出錯: {e}", exc_info=True)
        gpu_usage = None
        gpu_name = None
        gpu_detected = False

    # TODO: 這裡應該要有動態邏輯來決定當前載入的模型
    active_model = "Whisper-large-v3" # 暫時的佔位符

    return {
        "cpu_usage": round(cpu_usage, 1) if cpu_usage is not None else None,
        "ram_usage": round(ram_usage, 1) if ram_usage is not None else None,
        "gpu_usage": round(gpu_usage, 1) if gpu_usage is not None else None,
        "gpu_detected": gpu_detected,
        "gpu_name": gpu_name,
        "active_model": active_model,
    }


@app.get("/api/workers/status", response_class=JSONResponse)
async def get_workers_status():
    """
    獲取所有已知工作者的目前狀態。
    """
    # 為了安全，我們回傳一個不包含 'process' 物件的狀態副本
    status_copy = {
        worker: {
            "status": data["status"],
            "last_error": data["last_error"]
        }
        for worker, data in WORKER_STATUS.items()
    }
    return JSONResponse(content=status_copy)

@app.post("/api/workers/launch/{worker_name}", status_code=200)
async def launch_worker(worker_name: str):
    """
    按需啟動一個指定的工作者。
    [JULES'S REFACTOR]: 此功能現已由系統協調器自動管理。此端點僅為保留。
    """
    if worker_name not in WORKER_SCRIPTS:
        raise HTTPException(status_code=404, detail=f"找不到名為 '{worker_name}' 的工作者。")

    log.info(f"收到對工作者 '{worker_name}' 的啟動請求，但此操作現由協調器自動管理。")
    return {"status": "managed_by_orchestrator", "message": f"工作者 '{worker_name}' 的生命週期由系統自動管理，無需手動啟動。"}


@app.get("/api/tasks")
async def get_all_tasks_endpoint():
    """
    獲取所有任務的列表，用於前端展示。
    """
    tasks = db_client.get_all_tasks()
    # 嘗試解析 payload 和 result 中的 JSON 字串
    for task in tasks:
        try:
            if task.get("payload"):
                task["payload"] = json.loads(task["payload"])
        except (json.JSONDecodeError, TypeError):
            log.warning(f"任務 {task.get('task_id')} 的 payload 不是有效的 JSON。")
            pass # 保持原樣
        try:
            if task.get("result"):
                task["result"] = json.loads(task["result"])
        except (json.JSONDecodeError, TypeError):
            log.warning(f"任務 {task.get('task_id')} 的 result 不是有效的 JSON。")
            pass # 保持原樣
    return JSONResponse(content=tasks)


@app.get("/api/logs")
async def get_system_logs_endpoint(
    levels: List[str] = Query(None, alias="level"),
    sources: List[str] = Query(None, alias="source")
):
    """
    獲取系統日誌，可按等級和來源進行篩選。
    """
    log.info(f"API: 正在查詢系統日誌 (Levels: {levels}, Sources: {sources})")
    try:
        logs = db_client.get_system_logs(levels=levels, sources=sources)
        return JSONResponse(content=logs)
    except Exception as e:
        log.error(f"❌ 查詢系統日誌時 API 出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查詢系統日誌時發生內部錯誤")


@app.get("/api/download/{task_id}")
async def download_transcript(task_id: str):
    """
    根據任務 ID 下載轉錄結果檔案。
    """
    task = db_client.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="找不到指定的任務 ID。")

    if task['status'] != 'completed':
        raise HTTPException(status_code=400, detail="任務尚未完成，無法下載。")

    try:
        # 從 result 欄位解析出檔名
        result_data = json.loads(task['result'])
        # 依序檢查可能的路徑鍵名，以支援所有任務類型
        output_filename = (
            result_data.get("transcript_path") or
            result_data.get("output_path") or
            result_data.get("html_report_path") or
            result_data.get("pdf_report_path")
        )

        if not output_filename:
            raise HTTPException(status_code=500, detail="任務結果中未包含有效的檔案路徑。")

        # JULES'S FIX 2025-08-14: 將 URL 路徑轉換回檔案系統絕對路徑
        # 資料庫中儲存的是像 /media/reports/report.html 這樣的 URL，
        # 我們需要將其轉換回像 /app/uploads/reports/report.html 這樣的絕對檔案系統路徑。
        if output_filename.startswith('/media/'):
            # 移除 '/media/' 前綴並與上傳目錄合併
            relative_path = output_filename.lstrip('/media/')
            file_path = UPLOADS_DIR / relative_path
        else:
            # 作為備用，如果路徑不是 /media/ 開頭，則假設它是一個絕對路徑
            # 這可以保持對舊資料格式的相容性
            file_path = Path(output_filename)

        if not file_path.is_file():
            log.error(f"❌ 檔案系統中的檔案不存在: {file_path}")
            raise HTTPException(status_code=404, detail="檔案遺失或無法讀取。")

        # 提供檔案下載
        from fastapi.responses import FileResponse
        ext = file_path.suffix.lower()
        if ext == '.pdf':
            media_type = 'application/pdf'
        elif ext == '.html':
            media_type = 'text/html'
        elif ext == '.mp4':
            media_type = 'video/mp4'
        elif ext in ['.mp3', '.m4a', '.wav', '.flac']:
            media_type = f'audio/{ext.strip(".")}'
        else:
            media_type = 'text/plain'
        return FileResponse(path=file_path, filename=file_path.name, media_type=media_type)

    except (json.JSONDecodeError, KeyError) as e:
        log.error(f"❌ 解析任務 {task_id} 的結果時出錯: {e}")
        raise HTTPException(status_code=500, detail="無法解析任務結果。")


@app.post("/api/rename/{task_id}", status_code=200)
async def rename_task_file(task_id: str, request: Request):
    """
    重新命名與已完成任務關聯的檔案。
    """
    log.info(f"收到重新命名任務 {task_id} 的請求。")
    try:
        data = await request.json()
        new_filename_base = data.get("new_filename")
        if not new_filename_base:
            raise HTTPException(status_code=400, detail="請求中未提供 'new_filename'。")

        task = db_client.get_task_status(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="找不到指定的任務 ID。")
        if task['status'] != 'completed':
            raise HTTPException(status_code=400, detail="只能重新命名已完成的任務。")

        result_data = json.loads(task['result'])
        old_path_str = result_data.get("output_path")
        if not old_path_str:
            raise HTTPException(status_code=500, detail="任務結果中找不到檔案路徑。")

        old_path = Path(old_path_str)
        file_extension = old_path.suffix
        new_path = old_path.with_name(f"{new_filename_base}{file_extension}")

        if old_path == new_path:
            return {"status": "success", "message": "新舊檔名相同，無需變更。", "new_filename": new_filename_base}

        if new_path.exists():
            raise HTTPException(status_code=409, detail=f"目標檔名 {new_path.name} 已存在。")

        os.rename(old_path, new_path)
        log.info(f"檔案已從 {old_path} 重新命名為 {new_path}")

        # Update the result in the database
        result_data["output_path"] = str(new_path)
        result_data["video_title"] = new_filename_base

        db_client.update_task_status(task_id, 'completed', json.dumps(result_data))
        log.info(f"已更新資料庫中任務 {task_id} 的結果。")

        return {"status": "success", "message": "檔案重新命名成功。", "new_filename": new_filename_base}

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="無法解析任務結果。")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="找不到要重新命名的原始檔案。")
    except Exception as e:
        log.error(f"❌ 重新命名檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"伺服器內部錯誤: {e}")


# --- 提示詞管理 API ---
PROMPTS_FILE_PATH = ROOT_DIR / "src" / "prompts" / "default_prompts.json"

@app.get("/api/prompts")
async def get_prompts():
    """讀取並回傳 prompts/default_prompts.json 的內容。"""
    if not PROMPTS_FILE_PATH.is_file():
        log.error(f"提示詞檔案遺失: {PROMPTS_FILE_PATH}")
        raise HTTPException(status_code=404, detail="提示詞設定檔 (default_prompts.json) 找不到。")
    try:
        with open(PROMPTS_FILE_PATH, 'r', encoding='utf-8') as f:
            prompts = json.load(f)
        return JSONResponse(content=prompts)
    except Exception as e:
        log.error(f"讀取或解析提示詞檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法讀取或解析提示詞檔案。")

@app.post("/api/prompts")
async def save_prompts(request: Request):
    """接收前端傳來的 JSON 並儲存至 prompts/default_prompts.json。"""
    try:
        new_prompts = await request.json()
        # 進行基本的驗證，確保它是一個字典
        if not isinstance(new_prompts, dict):
            raise HTTPException(status_code=400, detail="無效的資料格式，應為 JSON 物件。")

        with open(PROMPTS_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_prompts, f, ensure_ascii=False, indent=4)

        log.info(f"✅ 提示詞已成功儲存至: {PROMPTS_FILE_PATH}")
        return {"status": "success", "message": "提示詞已成功更新。"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="請求內容不是有效的 JSON 格式。")
    except Exception as e:
        log.error(f"儲存提示詞檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"儲存提示詞檔案時發生伺服器內部錯誤: {e}")


@app.post("/api/upload_cookies", status_code=200)
async def upload_cookies_file(file: UploadFile = File(...)):
    """
    接收使用者上傳的 cookies.txt 檔案並儲存。
    """
    if "cookies.txt" not in file.filename.lower():
        raise HTTPException(status_code=400, detail="檔案名稱必須是 'cookies.txt' 或包含該字樣。")

    cookies_path = UPLOADS_DIR / "cookies.txt"
    try:
        with open(cookies_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        log.info(f"🍪 Cookies 檔案已儲存至: {cookies_path}")
        return {"status": "success", "message": "Cookies 檔案上傳成功。"}
    except Exception as e:
        log.error(f"❌ 儲存 Cookies 檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"無法儲存 Cookies 檔案: {e}")
    finally:
        await file.close()


# --- YouTube 功能相關 API ---

@app.post("/api/youtube/validate_api_key")
@app.post("/api/youtube/validate_api_key/") # 增加此行以處理結尾斜線
async def validate_api_key(request: Request):
    """接收前端傳來的 API Key 並進行驗證。"""
    try:
        payload = await request.json()
        api_key = payload.get("api_key")
        if not api_key:
            raise HTTPException(status_code=400, detail="未提供 API 金鑰。")

        # 在模擬模式下，只要金鑰非空就視為有效
        if IS_MOCK_MODE:
            log.info("模擬模式：將非空 API 金鑰視為有效。")
            return {"valid": True}

        # 真實模式下，呼叫工具進行驗證
        tool_script_path = ROOT_DIR / "src" / "tools" / "gemini_processor.py"
        cmd = [sys.executable, str(tool_script_path), "--command=validate_key"]

        # 將金鑰作為環境變數傳遞給子程序，更安全
        env = os.environ.copy()
        env["GOOGLE_API_KEY"] = api_key

        # 設定 check=False，因為我們預期在金鑰無效時程序會失敗
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=env, check=False)

        if result.returncode == 0:
            log.info(f"API 金鑰驗證成功。")
            return {"valid": True}
        else:
            log.warning(f"API 金鑰驗證失敗。Stderr: {result.stderr.strip()}")
            # 嘗試從 stderr 中提取更具體的錯誤訊息
            error_message = result.stderr.strip()
            if "API key not valid" in error_message:
                detail = "API 金鑰無效。請檢查您的金鑰是否正確。"
            else:
                detail = "金鑰驗證失敗，可能是網路問題或金鑰權限不足。"
            return JSONResponse(status_code=400, content={"valid": False, "detail": detail})

    except Exception as e:
        log.error(f"驗證 API 金鑰時發生伺服器內部錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"伺服器內部錯誤: {e}")


@app.post("/api/youtube/models")
async def get_youtube_models(request: Request):
    """獲取可用的 Gemini 模型列表。"""
    # JULES'S FIX (2025-08-20): 移除模擬模式檢查，強制此端點一律嘗試呼叫真實的 Gemini API。
    # 這是為了解決痛點 1：模型列表功能失效的問題。
    try:
        payload = await request.json()
        api_key = payload.get("api_key")
        if not api_key:
            raise HTTPException(status_code=400, detail="請求中未提供 API 金鑰。")

        log.info("收到獲取 Gemini 模型列表的請求，正在準備執行工具腳本...")

        env = os.environ.copy()
        env["GOOGLE_API_KEY"] = api_key

        tool_script_path = ROOT_DIR / "src" / "tools" / "gemini_processor.py"
        cmd = [sys.executable, str(tool_script_path), "--command=list_models"]

        log.info(f"正在執行指令: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8',
            env=env
        )

        models = json.loads(result.stdout)
        log.info(f"成功從工具腳本獲取到 {len(models)} 個模型。")
        return {"models": models}

    except subprocess.CalledProcessError as e:
        log.error(f"執行 gemini_processor.py 失敗。返回碼: {e.returncode}")
        log.error(f"Stderr: {e.stderr.strip()}")
        raise HTTPException(status_code=401, detail=f"無法使用提供的 API 金鑰獲取模型列表: {e.stderr.strip()}")
    except json.JSONDecodeError as e:
        log.error(f"解析來自 gemini_processor.py 的輸出時出錯: {e}")
        raise HTTPException(status_code=500, detail="無法解析來自模型工具的輸出。")
    except Exception as e:
        log.error(f"獲取 Gemini 模型列表時發生未預期錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取 Gemini 模型列表時發生內部錯誤。")


@app.post("/api/youtube/process", status_code=202)
async def process_youtube_urls(request: Request):
    """
    接收 YouTube URL，並根據前端傳來的參數，建立對應的下載和 AI 分析任務。
    """
    payload = await request.json()
    requests_list = payload.get("requests", [])

    # JULES'S FIX: 為了相容舊的 local_run.py 測試腳本
    if not requests_list and "urls" in payload:
        log.warning("偵測到舊版的 'urls' 負載格式，正在進行相容處理。")
        requests_list = [{"url": url, "filename": None} for url in payload.get("urls", [])]


    # 新的彈性參數
    model = payload.get("model")
    api_key = payload.get("api_key") # 提取 API 金鑰
    tasks_to_run = payload.get("tasks", "summary,transcript") # e.g., "summary,transcript,translate"
    output_format = payload.get("output_format", "html") # "html" or "txt"
    download_only = payload.get("download_only", False)
    download_type = payload.get("download_type", "audio") # JULES'S NEW FEATURE

    if not requests_list:
        # 在加入相容性邏輯後，更新錯誤訊息
        raise HTTPException(status_code=400, detail="請求中必須包含 'requests' 或 'urls'。")
    if not download_only and not model:
        raise HTTPException(status_code=400, detail="執行 AI 分析時必須提供 'model'。")
    if not download_only and not api_key:
        raise HTTPException(status_code=400, detail="執行 AI 分析時必須提供 'api_key'。")

    tasks = []
    for req_item in requests_list:
        url = req_item.get("url")
        filename = req_item.get("filename")

        if not url or not url.strip():
            continue

        task_id = str(uuid.uuid4())

        if download_only:
            # JULES'S NEW FEATURE: Pass download_type to payload
            task_payload = {"url": url, "output_dir": str(UPLOADS_DIR), "custom_filename": filename, "download_type": download_type}
            db_client.add_task(task_id, json.dumps(task_payload), task_type='youtube_download_only')
            tasks.append({"url": url, "task_id": task_id})
        else:
            download_task_id = task_id
            process_task_id = str(uuid.uuid4())

            # JULES'S NEW FEATURE: Pass download_type to download payload
            download_payload = {"url": url, "output_dir": str(UPLOADS_DIR), "custom_filename": filename, "download_type": download_type}
            # 將所有新參數存入 process 任務的 payload
            process_payload = {
                "model": model,
                "api_key": api_key, # 將 API 金鑰儲存到任務 payload
                "output_dir": "transcripts",
                "tasks": tasks_to_run,
                "output_format": output_format
            }

            db_client.add_task(download_task_id, json.dumps(download_payload), task_type='youtube_download')
            db_client.add_task(process_task_id, json.dumps(process_payload), task_type='gemini_process', depends_on=download_task_id)

            # JULES'S FIX: Return both task IDs so the frontend can track the full chain.
            tasks.append({
                "url": url,
                "task_id": download_task_id, # For display and initial tracking
                "final_task_id": process_task_id, # For listening to the final result
                "task_type": "youtube_process_chain"
            })

    return JSONResponse(content={"message": f"已為 {len(tasks)} 個 URL 建立處理任務。", "tasks": tasks})


# JULES'S REFACTOR (2025-08-20): 根據計畫，移除所有基於執行緒的任務觸發器。
# 這些 `trigger_*` 和 `run_*_in_background` 函式已被新的 Huey Worker 架構取代。
# 移除這些函式可以確保所有背景任務都透過一致的任務佇列機制來處理，
# 避免了舊的執行緒模式與新 Worker 模式之間的衝突。

@app.get("/api/debug/all_frontend_action_logs")
async def get_all_frontend_action_logs():
    """
    [僅供測試] 獲取所有前端操作日誌的完整列表。
    用於 E2E 測試，以驗證日誌是否已成功寫入資料庫。
    """
    try:
        # 我們只關心來自 'frontend_action' logger 的日誌
        logs = db_client.get_system_logs(sources=['frontend_action'])
        # 確保即使沒有日誌也回傳一個空列表
        logs = logs or []
        return JSONResponse(content={"logs": logs})
    except Exception as e:
        log.error(f"❌ 查詢所有前端日誌時出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查詢所有前端日誌時發生內部錯誤")


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            log.info(f"從 WebSocket 收到訊息: {data}")

            try:
                message = json.loads(data)
                msg_type = message.get("type")
                payload = message.get("payload", {})

                # JULES'S REFACTOR (2025-08-20): 根據新的 Huey Worker 架構，API Server 不再負責觸發任務。
                # Worker 會自行從資料庫拉取任務。因此，所有 `START_*` 類型的 WebSocket 訊息都將被忽略。
                # 這樣可以確保任務處理的唯一來源是 Worker，避免了雙重執行的風險。

                if msg_type == "CHECK_LOCAL_MODELS":
                    log.info("收到檢查本地模型的請求。")
                    available_models = [
                        model for model in KNOWN_WHISPER_MODELS if check_model_exists(model)
                    ]
                    response_payload = {"models": available_models}
                    log.info(f"準備回傳 LOCAL_MODELS_STATUS，內容: {response_payload}")
                    await websocket.send_json({
                        "type": "LOCAL_MODELS_STATUS",
                        "payload": response_payload
                    })
                    log.info("LOCAL_MODELS_STATUS 訊息已發送。")

                elif msg_type == "DOWNLOAD_MODEL":
                    model_size = payload.get("model")
                    if model_size and model_size in KNOWN_WHISPER_MODELS:
                        log.info(f"收到手動下載模型 '{model_size}' 的請求，正在建立任務...")
                        # 建立一個下載任務，讓 Huey Worker 來處理
                        download_task_id = str(uuid.uuid4())
                        download_payload = {"model_size": model_size}
                        db_client.add_task(
                            download_task_id,
                            json.dumps(download_payload),
                            task_type='download_model' # JULES'S FIX: 使用更精確的任務類型
                        )
                        await websocket.send_json({"type": "ACK", "payload": f"已為模型 '{model_size}' 建立下載任務。"})
                    else:
                        await manager.broadcast_json({"type": "ERROR", "payload": "無效或未提供的模型大小參數"})

                elif msg_type in ["START_TRANSCRIPTION", "START_YOUTUBE_PROCESSING"]:
                    task_id = payload.get("task_id", "N/A")
                    log.info(f"收到舊的任務觸發訊息 '{msg_type}' (任務 ID: {task_id})，將予以忽略。任務將由 Huey Worker 自動處理。")
                    await websocket.send_json({
                        "type": "ACK",
                        "payload": f"已收到 '{msg_type}' 請求，但此操作現由背景工作者自動處理，無需手動觸發。"
                    })

                else:
                    await manager.broadcast_json({
                        "type": "ECHO",
                        "payload": f"已收到未知類型的訊息: {msg_type}"
                    })

            except json.JSONDecodeError:
                log.error("收到了非 JSON 格式的 WebSocket 訊息。")
                await manager.broadcast_json({"type": "ERROR", "payload": "訊息必須是 JSON 格式"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        log.info("WebSocket 用戶端已離線。")
    except Exception as e:
        log.error(f"WebSocket 發生未預期錯誤: {e}", exc_info=True)
        # 確保在發生錯誤時也中斷連線
        if websocket in manager.active_connections:
            manager.disconnect(websocket)


@app.get("/api/health")
async def health_check():
    """提供一個簡單的健康檢查端點。"""
    return {"status": "ok", "message": "API Server is running."}


@app.post("/api/internal/notify_task_update", status_code=200)
async def notify_task_update(payload: Dict):
    """
    一個內部端點，供 Worker 程序在任務完成時呼叫，
    以便透過 WebSocket 將更新廣播給前端。
    """
    task_id = payload.get("task_id")
    status = payload.get("status")
    result = payload.get("result")
    log.info(f"🔔 收到來自 Worker 的任務更新通知: Task {task_id} -> {status}")

    # JULES'S FIX: 查詢任務類型以發送正確的 WebSocket 訊息
    task_info = db_client.get_task_status(task_id)
    task_type = task_info.get("type", "transcribe") if task_info else "transcribe"

    message_type = "TRANSCRIPTION_STATUS"
    if "youtube" in task_type or "gemini" in task_type:
        message_type = "YOUTUBE_STATUS"

    log.info(f"根據任務類型 '{task_type}'，將使用 WebSocket 訊息類型: '{message_type}'")

    # 確保 result 是字典格式
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            log.warning(f"來自 worker 的任務 {task_id} 結果不是有效的 JSON 格式。")

    message = {
        "type": message_type,
        "payload": {
            "task_id": task_id,
            "status": status,
            "result": result,
            "task_type": task_type  # 將 task_type 也傳給前端
        }
    }
    await manager.broadcast_json(message)
    return {"status": "notification_sent"}


# 這是 Vue.js SPA (單頁應用) 的 catch-all 路由。
# 它確保任何非 API、非靜態檔案的請求都會回傳主 index.html，
# 然後由 Vue Router 接管前端的路由。
# 必須放在所有其他 @app.get("/") 路由的後面。
@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_vue_app(request: Request, full_path: str):
    """根端點，提供 Vue.js 前端操作介面。"""
    vue_index_path = VUE_APP_DIST_DIR / "index.html"
    if not vue_index_path.is_file():
        log.error(f"找不到 Vue 前端入口檔案: {vue_index_path}")
        # JULES: 提供一個更友善的錯誤訊息，方便除錯
        return HTMLResponse(content="<h1>500: Frontend Not Built</h1><p>Vue app not found. Please run `bun install && bun run build` in the `vue-app` directory.</p>", status_code=500)
    return HTMLResponse(content=vue_index_path.read_text(encoding="utf-8"), status_code=200)


# --- 主程式啟動 ---
if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="鳳凰音訊轉錄儀 API 伺服器")
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="伺服器監聽的埠號"
    )
    args, _ = parser.parse_known_args()

    # JULES: 移除此處的資料庫初始化呼叫。
    # 父程序 src/core/orchestrator.py 將會負責此事，以避免競爭條件。

    # JULES'S FIX: The database logging is now set up via the app's lifespan event.
    # setup_database_logging() is no longer needed here.

    log.info("🚀 啟動 API 伺服器 (v3)...")
    log.info(f"請在瀏覽器中開啟 http://127.0.0.1:{args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)
