# -*- coding: utf-8 -*-
import time
import subprocess
import sys
import logging
from pathlib import Path
import os
import signal
import platform

# --- 路徑設定 ---
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))

try:
    from db.client import get_client
except ImportError as e:
    # This should not happen if the path is correct
    print(f"FATAL: Could not import db.client. Make sure src/ is in PYTHONPATH. Error: {e}")
    sys.exit(1)

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('StartupManager')

# --- 工作者設定 (包含虛擬環境和依賴資訊) ---
WORKER_MAPPING = {
    "youtube_download": {
        "name": "YouTubeWorker",
        "script": "run_youtube_worker.py",
        "venv_dir": ROOT_DIR / ".venv-youtube",
        "req_file": ROOT_DIR / "requirements-youtube.txt"
    },
    "transcription": {
        "name": "TranscriptionWorker",
        "script": "run_transcription_worker.py",
        "venv_dir": ROOT_DIR / ".venv-transcription",
        "req_file": ROOT_DIR / "requirements-transcription.txt"
    },
    "ai_report": {
        "name": "AIReportWorker",
        "script": "run_ai_report_worker.py",
        "venv_dir": ROOT_DIR / ".venv-ai-report",
        "req_file": ROOT_DIR / "requirements-ai-report.txt"
    }
}

