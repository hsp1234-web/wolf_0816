from src.core.queue_config import huey
from src.core.log_manager import log_message as write_log_to_db

@huey.task()
def add_log(source: str, level: str, message: str):
    """
    這是一個專門用於日誌記錄的 Huey 任務。
    所有其他服務和工作者都應該呼叫這個任務來記錄日誌，
    而不是直接寫入資料庫或印出到控制台。
    這確保了日誌的中心化和有序性。
    """
    try:
        write_log_to_db(source, level, message)
    except Exception as e:
        # 如果日誌任務本身失敗，我們只能印出到 stderr
        # 這種情況很少見，但必須處理
        print(f"!!! CRITICAL: 日誌任務執行失敗: {e} !!!")
        print(f"    - 原始日誌: [{source}] [{level}] {message}")

# 同樣，這個檔案不應直接執行。
# huey_consumer.py 會導入它來識別任務。
if __name__ == '__main__':
    print("警告：此腳本不應直接執行。")
    print("請執行 `huey_consumer.py workers.logging_worker.huey` 來啟動此工作者。")
