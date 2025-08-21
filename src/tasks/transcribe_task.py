# src/tasks/transcribe_task.py
import argparse
import json
import logging
import sys
import os
from pathlib import Path
import redis
import whisper
import google.generativeai as genai

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
log = logging.getLogger('TranscribeTask')

# --- Redis 設定 ---
REDIS_HOST = 'localhost'
REDIS_PORT = 6379

class MockRedis:
    """一個用於測試的模擬 Redis 客戶端。"""
    def __init__(self, *args, **kwargs):
        self._data = {}
        log.info("--- 使用模擬 Redis 客戶端 ---")

    def get(self, key):
        return self._data.get(key)

    def hset(self, key, mapping):
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
                "type": "transcribe",
                # 注意：在真實場景中，這個 audio_path 應該是 API 伺服器儲存上傳檔案後的位置
                "audio_path": "e2e_tests/fixtures/test.mp3",
                "model_size": "tiny",
                "language": "en",
                "status": "pending"
            }
            self.redis_client._data[f"task:{self.task_id}"] = json.dumps(mock_task_data)
        else:
            self.redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
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
        self.redis_client.hset(self.task_key, mapping=update_data)

def generate_report(transcript: str, use_mock: bool = False) -> str:
    """使用 Gemini API 從逐字稿生成報告。"""
    try:
        # GOOGLE_API_KEY 預期會被設定為環境變數
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            if use_mock:
                log.warning("在模擬模式下未找到 GOOGLE_API_KEY，將返回預設報告。")
                return "這是一份在模擬模式下生成的預設報告。"
            raise ValueError("環境變數 GOOGLE_API_KEY 未設定。")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')

        prompt = f"""
        請你扮演一位專業的會議記錄分析師。
        這是一份會議的語音逐字稿，請根據內容，整理成一份包含以下三個部分的結構化報告：

        1.  **摘要 (Summary)**:
            用一到兩句話簡潔地概括會議的核心主題與結論。

        2.  **重點 (Key Points)**:
            用項目符號條列出 3-5 個會議中最關鍵的討論點、決策或資訊。

        3.  **待辦事項 (Action Items)**:
            用項目符號條列出會議中明確提到的、需要後續執行的任務，並指明負責人（如果有的話）。

        如果逐字稿內容不足以產生某個部分，請在該部分標示「資訊不足」。

        ---
        **原始逐字稿:**
        {transcript}
        ---
        """

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        log.error(f"呼叫 Gemini API 時發生錯誤: {e}")
        # 返回一個錯誤訊息，而不是讓整個任務失敗
        return f"報告生成失敗: {e}"


def main(task_id: str, use_mock_redis: bool = False):
    """主執行函式。"""
    log.info(f"🚀 開始執行語音轉報告任務，ID: {task_id}")
    updater = TaskUpdater(task_id, use_mock=use_mock_redis)

    try:
        # 1. 從 Redis 獲取任務參數
        task_data = updater.get_task_data()
        audio_path = task_data.get('audio_path')
        model_size = task_data.get('model_size', 'tiny')
        language = task_data.get('language', 'en')

        if not audio_path or not Path(audio_path).exists():
            raise FileNotFoundError(f"音訊檔案不存在: {audio_path}")

        # 2. 階段一：語音轉文字
        updater.update_status("transcribing", {"message": f"正在使用 {model_size} 模型進行轉錄..."})
        model = whisper.load_model(model_size)
        result = model.transcribe(audio_path, language=language, fp16=False) # fp16=False 在 CPU 上更穩定
        transcript = result['text']
        log.info("轉錄完成。")
        updater.update_status("generating_report", {"transcript": transcript, "message": "轉錄完成，正在生成報告..."})

        # 3. 階段二：逐字稿轉報告
        report = generate_report(transcript, use_mock=use_mock_redis)
        log.info("報告生成完成。")

        # 4. 任務完成
        updater.update_status("completed", {
            "report": report,
            "message": "任務已成功完成。"
        })
        log.info(f"✅ 任務 {task_id} 成功完成！")

    except Exception as e:
        log.error(f"❌ 執行任務 {task_id} 時發生嚴重錯誤: {e}", exc_info=True)
        try:
            updater.update_status("failed", {"error_message": str(e)})
        except Exception as redis_e:
            log.error(f"!! 無法更新 Redis 中的失敗狀態: {redis_e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="一個獨立的語音轉報告任務腳本。")
    parser.add_argument("--task-id", required=True, help="要執行之任務的唯一 ID。")
    parser.add_argument("--mock-redis", action="store_true", help="如果設置，則使用模擬 Redis 客戶端進行測試。")
    args = parser.parse_args()

    main(args.task_id, args.mock_redis)
