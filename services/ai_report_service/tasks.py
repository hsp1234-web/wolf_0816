# services/ai_report_service/tasks.py
import requests
import google.generativeai as genai
from pathlib import Path

from ..huey_config import huey
from .config import settings

# --- 服務的 URL ---
FILE_SERVICE_URL = "http://localhost:8001"
LOG_SERVICE_URL = "http://localhost:8003"

def log_message(level: str, message: str):
    """一個輔助函式，用於向日誌服務發送日誌。"""
    try:
        log_entry = {"service": "AIReportService", "level": level, "message": message}
        requests.post(f"{LOG_SERVICE_URL}/log", json=log_entry)
    except requests.exceptions.RequestException as e:
        print(f"嚴重錯誤：無法將日誌寫入日誌服務: {e}")

@huey.task()
def generate_ai_report(transcription: str, original_filename: str):
    """
    接收轉錄文字，使用 Gemini AI 產生報告，並將報告存到檔案服務。
    """
    log_message("INFO", f"接收到 AI 報告生成任務，針對檔案: {original_filename}")

    # --- 1. 設定並呼叫 Gemini API ---
    try:
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "default_key_if_not_set":
            raise ValueError("Gemini API 金鑰未設定。")

        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash') # 使用速度較快的 Flash 模型

        prompt = f"""
        你是一位專業的報告分析師。請根據以下提供的「語音轉錄逐字稿」，為我生成一份結構化的分析報告。
        報告應包含以下三個部分，並使用清晰的標題和項目符號：

        1.  **內容摘要**:
            用一段話簡潔地總結整篇內容的核心要點。

        2.  **關鍵主題**:
            以項目符號列出 3-5 個主要的討論主題或關鍵詞。

        3.  **建議標題**:
            根據內容，提供 3 個可作為參考的標題。

        ---
        語音轉錄逐字稿:
        ---
        {transcription}
        """

        log_message("INFO", f"正在向 Gemini API 發送請求以生成報告...")
        response = model.generate_content(prompt)
        report_text = response.text
        log_message("INFO", "已成功從 Gemini API 收到報告。")

    except Exception as e:
        log_message("ERROR", f"呼叫 Gemini API 時發生錯誤: {e}")
        return # API 呼叫失敗，終止任務

    # --- 2. 將報告儲存到檔案管理服務 ---
    try:
        # 產生報告的檔名
        report_filename = f"{Path(original_filename).stem}.report.txt"

        # 準備上傳的檔案內容
        files = {'file': (report_filename, report_text, 'text/plain')}

        upload_response = requests.post(f"{FILE_SERVICE_URL}/upload", files=files)
        upload_response.raise_for_status()

        file_info = upload_response.json()
        saved_report_path = file_info.get("path")

        log_message("INFO", f"AI 報告已成功儲存至檔案服務，路徑: {saved_report_path}")

    except Exception as e:
        log_message("ERROR", f"上傳 AI 報告至檔案服務時發生錯誤: {e}")
        return # 儲存失敗，終止任務

    # --- 3. 呼叫通知服務，廣播報告完成事件 ---
    try:
        notification_service_url = "http://localhost:8010/broadcast"
        notification_payload = {
            "event": "report_complete",
            "data": { "filename": original_filename, "report_filename": report_filename }
        }
        requests.post(notification_service_url, json=notification_payload)
        log_message("INFO", "已成功發送報告完成通知。")
    except requests.exceptions.RequestException as e:
        print(f"無法發送通知: {e}")


    return "AI 報告生成與儲存流程完成。"
