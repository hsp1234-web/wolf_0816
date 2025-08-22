# services/api_gateway/main.py
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
import requests
import asyncio
from contextlib import asynccontextmanager
from pydantic import BaseModel

# 導入日誌管理器和佇列設定
from src.core.log_manager import initialize_log_database
from src.core.queue_config import huey
# 導入背景工作者啟動器
from src.core.background_tasks import install_and_launch_workers
# 導入新的日誌任務
from workers.logging_worker import add_log

# --- FastAPI 生命週期事件 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在伺服器啟動時執行的程式碼
    add_log("api_gateway", "INFO", "--- [API 閘道] 正在啟動 ---")

    # 步驟 1: 優先初始化日誌資料庫，確保它最先就緒
    add_log("api_gateway", "INFO", "步驟 1/2: 初始化日誌資料庫 (logs.db)...")
    initialize_log_database()
    add_log("api_gateway", "INFO", "日誌資料庫初始化完成。")

    # 步驟 2: 在背景啟動所有 Huey 工作者。
    # Huey 會在第一次使用時自動建立和初始化它的佇列資料庫 (queue.db)。
    add_log("api_gateway", "INFO", "步驟 2/2: 在背景啟動所有服務工作者...")
    asyncio.create_task(install_and_launch_workers())
    add_log("api_gateway", "INFO", "工作者啟動任務已觸發。")

    yield

    # 在伺服器關閉時執行的程式碼 (目前無操作)
    add_log("api_gateway", "INFO", "--- [API 閘道] 正在關閉 ---")


# --- Huey 任務定義 ---
# 注意：這些是任務的「簽章」。真正的實作將在 worker 中定義。
# 透過在這裡定義它們，我們可以讓 Huey 知道這些任務的存在，
# 並允許 api_gateway 將它們放入佇列，而無需直接導入 worker 的程式碼。
@huey.task()
def process_transcription(file_path: str, original_filename: str):
    # 這裡只是一個任務簽章，真正的邏輯在 worker 中。
    # 我們可以從這裡發送一個日誌來表示任務已被成功接收。
    add_log("api_gateway", "INFO", f"任務已成功放入佇列: process_transcription for {original_filename}")

@huey.task()
def process_youtube_video(url: str):
    # 同上，只是一個任務簽章。
    add_log("api_gateway", "INFO", f"任務已成功放入佇列: process_youtube_video for {url}")


# --- Pydantic 模型 ---
class YouTubeRequest(BaseModel):
    youtube_url: str


app = FastAPI(title="API 閘道", version="0.2.0", lifespan=lifespan)

import websockets
from fastapi import WebSocket, WebSocketDisconnect

# --- 服務的 URL ---
# 在真實的雲端環境中，這些應該是可設定的，例如從環境變數讀取
FILE_SERVICE_URL = "http://localhost:8001"
NOTIFICATION_SERVICE_WS_URL = "ws://localhost:8010/ws"


# --- WebSocket 代理 ---
@app.websocket("/ws")
async def websocket_proxy(client_websocket: WebSocket):
    """
    這個 WebSocket 端點作為一個代理，將前端的連線轉發到後端的通知服務。
    """
    await client_websocket.accept()
    add_log("websocket_proxy", "INFO", "Client connected to gateway.")

    try:
        async with websockets.connect(NOTIFICATION_SERVICE_WS_URL) as server_websocket:
            add_log("websocket_proxy", "INFO", "Gateway connected to notification service.")

            # 雙向轉發訊息
            client_to_server = asyncio.create_task(forward_messages(client_websocket, server_websocket, "c->s"))
            server_to_client = asyncio.create_task(forward_messages(server_websocket, client_websocket, "s->c"))

            # 等待任一任務結束
            done, pending = await asyncio.wait(
                [client_to_server, server_to_client],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

    except websockets.exceptions.ConnectionClosedError:
        add_log("websocket_proxy", "WARN", "Connection to notification service failed or was closed.")
    except Exception as e:
        add_log("websocket_proxy", "ERROR", f"WebSocket proxy error: {e}")
    finally:
        add_log("websocket_proxy", "INFO", "Client disconnected from gateway.")


async def forward_messages(source: WebSocket, destination: WebSocket, direction: str):
    """從來源 WebSocket 讀取訊息並轉發到目標 WebSocket。"""
    try:
        while True:
            message = await source.receive_text()
            await destination.send_text(message)
            # add_log("websocket_proxy", "DEBUG", f"Forwarded message {direction}: {message[:100]}...")
    except WebSocketDisconnect:
        add_log("websocket_proxy", "INFO", f"WebSocket disconnected in direction {direction}.")
    except Exception:
        # 捕捉其他可能的關閉錯誤
        pass


@app.get("/")
def read_root():
    return {"status": "ok", "service": "API Gateway"}

@app.post("/upload_for_transcription", summary="上傳檔案並觸發非同步轉錄", status_code=202)
async def upload_and_transcribe(file: UploadFile = File(...)):
    """
    此端點是整個核心流程的起點。
    1. 接收使用者上傳的檔案。
    2. (暫時停用) 將檔案轉發給 `檔案管理服務` 進行儲存。
    3. 將一個 `轉錄任務` 加入到 Huey 任務佇列中。
    4. 立即回傳，告知使用者任務已排入佇列。
    """
    # TODO: 重新啟用檔案管理服務的呼叫
    # 目前為了簡化，我們先假設檔案已存在於某個共享位置
    # 在真實情境中，這裡需要健壯的檔案儲存邏輯
    saved_file_path = f"/tmp/{file.filename}"
    with open(saved_file_path, "wb") as buffer:
        buffer.write(await file.read())
    add_log("api_gateway", "DEBUG", f"檔案已暫時儲存至: {saved_file_path}")

    try:
        # 正確的呼叫方式是不使用 .delay()
        process_transcription(file_path=saved_file_path, original_filename=file.filename)
        return {
            "message": "檔案已成功上傳，並已排入佇列等待轉錄。",
            "filename": file.filename,
            "task_queued": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法將轉錄任務放入佇列: {e}")


@app.post("/transcribe_youtube", summary="提供 YouTube 網址並觸發非同步下載與轉錄", status_code=202)
async def transcribe_from_youtube(request: YouTubeRequest):
    """
    接收一個 YouTube URL，並將下載與轉錄任務放入佇列。
    """
    try:
        # 正確的呼叫方式是不使用 .delay()
        process_youtube_video(url=request.youtube_url)
        return {
            "message": "YouTube 處理任務已成功排入佇列。",
            "youtube_url": request.youtube_url,
            "task_queued": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法將 YouTube 任務放入佇列: {e}")


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

# --- 靜態檔案服務設定 ---
# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = ROOT_DIR / "vue-app" / "dist"

# 掛載 /assets 目錄
if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

# 處理單頁應用 (SPA) 的路由
@app.get("/{full_path:path}", response_class=FileResponse, include_in_schema=False)
async def serve_spa(full_path: str):
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return "Frontend not built. Please run `npm run build` in `vue-app` directory.", 404

    # 檢查請求的路徑是否對應一個實際存在的檔案
    requested_path = STATIC_DIR / full_path
    if ".." not in full_path and requested_path.is_file():
        return FileResponse(requested_path)

    # 其他所有路徑都回傳主頁
    return FileResponse(index_path)


if __name__ == "__main__":
    # API Gateway 運行在 8000 連接埠，這是常見的閘道連接埠
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
