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

def run_hardware_monitor(stop_event: threading.Event, refresh_rate: float = 0.5):
    """
    在一個獨立的執行緒中運行，定期收集系統狀態並透過內部 API 回報。
    """
    log.info(f"🚀 硬體監控執行緒已啟動，更新頻率: {refresh_rate} 秒")

    # API URL 在執行緒啟動後動態建立
    api_url = None

    # 首次呼叫 psutil.cpu_percent() 以建立基準
    psutil.cpu_percent(interval=0.1)

    while not stop_event.is_set():
        try:
            # 如果 API URL 尚未設定，則嘗試從環境變數中獲取
            if not api_url:
                api_port = os.environ.get("API_PORT")
                if api_port:
                    api_url = f"http://127.0.0.1:{api_port}/api/internal/system_update"
                    log.info(f"硬體監控已設定 API URL: {api_url}")
                else:
                    # 如果 API_PORT 尚未就緒，則等待一下再重試
                    time.sleep(1)
                    continue

            cpu_usage = round(psutil.cpu_percent(interval=None), 1)
            ram_usage = round(psutil.virtual_memory().percent, 1)

            stats_payload = {
                "cpu_usage": cpu_usage,
                "ram_usage": ram_usage,
            }

            # 準備要發送給 API 閘道的完整訊息
            broadcast_message = {
                "type": "SYSTEM_STATS",
                "payload": stats_payload
            }

            # 透過 HTTP POST 請求將數據發送到 API 閘道的內部端點
            requests.post(api_url, json=broadcast_message, timeout=3)

            time.sleep(refresh_rate)

        except requests.exceptions.RequestException:
            # 如果 API Gateway 暫時無法連線，我們不將其視為致命錯誤，
            # 等待較長的時間後重試。
            time.sleep(5)
        except Exception as e:
            log.error(f"硬體監控執行緒發生未預期的錯誤: {e}", exc_info=True)
            time.sleep(5)

    log.info("🛑 硬體監控執行緒已接收到停止信號，即將退出。")
