# services/file_management_service/main.py
# 這是檔案管理服務的進入點

import uvicorn
import shutil
import logging
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from .config import settings

# --- 新增：磁碟容量檢查功能 ---
def check_disk_capacity(threshold_percent: int = 80):
    """
    檢查根目錄的磁碟使用率，如果超過閾值則拋出嚴重錯誤。
    這是一個啟動前的保護機制。
    """
    try:
        total, used, free = shutil.disk_usage('/')
        usage_percent = (used / total) * 100
        logging.info(f"磁碟容量檢查: 目前使用率 {usage_percent:.2f}% (閾值: {threshold_percent}%)")
        if usage_percent >= threshold_percent:
            error_msg = f"錯誤碼 102：磁碟空間嚴重不足！目前使用率 {usage_percent:.2f}%，已達或超過 {threshold_percent}% 的閾值。服務無法啟動。"
            logging.critical(error_msg) # 使用 CRITICAL 級別日誌
            raise RuntimeError(error_msg)
    except FileNotFoundError:
        logging.warning("無法找到根目錄 '/'，跳過磁碟容量檢查。")
    except Exception as e:
        error_msg = f"錯誤碼 103：無法檢查磁碟空間。錯誤: {e}"
        logging.critical(error_msg)
        raise RuntimeError(error_msg) from e

# 建立 FastAPI 應用實例
app = FastAPI(title="檔案管理服務", version="0.1.0")

# 應用程式啟動時執行的事件
@app.on_event("startup")
def on_startup():
    """
    應用程式啟動時執行的初始化工作。
    """
    # --- 步驟 1: 執行磁碟容量健康檢查 ---
    logging.info("執行啟動前健康檢查...")
    check_disk_capacity()
    logging.info("✅ 磁碟容量檢查通過。")

    # --- 步驟 2: 確保上傳目錄存在 ---
    upload_path = Path(settings.UPLOADS_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)
    logging.info(f"✅ 確保上傳目錄 '{upload_path.resolve()}' 已建立。")


@app.get("/", summary="服務健康檢查", description="回傳服務是否正常的狀態。")
def read_root():
    """
    根節點，用於簡單的健康檢查。
    """
    return {"status": "ok", "service": "File Management Service"}


@app.post("/upload", summary="上傳檔案", description="上傳一個檔案到伺服器指定的儲存目錄。")
async def upload_file(file: UploadFile = File(...)):
    """
    接收客戶端上傳的檔案並儲存。

    - **file**: 從請求中讀取的檔案。
    - **返回**: 包含儲存後檔案資訊的 JSON。
    """
    try:
        # 組合儲存路徑
        upload_dir = Path(settings.UPLOADS_DIR)
        file_path = upload_dir / file.filename

        # 檢查檔案是否已存在，避免覆寫
        if file_path.exists():
            raise HTTPException(status_code=409, detail=f"檔案 '{file.filename}' 已存在。")

        # 使用 shutil.copyfileobj 來儲存檔案，這對於大檔案更有效率
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "filename": file.filename,
            "content_type": file.content_type,
            "path": str(file_path.resolve()),
            "message": "檔案上傳成功！"
        }
    except HTTPException as e:
        # 重新拋出 HTTP 異常
        raise e
    except Exception as e:
        # 處理其他未預期的錯誤
        raise HTTPException(status_code=500, detail=f"檔案上傳失敗: {e}")
    finally:
        # 確保檔案控制代碼被關閉
        file.file.close()


@app.get("/download/{filename}", summary="下載檔案", description="根據檔名從伺服器下載指定的檔案。")
async def download_file(filename: str):
    """
    根據提供的檔名，回傳檔案。

    - **filename**: 要下載的檔案名稱。
    - **返回**: 檔案回應或 404 錯誤。
    """
    file_path = Path(settings.UPLOADS_DIR) / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"檔案 '{filename}' 不存在。")

    return FileResponse(path=file_path, filename=filename)


@app.delete("/delete/{filename}", summary="刪除檔案", description="根據檔名從伺服器刪除指定的檔案。")
async def delete_file(filename: str):
    """
    根據提供的檔名，刪除檔案。

    - **filename**: 要刪除的檔案名稱。
    - **返回**: 操作成功訊息或 404 錯誤。
    """
    try:
        file_path = Path(settings.UPLOADS_DIR) / filename
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"檔案 '{filename}' 不存在，無法刪除。")

        file_path.unlink() # 刪除檔案

        return {"message": f"檔案 '{filename}' 已成功刪除。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刪除檔案時發生錯誤: {e}")


@app.get("/files", summary="列出所有已上傳的檔案", description="取得儲存目錄中所有檔案的清單及其詳細資訊。")
async def list_files():
    """
    掃描上傳目錄並回傳所有檔案的列表。
    """
    upload_dir = Path(settings.UPLOADS_DIR)
    if not upload_dir.is_dir():
        return []

    try:
        files_info = []
        for file_path in upload_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files_info.append({
                    "filename": file_path.name,
                    "size_bytes": stat.st_size,
                    "last_modified": stat.st_mtime,
                })
        return files_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"讀取檔案列表時發生錯誤: {e}")


# 為了能夠直接執行此檔案來啟動服務 (主要用於開發)
if __name__ == "__main__":
    # 使用 uvicorn 來啟動服務，監聽在 8001 連接埠
    # 注意：在生產環境中，應使用 Gunicorn + Uvicorn workers 來管理
    uvicorn.run("main:app", host="0.0.0.0", port=8001)
