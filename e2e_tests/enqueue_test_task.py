# enqueue_test_task.py
# 這是一個用來手動觸發 YouTube 下載任務的測試腳本。
from services.youtube_service.tasks import download_youtube_video
import sys

def main():
    """
    將指定的 YouTube URL 作為任務放入 Huey 佇列。
    """
    # 為了方便測試，我們使用一個預設的 URL
    # 這是一個很短的影片，可以加快測試速度
    default_url = "https://www.youtube.com/watch?v=LXb3EKWsInQ" # "A Short Video of a Cat"

    if len(sys.argv) > 1:
        youtube_url = sys.argv[1]
        print(f"使用您提供的 URL: {youtube_url}")
    else:
        youtube_url = default_url
        print(f"未提供 URL，使用預設的測試 URL: {youtube_url}")

    print(f"準備將下載任務放入佇列...")
    # 使用 .delay() 將任務異步放入 Huey 佇列
    download_youtube_video.delay(youtube_url)
    print("任務已成功放入佇列。現在可以啟動 `run_youtube_worker.py` 來處理它。")

if __name__ == "__main__":
    main()
