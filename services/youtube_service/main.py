# services/youtube_service/main.py
# 此檔案是 Huey 消費者的進入點，負責執行背景的 YouTube 下載任務。

# 匯入任務，以便消費者能夠識別並執行它們。
from .tasks import download_youtube_video
# 匯入 huey 實例。
from ..huey_config import huey

# 若要運行此服務，您需要從專案的根目錄執行以下指令：
# python -m services.youtube_service.main

if __name__ == '__main__':
    # 建立並運行消費者
    consumer = huey.create_consumer(workers=2, loglevel=10)
    print("正在啟動 YouTube 下載任務消費者...")
    print("服務已就緒，正在等待佇列中的新任務...")
    consumer.run()
