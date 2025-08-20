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

from datetime import datetime, timezone

def _log_worker():
    """
    一個在背景執行的工作者，從佇列中批次獲取日誌並透過 DBClient 發送。
    """
    db_client = get_client()
    batch = []
    max_batch_size = 50  # 每批最大日誌數量
    max_batch_interval = 2.0  # 秒，即使批次未滿，也最多等待這麼久

    while True:
        try:
            # 等待第一個日誌，設定超時
            record = log_queue.get(timeout=max_batch_interval)
            if record is None:  # 停止信號
                # 發送剩餘的批次
                if batch:
                    try:
                        db_client.add_system_logs_batch(batch)
                    except Exception as e:
                        handler_log.error(f"關閉前，最後一批日誌寫入失敗: {e}", exc_info=True)
                    finally:
                        for _ in range(len(batch)):
                            log_queue.task_done()
                        batch.clear()
                break

            # 格式化並加入批次
            log_source = record.name
            log_level = record.levelname
            message = logging.Formatter().format(record)
            # 我們在這裡產生時間戳，以確保批次中的時間戳是一致的
            timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc)
            batch.append((timestamp.isoformat(), log_source, log_level, message))

            # 如果批次已滿，立即發送
            if len(batch) >= max_batch_size:
                db_client.add_system_logs_batch(batch)
                for _ in range(len(batch)):
                    log_queue.task_done()
                batch.clear()

        except queue.Empty:
            # 如果佇列為空（等待超時），發送當前累積的批次
            if batch:
                try:
                    db_client.add_system_logs_batch(batch)
                except Exception as e:
                    handler_log.error(f"日誌工作者執行緒無法將批次日誌寫入資料庫: {e}", exc_info=True)
                finally:
                    for _ in range(len(batch)):
                        log_queue.task_done()
                    batch.clear()
        except Exception as e:
            handler_log.error(f"日誌工作者執行緒發生未預期錯誤: {e}", exc_info=True)
            # 如果發生未知錯誤，為避免資料遺失，我們嘗試逐一處理剩餘批次
            if batch:
                handler_log.warning("正在嘗試逐一儲存批次中的日誌...")
                for log_item in batch:
                    try:
                        # 轉換回單獨的參數
                        _, source, level, msg = log_item
                        db_client.add_system_log(source, level, msg)
                    except Exception as single_e:
                        handler_log.error(f"無法儲存單條日誌: {single_e}", exc_info=True)
                    finally:
                        log_queue.task_done()
                batch.clear()

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
