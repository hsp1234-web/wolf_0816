# src/tasks/audio_to_report_task.py
import argparse
import json
import logging
import sys
import os
import time
from pathlib import Path
import redis
import google.generativeai as genai

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
log = logging.getLogger('AudioToReportTask')

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
            mock_task_data = {
                "id": self.task_id,
                "type": "audio_to_report",
                "audio_path": "e2e_tests/fixtures/test.mp3",
                "report_options": ["summary", "key_points"], # 模擬前端傳來的選項
                "status": "pending"
            }
            self.redis_client._data[f"task:{self.task_id}"] = json.dumps(mock_task_data)
        else:
            self.redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        self.task_key = f"task:{self.task_id}"

    def get_task_data(self):
        task_data_json = self.redis_client.get(self.task_key)
        if not task_data_json:
            raise ValueError(f"在 Redis 中找不到任務 ID: {self.task_id}")
        return json.loads(task_data_json)

    def update_status(self, status: str, details: dict = None):
        log.info(f"更新狀態: {status}, 細節: {details}")
        update_data = {"status": status}
        if details:
            update_data.update(details)
        self.redis_client.hset(self.task_key, mapping=update_data)

def build_prompt(report_options: list[str]) -> str:
    """根據前端傳來的選項動態建立提示詞。"""
    prompt = "請你扮演一位專業的會議記錄分析師。根據提供的音訊內容，整理成一份報告。\n報告必須包含以下部分：\n\n"
    if "summary" in report_options:
        prompt += "1. **摘要 (Summary)**: 用一到兩句話簡潔地概括音訊的核心主題與結論。\n"
    if "key_points" in report_options:
        prompt += "2. **重點 (Key Points)**: 用項目符號條列出 3-5 個最關鍵的討論點、決策或資訊。\n"
    if "action_items" in report_options:
        prompt += "3. **待辦事項 (Action Items)**: 用項目符號條列出明確提到的、需要後續執行的任務。\n"
    if "transcript" in report_options:
        prompt += "4. **詳細逐字稿 (Transcript)**: 提供完整的語音逐字稿。\n"

    prompt += "\n如果音訊內容不足以產生某個部分，請在該部分標示「資訊不足」。"
    return prompt

def main(task_id: str, use_mock_redis: bool = False):
    """主執行函式。"""
    log.info(f"🚀 開始執行音訊轉報告任務，ID: {task_id}")
    updater = TaskUpdater(task_id, use_mock=use_mock_redis)

    try:
        # 1. 從 Redis 獲取任務參數
        task_data = updater.get_task_data()
        audio_path_str = task_data.get('audio_path')
        report_options = task_data.get('report_options', ["summary"])

        if not audio_path_str or not Path(audio_path_str).exists():
            raise FileNotFoundError(f"音訊檔案不存在: {audio_path_str}")

        audio_path = Path(audio_path_str)

        # 2. 檢查 API Key
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            if use_mock_redis:
                log.warning("在模擬模式下未找到 GOOGLE_API_KEY，將返回預設報告並結束任務。")
                updater.update_status("completed", {
                    "report": "這是一份在模擬模式下生成的預設報告（因為缺少 API Key）。",
                    "message": "任務完成（模擬）。"
                })
                return
            raise ValueError("環境變數 GOOGLE_API_KEY 未設定。")

        # 3. 上傳檔案至 Gemini
        updater.update_status("uploading", {"message": f"正在上傳檔案: {audio_path.name}"})
        genai.configure(api_key=api_key)

        log.info(f"開始上傳檔案 '{audio_path.name}' 至 Gemini Files API...")
        audio_file = genai.upload_file(path=audio_path)
        log.info(f"檔案上傳成功。URI: {audio_file.uri}")

        # 等待檔案處理完成
        while audio_file.state.name == "PROCESSING":
            updater.update_status("processing_file", {"message": "Gemini 正在處理音訊檔案..."})
            time.sleep(2)
            audio_file = genai.get_file(name=audio_file.name)

        if audio_file.state.name == "FAILED":
            raise Exception(f"Gemini 檔案處理失敗: {audio_file.state}")

        # 4. 生成報告
        updater.update_status("generating_report", {"message": "正在生成報告..."})
        prompt = build_prompt(report_options)
        model = genai.GenerativeModel(model_name="models/gemini-1.5-flash") # 使用支援音訊的模型

        response = model.generate_content([prompt, audio_file])
        report = response.text
        log.info("報告生成完成。")

        # 5. 任務完成
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
    parser = argparse.ArgumentParser(description="一個獨立的、直接從音訊生成報告的 Gemini 任務腳本。")
    parser.add_argument("--task-id", required=True, help="要執行之任務的唯一 ID。")
    parser.add_argument("--mock-redis", action="store_true", help="如果設置，則使用模擬 Redis 客戶端進行測試。")
    args = parser.parse_args()

    main(args.task_id, args.mock_redis)
