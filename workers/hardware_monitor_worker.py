import sys
import os
import time
import psutil
import requests
import logging
from src.core.queue_config import huey
from huey import crontab

# 設定日誌
log = logging.getLogger('hardware_monitor_worker')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 從環境變數獲取 API 埠號，如果未設定則使用預設值 8000
API_PORT = os.environ.get("API_PORT", 8000)
API_URL = f"http://127.0.0.1:{API_PORT}/api/internal/system_update"

# 使用 Huey 的 decorator 來定義一個週期性任務
# crontab(minute='*/1') 表示每分鐘執行一次
# crontab(second='*/5') 表示每 5 秒執行一次
@huey.periodic_task(crontab(second='*/5'), retries=0)
def report_system_stats():
    """
    定期收集系統狀態 (CPU, RAM) 並透過內部 API 端點回報。
    """
    try:
        # 使用 psutil 獲取系統資訊
        cpu_usage = psutil.cpu_percent(interval=1)
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
        response.raise_for_status() # 如果請求失敗 (狀態碼非 2xx)，則會引發例外
        # log.info(f"成功回報系統狀態: CPU {cpu_usage}%, RAM {ram_usage}%")

    except requests.exceptions.RequestException as e:
        log.warning(f"無法回報系統狀態到 API 閘道: {e}")
    except Exception as e:
        log.error(f"收集系統狀態時發生未預期的錯誤: {e}", exc_info=True)
