# run_youtube_worker.py
import time
import logging
from services.huey_config import huey
# 確保 tasks.py 被載入，讓 Huey 認識我們剛剛修改過的任務
from services.youtube_service import tasks

# --- 設定區 (可直接在此修改) ---
IDLE_TIMEOUT_SECONDS = 20 # 沒有任務後，等待 20 秒就自動關閉
LOOP_SLEEP_SECONDS = 2   # 每 2 秒檢查一次佇列
# --- 設定區結束 ---

# 設定簡單的日誌，方便觀察
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    """
    工作者的主要執行迴圈。
    """
    logging.info("YouTube 工作者已啟動，正在檢查任務...")
    last_task_time = time.time()

    while True:
        # 檢查是否超時
        if time.time() - last_task_time > IDLE_TIMEOUT_SECONDS:
            logging.info(f"超過 {IDLE_TIMEOUT_SECONDS} 秒沒有新任務，工作者將自動關閉。")
            break

        # 從佇列中嘗試取出一個任務，這是一個非阻塞操作
        task = huey.dequeue()

        if task:
            logging.info(f"收到新任務：{task.name}，正在執行...")
            # 執行任務
            try:
                # Huey 執行任務時，會自動處理我們設定的重試機制
                huey.execute(task)
                logging.info(f"任務 {task.name} 執行完畢。")
            except Exception as e:
                # 即使 Huey 有重試機制，如果最終還是失敗，我們在這裡記錄下來
                logging.error(f"任務 {task.name} 在所有重試後最終失敗：{e}")

            # 重置計時器
            last_task_time = time.time()
        else:
            # 佇列是空的
            logging.info(f"目前沒有任務，等待 {LOOP_SLEEP_SECONDS} 秒... (閒置倒數中)")
            time.sleep(LOOP_SLEEP_SECONDS)

    logging.info("YouTube 工作者已關閉。")

if __name__ == "__main__":
    main()
