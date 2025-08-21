# services/dispatcher/main.py
import subprocess
import sys
import time
import argparse
import json
import logging
import os
from pathlib import Path
import redis

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)
log = logging.getLogger('Dispatcher')

# --- Redis 設定 ---
REDIS_SOCKET_PATH = os.getenv('REDIS_SOCKET_PATH', '/tmp/redis.sock')
TASK_QUEUE_KEY = "task_queue"

# --- 專案路徑設定 ---
# 此檔案位於 services/dispatcher/，所以根目錄是上上層
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
TASKS_DIR = ROOT_DIR / "src" / "tasks"

# --- 任務腳本設定 ---
# 將任務類型映射到其腳本和依賴
TASK_CONFIG = {
    "youtube_download": {
        "script": TASKS_DIR / "youtube_downloader.py",
        "dependencies": ["yt-dlp", "redis"]
    },
    "transcribe": {
        "script": TASKS_DIR / "transcribe_task.py",
        "dependencies": ["openai-whisper", "redis", "google-generativeai"]
    },
    "audio_to_report": {
        "script": TASKS_DIR / "audio_to_report_task.py",
        "dependencies": ["redis", "google-generativeai"]
    }
}

def ensure_venv_and_dependencies(task_type: str) -> Path:
    """
    確保指定任務類型的虛擬環境和依賴已準備就緒。
    如果環境不存在，則會「按需」建立並安裝。
    返回虛擬環境中的 Python 解譯器路徑。
    """
    if task_type not in TASK_CONFIG:
        raise ValueError(f"未知的任務類型: {task_type}")

    config = TASK_CONFIG[task_type]
    script_path = config["script"]
    dependencies = config["dependencies"]

    # 將虛擬環境建立在任務腳本所在目錄的旁邊，方便管理
    venv_path = script_path.parent / f".venv_{task_type}"

    # 根據作業系統決定 Python 解譯器路徑
    if sys.platform == "win32":
        python_executable = venv_path / "Scripts" / "python.exe"
    else:
        python_executable = venv_path / "bin" / "python"

    if not venv_path.exists():
        log.info(f"為任務 '{task_type}' 建立新的虛擬環境於: {venv_path}")
        try:
            # 1. 建立虛擬環境
            # 注意：這裡假設主環境中有 'uv'。在 Dockerfile 或部署腳本中應確保這一點。
            subprocess.run(["uv", "venv", str(venv_path), f"--python={sys.version_info.major}.{sys.version_info.minor}"], check=True, capture_output=True, text=True)

            # 2. 安裝依賴
            log.info(f"正在為 '{task_type}' 安裝依賴: {', '.join(dependencies)}")
            subprocess.run(
                ["uv", "pip", "install", "--python", str(python_executable)] + dependencies,
                check=True, capture_output=True, text=True
            )
            log.info(f"✅ 虛擬環境 '{task_type}' 已準備就緒。")
        except subprocess.CalledProcessError as e:
            log.error(f"❌ 建立虛擬環境或安裝依賴時失敗 for '{task_type}'.")
            log.error(f"   返回碼: {e.returncode}")
            log.error(f"   stdout: {e.stdout}")
            log.error(f"   stderr: {e.stderr}")
            raise
    else:
        log.debug(f"虛擬環境 for '{task_type}' 已存在，跳過建立。")

    return python_executable

def dispatch_task(task_data: dict):
    """
    根據任務資料分派並執行對應的任務腳本。
    """
    task_id = task_data.get("id")
    task_type = task_data.get("type")

    if not task_id or not task_type:
        log.error(f"收到的任務缺少 'id' 或 'type': {task_data}")
        return

    log.info(f"收到新任務，ID: {task_id}, 類型: {task_type}")

    try:
        # 1. 按需準備環境
        python_executable = ensure_venv_and_dependencies(task_type)

        # 2. 執行任務腳本
        script_path = TASK_CONFIG[task_type]["script"]
        command = [str(python_executable), str(script_path), "--task-id", task_id]

        log.info(f"執行指令: {' '.join(command)}")
        # 使用 Popen 以非阻塞方式執行，讓調度器可以繼續接收新任務
        process = subprocess.Popen(command, stdout=sys.stdout, stderr=sys.stderr)
        log.info(f"✅ 已為任務 {task_id} 啟動子程序，PID: {process.pid}")

    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as e:
        log.error(f"❌ 分派任務 {task_id} 失敗: {e}", exc_info=True)
        # TBD: 將失敗狀態寫回 Redis
    except Exception as e:
        log.error(f"❌ 分派任務 {task_id} 時發生未預期的錯誤: {e}", exc_info=True)
        # TBD: 將失敗狀態寫回 Redis