class StartupManager:
    """
    根據資料庫中的任務需求，動態地為其他工作者建立隔離的虛擬環境並啟動它們。
    """
    def __init__(self, poll_interval: int = 5):
        self.poll_interval = poll_interval
        self.active_workers = {}  # 儲存: {"worker_name": subprocess.Popen_object}
        self.db_client = None
        log.info("🚀 智慧啟動管理者已初始化 (虛擬環境隔離模式)。")

    def _get_venv_python_path(self, venv_dir: Path) -> Path:
        """根據作業系統取得虛擬環境中 Python 解譯器的正確路徑。"""
        if platform.system() == "Windows":
            return venv_dir / "Scripts" / "python.exe"
        else:
            return venv_dir / "bin" / "python"

    def run(self):
        """啟動主循環。"""
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        try:
            self.db_client = get_client()
            log.info("✅ 成功連接到資料庫。")
        except Exception as e:
            log.error(f"❌ 無法連接到資料庫，啟動失敗: {e}", exc_info=True)
            return

        log.info("👂 開始監聽資料庫中的待處理任務...")
        while True:
            try:
                self._check_for_new_tasks()
                self._monitor_active_workers()
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                log.info("收到手動中斷信號，準備關閉...")
                break
            except Exception as e:
                log.error(f"主循環發生未預期的錯誤: {e}", exc_info=True)
                time.sleep(self.poll_interval * 2)

    def _check_for_new_tasks(self):
        """檢查是否有待處理的任務，並根據需要啟動工作者。"""
        pending_tasks = self.db_client.get_tasks_by_status(TaskStatus.PENDING)
        if not pending_tasks:
            return

        unique_task_types = {task.task_type for task in pending_tasks}

        for task_type in unique_task_types:
            if task_type in WORKER_MAPPING:
                worker_info = WORKER_MAPPING[task_type]
                worker_name = worker_info["name"]

                if worker_name not in self.active_workers:
                    log.info(f"發現類型為 '{task_type}' 的新任務，需要啟動 '{worker_name}'。")
                    self._launch_worker(worker_info)

    def _prepare_venv(self, worker_info: dict) -> Path | None:
        """檢查、建立並準備一個工作者的虛擬環境。"""
        venv_dir = worker_info["venv_dir"]
        worker_name = worker_info["name"]
        req_file = worker_info["req_file"]
        venv_python = self._get_venv_python_path(venv_dir)

        if venv_dir.exists():
            log.info(f"✅ 發現 '{worker_name}' 的現有虛擬環境: {venv_dir}")
            return venv_python

        log.info(f"⚠️ 未找到 '{worker_name}' 的虛擬環境。將在 '{venv_dir}' 建立新環境。")
        try:
            # 1. 建立虛擬環境
            log.info(f"   - 步驟 1/2: 執行 `uv venv`...")
            subprocess.run(["uv", "venv", str(venv_dir)], check=True, capture_output=True, text=True)

            # 2. 安裝依賴
            log.info(f"   - 步驟 2/2: 在新環境中安裝依賴 from {req_file.name}...")
            if not req_file.exists():
                log.error(f"   ❌ 依賴檔案不存在: {req_file}")
                return None

            install_cmd = [str(venv_python), "-m", "pip", "install", "-r", str(req_file)]
            # 使用 uv 來加速 pip install
            # install_cmd = [str(venv_python), "-m", "uv", "pip", "install", "-r", str(req_file)]
            subprocess.run(install_cmd, check=True, capture_output=True, text=True)

            log.info(f"✅ '{worker_name}' 的虛擬環境已成功建立並準備就緒。")
            return venv_python

        except subprocess.CalledProcessError as e:
            log.error(f"❌ 為 '{worker_name}' 準備虛擬環境時失敗。")
            log.error(f"   - 指令: {' '.join(e.cmd)}")
            log.error(f"   - 輸出:\n{e.stdout}\n{e.stderr}")
            # 如果失敗，可以考慮刪除不完整的 venv 目錄
            # import shutil
            # if venv_dir.exists(): shutil.rmtree(venv_dir)
            return None
        except Exception as e:
            log.error(f"❌ 準備虛擬環境時發生未預期的錯誤: {e}", exc_info=True)
            return None

    def _launch_worker(self, worker_info: dict):
        """準備虛擬環境並啟動一個指定的工作者腳本。"""
        worker_name = worker_info["name"]
        script_path = ROOT_DIR / worker_info["script"]

        # 步驟 1: 準備虛擬環境
        venv_python = self._prepare_venv(worker_info)
        if not venv_python:
            log.error(f"由於虛擬環境準備失敗，無法啟動 '{worker_name}'。")
            return

        # 步驟 2: 啟動工作者
        if not script_path.exists():
            log.error(f"❌ 無法啟動 '{worker_name}'，因為找不到腳本: {script_path}")
            return

        log.info(f"🚀 正在從其專屬虛擬環境中啟動 {worker_name}...")
        try:
            process = subprocess.Popen(
                [str(venv_python), str(script_path)],
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            self.active_workers[worker_name] = process
            log.info(f"✅ {worker_name} 已成功啟動，PID: {process.pid}。")
        except Exception as e:
            log.error(f"❌ 啟動 {worker_name} 時發生嚴重錯誤: {e}", exc_info=True)

    def _monitor_active_workers(self):
        """監控已啟動的工作者程序，並清理已結束的程序。"""
        ended_workers = [name for name, proc in self.active_workers.items() if proc.poll() is not None]
        for name in ended_workers:
            log.info(f"監測到工作者 '{name}' (PID: {self.active_workers[name].pid}) 已結束。")
            del self.active_workers[name]

    def _handle_shutdown(self, signum, frame):
        """處理關閉信號，優雅地終止所有子程序。"""
        log.info(f"收到關閉信號 ({signal.Signals(signum).name})。正在終止所有由我啟動的工作者...")
        for name, process in self.active_workers.items():
            if process.poll() is None:
                log.info(f"  - 正在終止 {name} (PID: {process.pid})...")
                process.terminate()

        for name, process in self.active_workers.items():
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                log.warning(f"  - {name} 未能正常終止，強制擊殺。")
                process.kill()

        log.info("✅ 所有子工作者已關閉。啟動管理者即將退出。")
        sys.exit(0)

if __name__ == "__main__":
    # 確保 uv 已安裝
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        log.error("❌ 找不到 `uv` 指令。請先執行 `pip install uv`。")
        sys.exit(1)

    manager = StartupManager()
    manager.run()
