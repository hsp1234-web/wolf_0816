# src/tasks/youtube_downloader.py
import argparse
import json
import logging
import sys
import os
from pathlib import Path
import redis
import yt_dlp

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
log = logging.getLogger('YouTubeDownloaderTask')

# --- Redis 設定 ---
REDIS_SOCKET_PATH = os.getenv('REDIS_SOCKET_PATH', '/tmp/redis.sock')

# --- 檔案儲存設定 ---
DOWNLOAD_DIR = Path.home() / "youtube_downloads"

class MockRedis:
    """一個用於測試的模擬 Redis 客戶端。"""
    def __init__(self, *args, **kwargs):
        self._data = {}
        log.info("--- 使用模擬 Redis 客戶端 ---")

    def get(self, key):
        return self._data.get(key)

    def hset(self, key, mapping):
        if key not in self._data:
            # 如果是第一次 hset，我們需要模擬 get 返回的 json 結構
            # 先將整個 mapping 作為一個 json 字串存儲
            self._data[key] = json.dumps(mapping)
        else:
            # 後續 hset，模擬更新 json 字串中的欄位
            current_data = json.loads(self._data.get(key, '{}'))
            current_data.update(mapping)
            self._data[key] = json.dumps(current_data)
        log.info(f"[MOCK REDIS] HSET on '{key}': {mapping}")
        log.info(f"[MOCK REDIS] Current state of '{key}': {self._data[key]}")

class TaskUpdater:
    """一個輔助類別，用於處理與 Redis 的所有通訊。"""
    def __init__(self, task_id, use_mock=False):
        self.task_id = task_id
        if use_mock:
            self.redis_client = MockRedis()
            # 為模擬任務預先填入資料
            mock_task_data = {
                "id": self.task_id,
                "type": "youtube_download",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", # Rick Astley - Never Gonna Give You Up
                "status": "pending"
            }
            self.redis_client._data[f"task:{self.task_id}"] = json.dumps(mock_task_data)
        else:
            self.redis_client = redis.Redis(unix_socket_path=REDIS_SOCKET_PATH, decode_responses=True)
        self.task_key = f"task:{self.task_id}"

    def get_task_data(self):
        """從 Redis 獲取完整的任務資料。"""
        task_data_json = self.redis_client.get(self.task_key)
        if not task_data_json:
            raise ValueError(f"在 Redis 中找不到任務 ID: {self.task_id}")
        return json.loads(task_data_json)

    def update_status(self, status: str, details: dict = None):
        """更新任務狀態和可選的詳細資訊。"""
        log.info(f"更新狀態: {status}, 細節: {details}")
        update_data = {"status": status}
        if details:
            update_data.update(details)

        # 使用 HSET 來更新多個欄位
        self.redis_client.hset(self.task_key, mapping=update_data)

    def progress_hook(self, d):
        """yt-dlp 的進度回調函式。"""
        if d['status'] == 'downloading':
            try:
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded_bytes = d.get('downloaded_bytes', 0)
                if total_bytes > 0:
                    percent = (downloaded_bytes / total_bytes) * 100
                    # 我們只更新進度，以避免覆蓋其他狀態
                    self.redis_client.hset(self.task_key, "progress", f"{percent:.2f}")
            except Exception as e:
                log.warning(f"進度回調中發生錯誤: {e}")

        elif d['status'] == 'finished':
            log.info("yt-dlp 回報下載完成，準備合併...")
            # 可以在此處設定一個「合併中」的狀態
            self.update_status("merging")


def main(task_id: str, use_mock_redis: bool = False):
    """主執行函式。"""
    log.info(f"🚀 開始執行 YouTube 下載任務，ID: {task_id}")
    updater = TaskUpdater(task_id, use_mock=use_mock_redis)

    try:
        # 1. 從 Redis 獲取任務參數
        task_data = updater.get_task_data()
        youtube_url = task_data.get('url')
        if not youtube_url:
            raise ValueError("任務資料中缺少 'url' 欄位。")

        # 2. 建立下載目錄
        DOWNLOAD_DIR.mkdir(exist_ok=True)

        # 3. 設定 yt-dlp 選項
        ydl_opts = {
            # 變更：請求一個不需要 ffmpeg 合併的、預先合併好的格式 (最高 720p 的 mp4)
            # 這足以驗證我們的下載邏輯
            'format': 'best[ext=mp4][height<=720]/best[ext=mp4]/best',
            'outtmpl': str(DOWNLOAD_DIR / '%(title)s [%(id)s].%(ext)s'),
            'progress_hooks': [updater.progress_hook],
            'quiet': True, # 關閉 yt-dlp 自己的日誌，由我們的回調函式處理
            'noplaylist': True,
        }

        # 4. 開始下載
        updater.update_status("downloading")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 獲取影片資訊以更新標題
            info_dict = ydl.extract_info(youtube_url, download=False)
            video_title = info_dict.get('title', 'Unknown Title')
            updater.update_status("downloading", {"video_title": video_title})

            # 正式下載
            ydl.download([youtube_url])

        # 5. 下載完成
        final_filepath = ydl.prepare_filename(info_dict)
        updater.update_status("completed", {
            "progress": "100.00",
            "result_path": final_filepath,
            "message": "下載並合併完成。"
        })
        log.info(f"✅ 任務 {task_id} 成功完成！檔案儲存於: {final_filepath}")

    except Exception as e:
        log.error(f"❌ 執行任務 {task_id} 時發生嚴重錯誤: {e}", exc_info=True)
        try:
            updater.update_status("failed", {"error_message": str(e)})
        except Exception as redis_e:
            log.error(f"!! 無法更新 Redis 中的失敗狀態: {redis_e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="一個獨立的 YouTube 下載任務腳本。")
    parser.add_argument("--task-id", required=True, help="要執行之任務的唯一 ID。")
    parser.add_argument("--mock-redis", action="store_true", help="如果設置，則使用模擬 Redis 客戶端進行測試。")
    args = parser.parse_args()

    main(args.task_id, args.mock_redis)
