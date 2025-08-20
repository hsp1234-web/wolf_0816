import os
import sys
import subprocess
import logging
import time
from pathlib import Path
from datetime import datetime
import json

# --- 設定區 ---
VENV_DIR = Path(__file__).parent / ".venv_youtube"
REQUIRED_PACKAGES = [
    "huey==2.5.0",
    "yt-dlp==2023.12.30",
    "pytz==2024.1"
]
IDLE_TIMEOUT_SECONDS = 20
LOOP_SLEEP_SECONDS = 2
# --- 設定區結束 ---

def bootstrap_venv():
    """
    檢查是否在虛擬環境中，如果不是，則建立虛擬環境、安裝依賴，並在其中重新執行。
    """
    if sys.prefix == str(VENV_DIR.resolve()):
        # 已經在虛擬環境中，無需任何操作
        return

    # 檢查主系統中是否有 uv
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
# 這是腳本的第一個實際操作。如果不在 venv 中，它會安裝依賴並重新啟動。
# 如果在 venv 中，它會直接返回。
bootstrap_venv()

# --- 2. 在 venv 中延遲匯入和設定 ---
# 只有在 venv 啟動並確認依賴存在後，才匯入這些模組
import pytz
from huey import MemoryHuey as Huey, signals
import yt_dlp

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
    # 'youtube_worker' 將作為日誌來源的標識符
    db_handler = DatabaseLogHandler(source='youtube_worker')
    logger.addHandler(db_handler)

    # 處理器 2: StreamHandler - 用於在本機主控台顯示日誌，方便偵錯
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = TaipeiTimeFormatter(
        '[%(asctime)s] [youtube_worker] [%(levelname)s] - %(message)s'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 讓 huey 的日誌也透過我們設定的根記錄器進行處理
    huey_logger = logging.getLogger('huey')
    huey_logger.setLevel(logging.INFO)
    huey_logger.propagate = True # 設為 True，讓日誌傳遞到根記錄器

# 執行日誌設定
setup_logging()
log = logging.getLogger(__name__)

# --- 3. Huey 佇列與任務定義 ---
huey = Huey('youtube_downloader')

@huey.task(retries=2, retry_delay=10)
def download_youtube_video(youtube_url: str):
    log.info(f"接收到新的 YouTube 下載任務，URL: {youtube_url}")

    output_dir = Path("./youtube_downloads")
    output_dir.mkdir(exist_ok=True)

    ydl_opts = {
        'format': 'bestaudio/best',
        # JULES'S FIX (2025-08-18): 檔名淨化
        # 原始的 '%(title)s' 模板會因包含特殊字元而導致後續的檔案處理工具失敗。
        # 改為僅使用影片 ID 作為檔名，這是一個檔案系統安全的唯一識別碼。
        # 完整的標題資訊仍然會被儲存在資料庫中。
        'outtmpl': str(output_dir / '%(id)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'logger': log,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(youtube_url, download=True)
            log.info(f"✅ 影片 '{info_dict.get('title')}' 已成功下載為 MP3。")
            return f"下載成功: {ydl.prepare_filename(info_dict)}"
    except yt_dlp.utils.DownloadError as e:
        log.error(f"❌ 下載失敗，URL: {youtube_url}。錯誤訊息: {e}")
        raise
    except Exception as e:
        log.error(f"❌ 處理 URL {youtube_url} 時發生未預期的錯誤: {e}")
        raise


# --- 4. 工作者主迴圈 ---
def run_worker():
    consumer = huey.create_consumer(workers=1, worker_type='thread')

    last_task_time = time.time()
    initial_tasks_exist = (huey.pending_count() + huey.scheduled_count()) > 0
    has_pending_tasks = initial_tasks_exist

    # 當有任務開始執行時，重設閒置計時器
    @huey.signal(signals.SIGNAL_EXECUTING)
    def reset_idle_timer(signal, task):
        nonlocal last_task_time
        last_task_time = time.time()
        log.info(f"開始執行任務: {task.name} ({task.id})")

    # Huey 的消費者本身會記錄任務完成或失敗，此處不再重複
    @huey.signal(signals.SIGNAL_COMPLETE, signals.SIGNAL_ERROR)
    def update_last_task_time_on_finish(signal, task, exc=None):
        nonlocal last_task_time
        last_task_time = time.time()
        # 這裡的日誌是可選的，因為消費者已經會記錄
        if signal == signals.SIGNAL_COMPLETE:
            log.info(f"任務 {task.name} ({task.id}) 處理完成。")
        elif signal == signals.SIGNAL_ERROR:
            log.warning(f"任務 {task.name} ({task.id}) 處理失敗。")

    log.info("YouTube 工作者已啟動，開始監聽任務...")
    consumer.start()

    try:
        while True:
            if (huey.pending_count() + huey.scheduled_count()) == 0:
                if has_pending_tasks:
                    log.info("所有任務已處理完畢，啟動閒置計時器。")
                    last_task_time = time.time()
                    has_pending_tasks = False

                idle_time = time.time() - last_task_time
                if idle_time > IDLE_TIMEOUT_SECONDS:
                    log.info(f"工作者閒置超過 {IDLE_TIMEOUT_SECONDS} 秒，準備關閉...")
                    break
            else:
                has_pending_tasks = True

            time.sleep(LOOP_SLEEP_SECONDS)

    except KeyboardInterrupt:
        log.info("收到手動中斷訊號，正在關閉...")
    finally:
        log.info("正在關閉消費者...")
        consumer.stop()
        log.info("工作者已成功關閉。")

# --- 5. 主執行區塊 ---
if __name__ == "__main__":
    is_test_run = len(sys.argv) > 1 and sys.argv[1] == '--test'

    if is_test_run:
        log.info("在測試模式下執行：正在將測試任務加入佇列...")
        huey.flush()
        log.info("舊的佇列已清空。")

        # 直接呼叫任務函式即可將其加入佇列
        download_youtube_video("https://youtube.com/shorts/KZgVxY9vFwg?si=AlA5duWlsK1IU1l6")
        download_youtube_video("http://invalid.url/this-will-fail")

        log.info("兩個測試任務已成功加入佇列。")

    run_worker()
