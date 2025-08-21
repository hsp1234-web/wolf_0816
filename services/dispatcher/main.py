# services/dispatcher/main.py
import subprocess
import sys
import time
import logging
from pathlib import Path

# TBD: Redis client and task fetching logic will go here.
# TBD: This will be the long-running service that listens for new tasks.

log = logging.getLogger('Dispatcher')

def setup_venv_and_run_task(task_type: str, task_id: str):
    """
    未來此函式將負責：
    1. 根據 task_type 找到對應的任務腳本 (例如 'youtube_download' -> 'tasks/youtube_downloader.py')。
    2. 檢查該任務的虛擬環境是否存在 (例如 'tasks/.venv_youtube')。
    3. 如果不存在，則使用 'uv venv' 和 'uv pip install' 建立環境並安裝依賴。
    4. 使用虛擬環境中的 Python 解譯器，透過 subprocess.Popen 執行任務腳本，並傳入 task_id。
    5. 監控子程序的執行狀況。
    """
    log.info(f"準備調度任務: type={task_type}, id={task_id}")
    # 實際的 venv 和 subprocess 邏輯將在此處實現
    pass

def main_loop():
    """
    主迴圈，持續從 Redis 獲取任務並分派。
    """
    log.info("🚀 中央調度器已啟動，等待新任務...")
    # while True:
    #     task = redis_client.blpop('task_queue')
    #     task_id = task['id']
    #     task_type = task['type']
    #     setup_venv_and_run_task(task_type, task_id)
    #     time.sleep(1)
    pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # main_loop()
    log.info("此為調度器 (Dispatcher) 的骨架檔案，尚未實現完整功能。")
