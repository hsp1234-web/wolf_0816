import sys
import os
import time
import psutil
import requests
import logging
import threading

# 設定日誌
log = logging.getLogger('hardware_monitor_worker')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 從環境變數獲取 API 埠號，如果未設定則使用預設值 8000
API_PORT = os.environ.get("API_PORT", 8000)
API_URL = f"http://127.0.0.1:{API_PORT}/api/internal/system_update"

def run_hardware_monitor(stop_event: threading.Event, refresh_rate: float = 0.5):
    """
    在一個獨立的執行緒中運行，定期收集系統狀態並透過內部 API 回報。
    此函式取代了原有的 Huey 週期性任務，以支援高頻率（秒級以下）的更新。

    :param stop_event: 用於從外部優雅地停止執行緒的 threading.Event。
    :param refresh_rate: 監控數據的更新頻率（以秒為單位）。
    """
    log.info(f"🚀 硬體監控執行緒已啟動，更新頻率: {refresh_rate} 秒")

    # 確保在進入迴圈前，API 埠號已經被設定
    global API_PORT, API_URL
    if os.environ.get("API_PORT"):
        API_PORT = os.environ.get("API_PORT")
        API_URL = f"http://127.0.0.1:{API_PORT}/api/internal/system_update"
        log.info(f"硬體監控已更新 API URL: {API_URL}")
    else:
        log.warning("未在環境變數中找到 API_PORT，將使用預設值。")


    while not stop_event.is_set():
        try:
            # 使用 psutil 獲取系統資訊。
            # interval=None 表示進行非阻塞呼叫，與上次呼叫進行比較。
            cpu_usage = psutil.cpu_percent(interval=None)
            ram_usage = psutil.virtual_memory().percent

            stats_payload = {
                "cpu_usage": round(cpu_usage, 1),
                "ram_usage": round(ram_usage, 1),
            }

            # 準備要發送給 API 閘道的完整訊息
            broadcast_message = {
                "type": "SYSTEM_STATS",
                "payload": stats_payload
            }

            # 透過 HTTP POST 請求將數據發送到 API 閘道的內部端點
            response = requests.post(API_URL, json=broadcast_message, timeout=3)
            response.raise_for_status()

            # 等待下一個週期
            time.sleep(refresh_rate)

        except requests.exceptions.RequestException:
            # 如果 API Gateway 還沒準備好，或暫時無法連線，我們不將其視為致命錯誤，
            # 而是等待較長的時間後重試。
            # log.warning(f"硬體監控無法回報狀態 (可能是 API Gateway 尚未就緒): {e}")
            time.sleep(5)
        except Exception as e:
            log.error(f"硬體監控執行緒發生未預期的錯誤: {e}", exc_info=True)
            # 發生其他未知錯誤時，也等待較長時間
            time.sleep(5)

    log.info("🛑 硬體監控執行緒已接收到停止信號，即將退出。")
