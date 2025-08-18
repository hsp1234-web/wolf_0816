# services/youtube_service/tasks.py
import yt_dlp
import requests
import tempfile
import os
from pathlib import Path

from ..huey_config import huey
# 匯入轉錄服務的任務，以便我們可以鏈式呼叫
from ..transcription_service.tasks import create_transcription_task

# --- 服務的 URL ---
FILE_SERVICE_URL = "http://localhost:8001"
LOG_SERVICE_URL = "http://localhost:8003"

def log_message(level: str, message: str):
    """一個輔助函式，用於向日誌服務發送日誌。"""
    try:
        log_entry = {"service": "YouTubeService", "level": level, "message": message}
        requests.post(f"{LOG_SERVICE_URL}/log", json=log_entry)
    except requests.exceptions.RequestException as e:
        print(f"嚴重錯誤：無法將日誌寫入日誌服務: {e}")

@huey.task(retries=3, retry_delay=30)
def download_youtube_video(youtube_url: str):
    """
    從 YouTube 下載音訊，存到檔案服務，然後觸發轉錄任務。
    """
    log_message("INFO", f"接收到新的 YouTube 下載任務，URL: {youtube_url}")

    # 使用 tempfile 來建立一個暫存目錄，確保下載的檔案在處理完後會被清理
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # --- 1. 使用 yt-dlp 下載音訊 ---
        ydl_opts = {
            'format': 'bestaudio/best', # 選擇最佳音質的音訊
            'outtmpl': str(tmpdir_path / '%(title)s.%(ext)s'), # 輸出檔案範本
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(youtube_url, download=True)
                # yt-dlp 下載後會將檔名資訊寫入 info_dict
                original_filename = ydl.prepare_filename(info_dict)
                # 處理後的檔名 (例如 .mp3)
                processed_filename = Path(original_filename).with_suffix('.mp3')

            if not processed_filename.exists():
                raise FileNotFoundError("yt-dlp 未能成功產生音訊檔案。")

            log_message("INFO", f"影片 '{info_dict.get('title')}' 已成功下載為 MP3。")

        except Exception as e:
            log_message("ERROR", f"使用 yt-dlp 下載時發生錯誤: {e}")
            raise  # 下載失敗，重新引發異常以觸發 Huey 重試

        # --- 2. 將下載的檔案上傳到檔案管理服務 ---
        try:
            with open(processed_filename, 'rb') as f:
                files = {'file': (processed_filename.name, f, 'audio/mpeg')}
                upload_response = requests.post(f"{FILE_SERVICE_URL}/upload", files=files)
                upload_response.raise_for_status()

                file_info = upload_response.json()
                saved_file_path = file_info.get("path")
                if not saved_file_path:
                    raise Exception("檔案服務未回傳儲存路徑。")

                log_message("INFO", f"下載的檔案已成功上傳至檔案服務，路徑: {saved_file_path}")

        except Exception as e:
            log_message("ERROR", f"上傳檔案至檔案服務時發生錯誤: {e}")
            raise  # 上傳失敗，重新引發異常以觸發 Huey 重試

        # --- 3. 觸發轉錄任務 ---
        try:
            log_message("INFO", f"準備觸發轉錄任務，檔案路徑: {saved_file_path}")
            create_transcription_task(saved_file_path, processed_filename.name)
            log_message("INFO", "轉錄任務已成功放入佇列。")
        except Exception as e:
            log_message("ERROR", f"觸發轉錄任務時發生錯誤: {e}")
            raise  # 觸發失敗，重新引發異常以觸發 Huey 重試

    return "YouTube 下載與轉錄觸發流程完成。"
