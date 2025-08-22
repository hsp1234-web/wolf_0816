import time
from src.core.queue_config import huey
from .logging_worker import add_log

@huey.task()
def process_transcription(file_path: str, original_filename: str):
    """
    這是一個模擬的轉錄任務。
    在真實世界中，這裡會包含使用 Whisper 或其他 AI 模型進行轉錄的複雜邏輯。
    """
    worker_name = "transcription_worker"
    add_log(worker_name, "INFO", f"--- 開始處理任務: {original_filename} ---")
    add_log(worker_name, "DEBUG", f"  - 檔案路徑: {file_path}")

    # 模擬耗時的 AI 處理
    add_log(worker_name, "INFO", "正在進行模擬轉錄...")
    time.sleep(10) # 模擬 10 秒的處理時間

    result = f"這是 '{original_filename}' 的模擬轉錄結果。"
    add_log(worker_name, "SUCCESS", f"  - 轉錄完成: {result}")
    add_log(worker_name, "INFO", f"--- 任務完成: {original_filename} ---")
    return result

# 這部分不是必須的，因為我們將透過 huey_consumer.py 來啟動 worker。
# 但保留它可以方便單獨測試這個 worker。
if __name__ == '__main__':
    print("警告：此腳本不應直接執行。")
    print("請執行 `huey_consumer.py workers.transcription_worker.huey` 來啟動此工作者。")
