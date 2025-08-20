import os
import sys
import subprocess
import logging
import time
from pathlib import Path
from datetime import datetime

# --- 設定區 ---
VENV_DIR = Path(__file__).parent / ".venv_ai_report"
REQUIRED_PACKAGES = [
    "huey==2.5.0",
    "pytz==2024.1"
]
IDLE_TIMEOUT_SECONDS = 20
LOOP_SLEEP_SECONDS = 2
REPORTS_DIR = Path("./ai_reports")
# --- 設定區結束 ---

def bootstrap_venv():
    """
    檢查是否在虛擬環境中，如果不是，則建立虛擬環境、安裝依賴，並在其中重新執行。
    """
    if sys.prefix == str(VENV_DIR.resolve()):
        return

    try:
        subprocess.run([sys.executable, "-m", "uv", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("錯誤：`uv` 未在主環境中找到或無法執行。請先透過 `pip install uv` 安裝。")
        sys.exit(1)

    if not VENV_DIR.exists():
        print(f"[{datetime.now().isoformat()}] 虛擬環境不存在，正在建立於: {VENV_DIR}")
        subprocess.run([sys.executable, "-m", "uv", "venv", str(VENV_DIR)], check=True)

    python_executable = VENV_DIR / "bin" / "python"

    print(f"[{datetime.now().isoformat()}] 正在安裝/驗證依賴 (已停用快取)...")
    subprocess.run([sys.executable, "-m", "uv", "pip", "install", "--no-cache-dir", *REQUIRED_PACKAGES, f"--python={python_executable}"], check=True)

    print(f"[{datetime.now().isoformat()}] 依賴安裝完成，正在虛擬環境中重新啟動腳本...")
    os.execv(python_executable, [python_executable, *sys.argv])

# --- 1. 執行引導程序 ---
bootstrap_venv()

# --- 2. 在 venv 中延遲匯入和設定 ---
import pytz
from huey import MemoryHuey as Huey, signals

# --- 日誌系統設定 ---
class TaipeiTimeFormatter(logging.Formatter):
    def converter(self, timestamp):
        dt = datetime.fromtimestamp(timestamp)
        return dt.astimezone(pytz.timezone('Asia/Taipei'))

    def formatTime(self, record, datefmt=None):
        dt = self.converter(record.created)
        if datefmt:
            s = dt.strftime(datefmt)
        else:
            s = dt.isoformat(timespec='milliseconds')
        return s

def setup_logging():
    """
    設定日誌系統，將日誌同時發送到資料庫（透過 DatabaseLogHandler）和主控台。
    """
    try:
        # 將 'src' 目錄新增到 Python 路徑中，以便找到 db 模組
        src_path = str(Path(__file__).resolve().parent / 'src')
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        from db.log_handler import DatabaseLogHandler
    except ImportError as e:
        # 如果匯入失敗，這是一個嚴重錯誤，因為日誌無法記錄到資料庫
        print(f"嚴重錯誤：無法匯入 DatabaseLogHandler。請確認 'src' 目錄路徑是否正確。錯誤: {e}", file=sys.stderr)
        sys.exit(1)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear() # 清除所有現有的處理器

    # 處理器 1: DatabaseLogHandler - 用於將日誌發送到中央資料庫
    db_handler = DatabaseLogHandler(source='ai_report_worker')
    logger.addHandler(db_handler)

    # 處理器 2: StreamHandler - 用於在本機主控台顯示日誌，方便偵錯
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = TaipeiTimeFormatter(
        '[%(asctime)s] [ai_report_worker] [%(levelname)s] - %(message)s'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 讓 huey 的日誌也透過我們設定的根記錄器進行處理
    huey_logger = logging.getLogger('huey')
    huey_logger.setLevel(logging.INFO)
    huey_logger.propagate = True # 設為 True，讓日誌傳遞到根記錄器

setup_logging()
log = logging.getLogger(__name__)

# --- 3. Huey 佇列與任務定義 ---
huey = Huey('ai_report')

@huey.task(retries=1, retry_delay=5)
def generate_ai_report(transcription: str, original_filename: str):
    """
    接收轉錄文字，模擬產生報告，並將報告存到本地檔案系統。
    """
    log.info(f"接收到 AI 報告生成任務，針對檔案: {original_filename}")

    try:
        # 模擬呼叫 AI API 的延遲
        log.info("正在模擬呼叫 AI API 生成報告，將花費 5 秒...")
        time.sleep(5)

        # 產生一個假的報告
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
        mock_report_text = f"""
# AI 模擬分析報告

**原始檔案**: {original_filename}
**報告生成時間**: {datetime.now().astimezone(pytz.timezone('Asia/Taipei')).isoformat()}

---

### **1. 內容摘要**
這是一份根據您的逐字稿自動生成的模擬報告。它總結了文本的核心思想，指出主要討論點是關於一個模擬的轉錄過程。

### **2. 關鍵主題**
- 模擬轉錄
- 工作者架構
- 任務佇列
- 異步處理

### **3. 建議標題**
- 模擬轉錄流程分析
- 關於 {original_filename} 的初步報告
- 系統自動生成摘要

---
*免責聲明：此報告由 AI 報告工作者模擬生成，僅供測試用途。*
"""
        log.info("已成功模擬生成 AI 分析報告。")

        # 將報告儲存到本地檔案
        REPORTS_DIR.mkdir(exist_ok=True)
        report_filename = f"{Path(original_filename).stem}.report.txt"
        report_path = REPORTS_DIR / report_filename

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(mock_report_text)

        log.info(f"✅ AI 報告已成功儲存至: {report_path}")
        return str(report_path)

    except Exception as e:
        log.error(f"❌ 產生或儲存 AI 報告時發生錯誤: {e}")
        raise

# --- 4. 工作者主迴圈 ---
def run_worker():
    consumer = huey.create_consumer(workers=1, worker_type='thread')

    last_task_time = time.time()
    has_pending_tasks = (huey.pending_count() + huey.scheduled_count()) > 0

    @huey.signal(signals.SIGNAL_EXECUTING, signals.SIGNAL_COMPLETE, signals.SIGNAL_ERROR)
    def reset_idle_timer(signal, task, exc=None):
        nonlocal last_task_time
        last_task_time = time.time()
        if signal == signals.SIGNAL_EXECUTING:
            log.info(f"開始執行任務: {task.name} ({task.id})")
        elif signal == signals.SIGNAL_COMPLETE:
            log.info(f"任務 {task.name} ({task.id}) 處理完成。")
        elif signal == signals.SIGNAL_ERROR:
            log.warning(f"任務 {task.name} ({task.id}) 處理失敗。")

    log.info("AI 報告工作者已啟動，開始監聽 'ai_report' 佇列...")
    consumer.start()

    try:
        while True:
            pending = (huey.pending_count() + huey.scheduled_count()) > 0
            if not pending:
                if has_pending_tasks:
                    log.info("所有 AI 報告任務已處理完畢，啟動閒置計時器。")
                    last_task_time = time.time()

                idle_time = time.time() - last_task_time
                if idle_time > IDLE_TIMEOUT_SECONDS:
                    log.info(f"工作者閒置超過 {IDLE_TIMEOUT_SECONDS} 秒，準備關閉...")
                    break

            has_pending_tasks = pending
            time.sleep(LOOP_SLEEP_SECONDS)

    except KeyboardInterrupt:
        log.info("收到手動中斷訊號，正在關閉...")
    finally:
        log.info("正在關閉消費者...")
        consumer.stop()
        log.info("AI 報告工作者已成功關閉。")

# --- 5. 主執行區塊 ---
if __name__ == "__main__":
    is_test_run = len(sys.argv) > 1 and sys.argv[1] == '--test'

    if is_test_run:
        log.info("在測試模式下執行：正在將測試任務加入佇列...")
        huey.flush()
        log.info("舊的 'ai_report' 佇列已清空。")

        test_transcription = "這是一段用於測試 AI 報告生成功能的模擬轉錄文字。"
        generate_ai_report(test_transcription, "test_audio.mp3")
        log.info("一個測試 AI 報告任務已成功加入佇列。")

    run_worker()
