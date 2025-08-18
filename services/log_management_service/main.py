# services/log_management_service/main.py
# 這是日誌管理服務的進入點

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from pathlib import Path
import datetime

from .config import settings

# --- Pydantic 模型 ---
class LogEntry(BaseModel):
    service: str
    level: str = "INFO"
    message: str

# --- FastAPI 應用設定 ---
app = FastAPI(title="日誌管理服務", version="0.1.0")


@app.on_event("startup")
def on_startup():
    """
    應用啟動時，確保日誌檔案所在的目錄存在。
    """
    log_file_path = Path(settings.LOG_FILE_PATH)
    log_dir = log_file_path.parent
    log_dir.mkdir(parents=True, exist_ok=True)
    print(f"確保日誌目錄 '{log_dir.resolve()}' 已建立。")

def write_log_to_file(log_message: str):
    """
    將格式化後的日誌訊息附加到檔案中。
    這是一個背景任務，以避免阻塞 API 回應。
    """
    log_file_path = Path(settings.LOG_FILE_PATH)
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(log_message + "\n")


@app.get("/", summary="服務健康檢查")
def read_root():
    """
    根節點，用於簡單的健康檢查。
    """
    return {"status": "ok", "service": "Log Management Service"}

@app.post("/log", summary="接收並記錄日誌", status_code=202)
async def create_log_entry(entry: LogEntry, background_tasks: BackgroundTasks):
    """
    接收來自其他服務的日誌條目，並將其寫入日誌檔案。
    """
    try:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_message = f"[{timestamp}] [{entry.service}] [{entry.level}] {entry.message}"

        # 使用背景任務來寫入檔案，這樣 API 可以立即回應
        background_tasks.add_task(write_log_to_file, log_message)

        return {"message": "日誌已接收"}
    except Exception as e:
        # 雖然寫入是背景任務，但仍保留此處以防格式化等同步操作出錯
        raise HTTPException(status_code=500, detail=f"處理日誌時發生錯誤: {e}")


if __name__ == "__main__":
    # 使用 uvicorn 來啟動服務，監聽在 8003 連接埠
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)
