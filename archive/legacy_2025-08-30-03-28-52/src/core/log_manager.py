import sqlite3
from pathlib import Path
import threading
from datetime import datetime
import pytz

# --- 統一的路徑定義 ---
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DB_PATH = ROOT_DIR / "logs.db"
TIMEZONE = "Asia/Taipei" # 或者從設定檔讀取

# 使用 threading.local() 來確保每個執行緒都有自己獨立的資料庫連線
# 這對於在多執行緒環境 (如 FastAPI) 中使用 SQLite 至關重要
local_storage = threading.local()

def get_log_db_connection():
    """
    為當前執行緒建立並回傳一個日誌資料庫連線。
    如果連線已存在，則直接回傳。
    """
    if not hasattr(local_storage, 'log_db_conn'):
        try:
            # `timeout=10` 讓程序在資料庫被鎖定時，最多等待 10 秒
            conn = sqlite3.connect(LOG_DB_PATH, timeout=10, check_same_thread=False)
            # 啟用 WAL (Write-Ahead Logging) 模式，提升併發效能
            conn.execute("PRAGMA journal_mode=WAL;")
            local_storage.log_db_conn = conn
        except sqlite3.Error as e:
            print(f"日誌資料庫連線失敗: {e}")
            return None
    return local_storage.log_db_conn

def initialize_log_database():
    """
    初始化日誌資料庫，建立 logs 資料表。
    應在應用程式啟動時被呼叫一次。
    """
    conn = None
    try:
        conn = get_log_db_connection()
        if not conn:
            raise ConnectionError("無法建立日誌資料庫連線。")

        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL
        );
        """)
        conn.commit()
        print(f"日誌資料庫 '{LOG_DB_PATH}' 已成功初始化。")
    except Exception as e:
        print(f"日誌資料庫初始化失敗: {e}")
    finally:
        # 初始化後不斷開連線，讓 local_storage 繼續持有
        pass

def log_message(source: str, level: str, message: str):
    """
    將一條日誌訊息寫入資料庫。
    這是所有服務和工作者應該呼叫的統一日誌函式。
    """
    conn = None
    try:
        conn = get_log_db_connection()
        if not conn:
            print(f"無法獲取日誌資料庫連線，日誌遺失: [{source}] {message}")
            return

        now = datetime.now(pytz.timezone(TIMEZONE)).isoformat()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO logs (timestamp, source, level, message) VALUES (?, ?, ?, ?)",
            (now, source, level.upper(), message)
        )
        conn.commit()
    except Exception as e:
        # 如果日誌系統本身出錯，我們只能印出來了
        print(f"寫入日誌到資料庫時發生錯誤: {e}")

if __name__ == '__main__':
    # 手動初始化資料庫以供測試
    print("正在手動初始化日誌資料庫...")
    initialize_log_database()
    print("\n正在測試寫入日誌...")
    log_message("TEST", "INFO", "這是一條測試日誌。")
    log_message("WORKER_A", "DEBUG", "正在處理任務...")
    log_message("API_GATEWAY", "ERROR", "一個預期的錯誤發生了。")
    print("測試完成。請檢查 logs.db 檔案。")
