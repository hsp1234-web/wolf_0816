# services/transcription_service/tasks.py
# 定義將由 huey 執行的任務

# 匯入我們在中央設定檔中定義的 Huey 實例
from ..huey_config import huey
import requests

# 匯入 AI 報告服務的任務，以便我們可以鏈式呼叫
from ..ai_report_service.tasks import generate_ai_report


# 這是一個 huey 任務。裝飾器 @huey.task() 會將其註冊到佇列中。
@huey.task()
def create_transcription_task(file_path: str, file_name: str):
    """
    這是一個非同步執行的轉錄任務。

    當 `transcription_service` 的消費者執行此任務時，它會：
    1. 呼叫 AI 模型服務來進行轉錄。
    2. 呼叫日誌服務來記錄結果。
    """
    print(f"背景任務已接收：開始處理檔案 '{file_path}' 的轉錄。")

    # --- 1. 呼叫 AI 本地模型服務 ---
    try:
        # AI 服務在 port 8002 上運行
        ai_service_url = "http://localhost:8002/transcribe"
        response = requests.post(ai_service_url, json={"file_path": file_path})
        response.raise_for_status()  # 如果回應狀態碼不是 2xx，則拋出異常

        transcription_result = response.json()
        transcribed_text = transcription_result.get("transcription", "轉錄失敗")

        log_message = f"檔案 '{file_name}' 轉錄成功。結果: {transcribed_text[:50]}..."
        print(log_message)

        # --- 轉錄成功後，觸發 AI 報告生成任務 ---
        try:
            print(f"準備觸發 AI 報告生成任務...")
            generate_ai_report(transcribed_text, file_name)
            print("AI 報告任務已成功放入佇列。")
        except Exception as e:
            # 如果觸發失敗，只記錄錯誤，不影響主任務的成功狀態
            error_log_message = f"觸發 AI 報告任務時失敗: {e}"
            print(error_log_message)
            # 可以在這裡決定是否要將這個觸發失敗的訊息也記錄到日誌服務
            # 為了簡單起見，暫時只在控制台輸出

    except requests.exceptions.RequestException as e:
        transcribed_text = f"無法呼叫 AI 模型服務: {e}"
        log_message = f"檔案 '{file_name}' 轉錄失敗。原因: {transcribed_text}"
        print(log_message)

    # --- 2. 呼叫日誌管理服務來記錄最終的轉錄結果 ---
    try:
        # 日誌服務在 port 8003 上運行
        log_service_url = "http://localhost:8003/log"
        log_entry = {
            "service": "TranscriptionService",
            "level": "INFO" if "成功" in log_message else "ERROR",
            "message": log_message
        }
        requests.post(log_service_url, json=log_entry)

    except requests.exceptions.RequestException as e:
        print(f"嚴重錯誤：無法將轉錄結果寫入日誌服務: {e}")

    # --- 3. 呼叫通知服務來廣播事件 ---
    if "成功" in log_message:
        try:
            notification_service_url = "http://localhost:8010/broadcast"
            notification_payload = {
                "event": "transcription_complete",
                "data": { "filename": file_name, "message": log_message }
            }
            requests.post(notification_service_url, json=notification_payload)
        except requests.exceptions.RequestException as e:
            print(f"無法發送通知: {e}")

    return log_message
