# services/api_gateway/main.py
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
import requests

from pydantic import BaseModel

# 匯入我們在 transcription_service 中定義的 huey 任務
from ..transcription_service.tasks import create_transcription_task
# 匯入 YouTube 下載服務的任務
from ..youtube_service.tasks import download_youtube_video


# --- Pydantic 模型 ---
class YouTubeRequest(BaseModel):
    youtube_url: str


app = FastAPI(title="API 閘道", version="0.1.0")

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
    2. 將檔案轉發給 `檔案管理服務` 進行儲存。
    3. 將一個 `轉錄任務` 加入到 Huey 任務佇列中。
    4. 立即回傳，告知使用者任務已排入佇列。
    """

    # --- 1. 將檔案轉發給檔案管理服務 ---
    try:
        # 準備要傳送給檔案服務的檔案
        files = {'file': (file.filename, file.file, file.content_type)}

        # 呼叫檔案管理服務的 /upload 端點
        upload_response = requests.post(f"{FILE_SERVICE_URL}/upload", files=files)

        # 檢查回應是否成功
        upload_response.raise_for_status()

        # 從回應中取得儲存後的檔案資訊
        file_info = upload_response.json()
        saved_file_path = file_info.get("path")

        if not saved_file_path:
            raise HTTPException(status_code=500, detail="檔案服務未回傳儲存路徑。")

        print(f"檔案已成功儲存至: {saved_file_path}")

    except requests.exceptions.RequestException as e:
        # 處理網路或服務無回應的錯誤
        raise HTTPException(status_code=503, detail=f"無法連接檔案管理服務: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"呼叫檔案管理服務時發生未知錯誤: {e}")

    # --- 2. 將轉錄任務放入 Huey 佇列 ---
    try:
        print(f"準備將轉錄任務放入佇列，檔案路徑: {saved_file_path}")
        # 呼叫任務函式。Huey 會自動將其序列化並放入佇列，而不是立即執行。
        create_transcription_task(saved_file_path, file.filename)

        return {
            "message": "檔案已成功上傳，並已排入佇列等待轉錄。",
            "filename": file.filename,
            "task_queued": True
        }
    except Exception as e:
        # 處理佇列服務可能發生的錯誤 (例如資料庫無法寫入)
        raise HTTPException(status_code=500, detail=f"無法將任務放入佇列: {e}")


@app.post("/transcribe_youtube", summary="提供 YouTube 網址並觸發非同步下載與轉錄", status_code=202)
async def transcribe_from_youtube(request: YouTubeRequest):
    """
    接收一個 YouTube URL，並將下載與轉錄任務放入佇列。
    """
    try:
        log_message = f"接收到 YouTube 轉錄請求: {request.youtube_url}"
        print(log_message)

        # 將下載任務放入佇列
        download_youtube_video(request.youtube_url)

        return {
            "message": "YouTube 下載與轉錄任務已成功排入佇列。",
            "youtube_url": request.youtube_url,
            "task_queued": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法將 YouTube 下載任務放入佇列: {e}")


if __name__ == "__main__":
    # API Gateway 運行在 8000 連接埠，這是常見的閘道連接埠
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
