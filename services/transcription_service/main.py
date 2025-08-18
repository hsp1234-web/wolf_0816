# services/transcription_service/main.py
# 此檔案是 Huey 消費者的進入點，負責執行背景任務。

# 我們需要匯入任務，以便消費者能夠識別並執行它們。
from .tasks import create_transcription_task
# 同時也需要匯入 huey 實例本身。
from ..huey_config import huey

# 這個服務不運行網頁伺服器，而是運行一個 Huey 消費者來處理背景任務。
# 若要運行此服務，您需要從專案的根目錄執行以下指令：
# python -m services.transcription_service.main
# (使用 -m 選項可以確保 Python 正確處理相對匯入)

if __name__ == '__main__':
    # 消費者是一個長時間運行的進程，它會輪詢佇列以尋找新任務。
    # `workers` 參數可以根據負載進行調整，決定同時處理多少個任務。
    # `loglevel=10` 對應於 DEBUG 級別，會提供詳細的輸出訊息。
    consumer = huey.create_consumer(workers=2, loglevel=10)
    print("正在啟動轉錄任務消費者...")
    print("服務已就緒，正在等待佇列中的新任務...")
    consumer.run()