def main_loop():
    """
    主迴圈，持續從 Redis 獲取任務並分派。
    """
    log.info("---")
    log.info(f"🚀 中央調度器已啟動，正在透過 Unix Socket 連接至 Redis ({REDIS_SOCKET_PATH})...")
    log.info("---")

    # 在真實場景中，這裡應該有重試邏輯
    try:
        redis_client = redis.Redis(unix_socket_path=REDIS_SOCKET_PATH)
        # 測試連線
        redis_client.ping()
        log.info("✅ 成功連接至 Redis。")
    except redis.exceptions.ConnectionError as e:
        log.critical(f"❌ 無法透過 Unix Socket 連接至 Redis: {e}")
        log.critical(f"   請確保 Redis 伺服器正在運行，並且其 redis.conf 已配置好 socket 檔案路徑為: {REDIS_SOCKET_PATH}")
        sys.exit(1)

    log.info(f"🎧 開始監聽 Redis 列表 '{TASK_QUEUE_KEY}' 上的新任務...")
    while True:
        try:
            # blpop 是一個阻塞操作，它會等待直到有元素可供彈出
            # 返回的是一個元組 (key, value)
            _, task_json = redis_client.blpop(TASK_QUEUE_KEY)

            try:
                task_data = json.loads(task_json)
                dispatch_task(task_data)
            except json.JSONDecodeError:
                log.error(f"收到的任務不是有效的 JSON 格式: {task_json}")

        except redis.exceptions.ConnectionError as e:
            log.error(f"與 Redis 的連線中斷，將在 5 秒後重試... 錯誤: {e}")
            time.sleep(5)
        except Exception as e:
            log.error(f"主迴圈發生未預期的錯誤: {e}", exc_info=True)
            # 為避免因未知錯誤導致迴圈崩潰，短暫休眠後繼續
            time.sleep(1)

def run_test_dispatch():
    """一個用於快速測試分派功能的函式。"""
    log.info("--- 執行測試分派 ---")

    # 測試 1: YouTube 下載器
    log.info("--- 測試案例 1: YouTube 下載器 ---")
    mock_yt_task = {"id": "test-yt-001", "type": "youtube_download"}
    dispatch_task(mock_yt_task)

    # 等待一下，讓第一個任務的子程序有時間啟動
    time.sleep(5)

    # 測試 2: 語音轉報告 (Gemini)
    log.info("--- 測試案例 2: Gemini 音訊轉報告 ---")
    mock_gemini_task = {"id": "test-gemini-001", "type": "audio_to_report"}
    dispatch_task(mock_gemini_task)

    log.info("--- 測試分派完成 ---")
    # 給予子程序一些運行時間
    time.sleep(10)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="中央任務調度器。")
    parser.add_argument(
        "--test-dispatch",
        action="store_true",
        help="如果設置，則不監聽 Redis，而是執行一個預設的測試分派流程。"
    )
    args = parser.parse_args()

    # 在啟動調度器前，確保主環境有 uv
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        log.info("偵測到主環境中缺少 'uv'，正在嘗試安裝...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "uv"], check=True)
            log.info("✅ 'uv' 安裝成功。")
        except Exception as e:
            log.critical(f"❌ 無法自動安裝 'uv'，請手動安裝後再試。錯誤: {e}")
            sys.exit(1)

    if args.test_dispatch:
        run_test_dispatch()
    else:
        main_loop()
