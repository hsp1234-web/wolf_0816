import os
import sys
import subprocess
import logging
import time
from pathlib import Path
from datetime import datetime
import json

# --- 設定區 ---
VENV_DIR = Path(__file__).parent / ".venv_transcription"
REQUIRED_PACKAGES = [
    "huey==2.5.0",
    "pytz==2024.1"
]
IDLE_TIMEOUT_SECONDS = 30  # 增加閒置時間以應對鏈式任務
LOOP_SLEEP_SECONDS = 2
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
    db_handler = DatabaseLogHandler(source='transcription_worker')
    logger.addHandler(db_handler)

    # 處理器 2: StreamHandler - 用於在本機主控台顯示日誌，方便偵錯
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = TaipeiTimeFormatter(
        '[%(asctime)s] [transcription_worker] [%(levelname)s] - %(message)s'
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
# 主要的佇列，用於此工作者執行的任務
transcription_huey = Huey('transcription')

# 代理佇列，用於將任務發送到 AI 報告工作者
ai_report_huey = Huey('ai_report')

@ai_report_huey.task()
def generate_ai_report(transcription: str, original_filename: str):
    # 這只是一個代理任務定義，真正的實作在 AI 報告工作者中
    # Huey 只需要知道任務簽名 (名稱和參數) 就可以將其加入佇列
    pass

@transcription_huey.task(retries=1, retry_delay=5)
def create_transcription_task(file_path: str, file_name: str):
    """
    模擬的轉錄任務
    """
    log.info(f"接收到新的轉錄任務，檔案：'{file_name}' (路徑: {file_path})")

    try:
        # 模擬耗時的轉錄過程
        log.info("正在模擬轉錄，將花費 10 秒...")
        time.sleep(10)
        mock_transcribed_text = f"這是 '{file_name}' 的模擬轉錄結果。時間: {datetime.now().isoformat()}"
        log.info(f"✅ 檔案 '{file_name}' 已成功模擬轉錄。")

        # 觸發 AI 報告生成任務
        log.info(f"準備觸發 AI 報告生成任務...")
        generate_ai_report(mock_transcribed_text, file_name)
        log.info("AI 報告任務已成功放入佇列。")

        return mock_transcribed_text

    except Exception as e:
        log.error(f"❌ 處理檔案 {file_name} 時發生未預期的錯誤: {e}")
        raise

# --- 4. 工作者主迴圈 ---
def run_worker():
    consumer = transcription_huey.create_consumer(workers=1, worker_type='thread')

    last_task_time = time.time()
    has_pending_tasks = (transcription_huey.pending_count() + transcription_huey.scheduled_count()) > 0

    @transcription_huey.signal(signals.SIGNAL_EXECUTING, signals.SIGNAL_COMPLETE, signals.SIGNAL_ERROR)
    def reset_idle_timer(signal, task, exc=None):
        nonlocal last_task_time
        last_task_time = time.time()
        if signal == signals.SIGNAL_EXECUTING:
            log.info(f"開始執行任務: {task.name} ({task.id})")
        elif signal == signals.SIGNAL_COMPLETE:
            log.info(f"任務 {task.name} ({task.id}) 處理完成。")
        elif signal == signals.SIGNAL_ERROR:
            log.warning(f"任務 {task.name} ({task.id}) 處理失敗。")

    log.info("轉錄工作者已啟動，開始監聽 'transcription' 佇列...")
    consumer.start()

    try:
        while True:
            pending = (transcription_huey.pending_count() + transcription_huey.scheduled_count()) > 0
            if not pending:
                if has_pending_tasks:
                    log.info("所有轉錄任務已處理完畢，啟動閒置計時器。")
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
        log.info("轉錄工作者已成功關閉。")

# --- 5. 主執行區塊 ---
if __name__ == "__main__":
    is_test_run = len(sys.argv) > 1 and sys.argv[1] == '--test'

    if is_test_run:
        log.info("在測試模式下執行：正在將測試任務加入佇列...")
        # 清空相關佇列以進行乾淨的測試
        transcription_huey.flush()
        ai_report_huey.flush()
        log.info("舊的 'transcription' 和 'ai_report' 佇列已清空。")

        create_transcription_task("/path/to/fake/testfile.mp3", "testfile.mp3")
        log.info("一個測試轉錄任務已成功加入佇列。")

    run_worker()
