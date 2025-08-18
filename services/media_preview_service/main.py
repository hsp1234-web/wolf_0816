# services/media_preview_service/main.py
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from .config import settings

app = FastAPI(title="媒體預覽服務", version="0.1.0")

@app.get("/", summary="服務健康檢查")
def read_root():
    return {"status": "ok", "service": "Media Preview Service"}

@app.get("/media/{filename}", summary="串流媒體檔案")
async def stream_media(filename: str):
    """
    從媒體根目錄串流一個指定的檔案。
    這個端點支援 HTTP Range Requests，因此可以用於音訊或影片播放。
    """
    try:
        # 基本的安全性檢查，防止路徑遍歷攻擊
        if ".." in filename:
            raise HTTPException(status_code=400, detail="無效的檔案名稱。")

        file_path = settings.MEDIA_ROOT_DIR / filename

        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="找不到指定的媒體檔案。")

        return FileResponse(file_path)

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"串流檔案時發生錯誤: {e}")


if __name__ == "__main__":
    # 媒體預覽服務運行在 8009 連接埠
    uvicorn.run("main:app", host="0.0.0.0", port=8009, reload=True)
