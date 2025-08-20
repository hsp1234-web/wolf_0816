# db/log_handler.py
import logging
import sys
import queue
import threading
import time
from .client import get_client

# 避免在日誌處理器中再次觸發日誌，導致無限迴圈
handler_log = logging.getLogger('db_log_handler')
handler_log.propagate = False
if not handler_log.handlers:
    console_handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter('%(asctime)s - [DBLogHandler] - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    handler_log.addHandler(console_handler)

log_queue = queue.Queue()

def _log_worker():
    """
    一個在背景執行的工作者，從佇列中獲取日誌並透過 DBClient 發送。
    """
    while True:
        record = log_queue.get()
        if record is None:  # A sentinel to stop the thread
            break
        try:
            # 獲取客戶端實例。因為這是在一個單獨的執行緒中，
            # 它會安全地等待 DBManager 準備就緒，而不會阻塞主應用程式。
            db_client = get_client()

            log_source = record.name
            log_level = record.levelname

            # 我們需要手動格式化訊息，因為我們繞過了標準的 format() 流程
            message = logging.Formatter().format(record)

            db_client.add_system_log(log_source, log_level, message)
        except Exception as e:
            handler_log.error(f"日誌工作者執行緒無法將日誌寫入資料庫: {e}", exc_info=True)
        finally:
            log_queue.task_done()

# 啟動單一的背景工作者執行緒
# 將其設定為 daemon，這樣主程式退出時它也會自動退出
log_worker_thread = threading.Thread(target=_log_worker, daemon=True)
log_worker_thread.start()

class DatabaseLogHandler(logging.Handler):
    """
    一個自訂的非阻塞日誌處理器。
    它將日誌記錄放入一個佇列，由一個專門的背景執行緒來處理資料庫寫入，
    從而避免阻塞主應用程式的執行緒。
    """
    def __init__(self, source: str):
        super().__init__()
        self.source = source

    def emit(self, record: logging.LogRecord):
        """
        將日誌記錄放入佇列，立即返回。
        """
        if record.name == 'db_log_handler':
            return
        log_queue.put(record)

# 可以在應用程式關閉時呼叫此函式，以確保所有日誌都已寫入
def shutdown_log_worker():
    log_queue.put(None)
    log_worker_thread.join()
