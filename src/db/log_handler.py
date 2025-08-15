# db/log_handler.py
import logging
import sqlite3
import sys
from pathlib import Path
import threading
import time

# 避免在日誌處理器中再次觸發日誌，導致無限迴圈
# 我們為這個模組建立一個獨立的、只輸出到控制台的日誌器
handler_log = logging.getLogger('db_log_handler')
handler_log.propagate = False
if not handler_log.handlers:
    console_handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('%(asctime)s - [DBLogHandler] - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    handler_log.addHandler(console_handler)

DB_FILE = Path(__file__).parent / "queue.db"

class DatabaseLogHandler(logging.Handler):
    """
    一個自訂的日誌處理器，將日誌記錄寫入 SQLite 資料庫。
    為確保執行緒安全，它為每個執行緒維護一個獨立的資料庫連線。
    """
    def __init__(self, source: str):
        super().__init__()
        self.source = source
        self.local = threading.local()

    def get_conn(self):
        """為每個執行緒建立或取得資料庫連線。"""
        if not hasattr(self.local, 'conn') or self.local.conn is None:
            try:
                # 使用較長的超時並啟用 autocommit
                conn = sqlite3.connect(DB_FILE, timeout=10, isolation_level=None)
                # 啟用 WAL (Write-Ahead Logging) 模式以提高併發性
                conn.execute("PRAGMA journal_mode=WAL")
                self.local.conn = conn
            except sqlite3.Error as e:
                handler_log.error(f"無法建立資料庫連線: {e}")
                self.local.conn = None
        return self.local.conn

    def emit(self, record: logging.LogRecord):
        """
        將日誌記錄寫入資料庫。
        """
        if record.name == 'db_log_handler':
            return

        conn = self.get_conn()
        if not conn:
            print(f"DBLogHandler Error: Cannot get DB connection. Log from {self.source} lost.", file=sys.stderr)
            return

        message = self.format(record)

        sql = "INSERT INTO system_logs (source, level, message) VALUES (?, ?, ?)"

        # JULES'S FIX: The source of the log should be the logger's name, not the handler's name.
        log_source = record.name

        retries = 5
        for i in range(retries):
            try:
                conn.execute(sql, (log_source, record.levelname, message))
                return
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    if i < retries - 1:
                        time.sleep(0.1)
                        continue
                    else:
                        print(f"DBLogHandler Error: DB locked after {retries} retries. Log from {self.source} lost.", file=sys.stderr)
                else:
                    print(f"DBLogHandler Error: {e}. Log from {self.source} lost.", file=sys.stderr)
                    return
            except Exception as e:
                print(f"DBLogHandler Error: Unexpected error: {e}. Log from {self.source} lost.", file=sys.stderr)
                return

    def __del__(self):
        if hasattr(self.local, 'conn') and self.local.conn:
            self.local.conn.close()
            self.local.conn = None
