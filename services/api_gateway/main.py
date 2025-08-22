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
    add_log.delay("api_gateway", "INFO", "--- [API 閘道] 正在啟動 ---")

    # 步驟 1: 優先初始化日誌資料庫，確保它最先就緒
    add_log.delay("api_gateway", "INFO", "步驟 1/2: 初始化日誌資料庫 (logs.db)...")
    initialize_log_database()
    add_log.delay("api_gateway", "INFO", "日誌資料庫初始化完成。")

    # 步驟 2: 在背景啟動所有 Huey 工作者。
    # Huey 會在第一次使用時自動建立和初始化它的佇列資料庫 (queue.db)。
    add_log.delay("api_gateway", "INFO", "步驟 2/2: 在背景啟動所有服務工作者...")
    asyncio.create_task(install_and_launch_workers())
    add_log.delay("api_gateway", "INFO", "工作者啟動任務已觸發。")

    yield

    # 在伺服器關閉時執行的程式碼 (目前無操作)
    add_log.delay("api_gateway", "INFO", "--- [API 閘道] 正在關閉 ---")


# --- Huey 任務定義 ---
# 注意：這些是任務的「簽章」。真正的實作將在 worker 中定義。
# 透過在這裡定義它們，我們可以讓 Huey 知道這些任務的存在，
# 並允許 api_gateway 將它們放入佇列，而無需直接導入 worker 的程式碼。
@huey.task()
def process_transcription(file_path: str, original_filename: str):
    # 這裡只是一個任務簽章，真正的邏輯在 worker 中。
    # 我們可以從這裡發送一個日誌來表示任務已被成功接收。
    add_log.delay("api_gateway", "INFO", f"任務已成功放入佇列: process_transcription for {original_filename}")

@huey.task()
def process_youtube_video(url: str):
    # 同上，只是一個任務簽章。
    add_log.delay("api_gateway", "INFO", f"任務已成功放入佇列: process_youtube_video for {url}")


# --- Pydantic 模型 ---
class YouTubeRequest(BaseModel):
    youtube_url: str


app = FastAPI(title="API 閘道", version="0.2.0", lifespan=lifespan)

# --- 服務的 URL ---
# 在真實的雲端環境中，這些應該是可設定的，例如從環境變數讀取
FILE_SERVICE_URL = "http://localhost:8001"


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
    add_log.delay("api_gateway", "DEBUG", f"檔案已暫時儲存至: {saved_file_path}")

    try:
        # 使用 .delay() 將任務放入佇列，而不是立即執行
        process_transcription.delay(file_path=saved_file_path, original_filename=file.filename)
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
        # 使用 .delay() 將任務放入佇列
        process_youtube_video.delay(url=request.youtube_url)
        return {
            "message": "YouTube 處理任務已成功排入佇列。",
            "youtube_url": request.youtube_url,
            "task_queued": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法將 YouTube 任務放入佇列: {e}")


if __name__ == "__main__":
    # API Gateway 運行在 8000 連接埠，這是常見的閘道連接埠
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
