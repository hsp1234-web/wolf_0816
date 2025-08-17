# runner/localrun.py
import subprocess
import sys
import time
import logging
import threading
import queue
import socket
import os
import argparse
import urllib.request
import json
from pathlib import Path

# --- 全域設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent

# 將 src 目錄加入 sys.path 以便匯入後端模組
sys.path.insert(0, str(ROOT_DIR / "src"))
from db.database import initialize_database


GLOBAL_TIMEOUT = 120  # 全局超時增加至 120 秒，以提供更寬裕的 E2E 測試時間
LOG_WATCHDOG_TIMEOUT = 10  # 使用者要求的 10 秒看門狗

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('LocalLauncher')

class LocalServerLauncher:
    """
    負責在本地環境中啟動和監控後端服務。
    它會處理依賴安裝、服務啟動、健康檢查和最終清理。
    """

    def __init__(self, mock_mode=True):
        self.mock_mode = mock_mode
        self.processes = []
        self.api_port = None
        self.api_url = None
        self.log_queue = queue.Queue()
        self.last_log_time = time.time()

    def _install_dependencies(self):
        """安裝專案依賴。"""
        log.info("📋 步驟 1/4: 檢查並安裝 Python 依賴...")
        req_file = ROOT_DIR / "requirements-server.txt"
        if not req_file.exists():
            log.warning(f"⚠️ 未找到依賴檔案 {req_file}，跳過安裝。")
            return True
        try:
            # JULES'S FIX (2025-08-16): 新增 Playwright 瀏覽器安裝步驟
            log.info("  - 安裝 Playwright 瀏覽器 (Chromium)...")
            subprocess.run(["npx", "playwright", "install", "chromium"], check=True, capture_output=True)
            log.info("  - 安裝 Python 套件...")
            command = [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            log.info("✅ 依賴安裝完成。")
            return True
        except subprocess.CalledProcessError as e:
            log.error(f"❌ 依賴安裝失敗:\n{e.stderr}")
            return False

    def _initialize_db(self):
        """呼叫資料庫初始化函式，確保資料表已建立。"""
        log.info("🛠️ 步驟 2/4: 初始化資料庫...")
        try:
            initialize_database()
            log.info("✅ 資料庫初始化成功。")
            return True
        except Exception as e:
            log.error(f"❌ 資料庫初始化失敗: {e}", exc_info=True)
            return False

    def _enqueue_output(self, stream, process_name):
        """從給定的流中讀取行並將其放入佇列。"""
        for line in iter(stream.readline, ''):
            self.log_queue.put((process_name, line.strip()))
        stream.close()

    def _start_services(self):
        """啟動所有必要的後端服務，並為其輸出建立監控執行緒。"""
        log.info(f"🚀 步驟 3/4: 啟動後端服務 (模式: {'模擬' if self.mock_mode else '真實'})")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")

        # --- 啟動 DB Manager ---
        db_manager_cmd = [sys.executable, str(ROOT_DIR / "src" / "db" / "manager.py")]
        db_proc = subprocess.Popen(
            db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', preexec_fn=os.setsid, env=env
        )
        self.processes.append(("db_manager", db_proc))
        log.info(f"  - DB Manager (PID: {db_proc.pid}) 啟動中...")

        # --- 啟動 API Server ---
        self.api_port = self._find_free_port()
        self.api_url = f"http://127.0.0.1:{self.api_port}"
        log.info(f"  - 為 API 伺服器指派埠號: {self.api_port}")
        api_server_cmd = [
            sys.executable, str(ROOT_DIR / "src" / "api" / "api_server.py"),
            "--port", str(self.api_port)
        ]
        if self.mock_mode:
            api_server_cmd.append("--mock")
        api_proc = subprocess.Popen(
            api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', preexec_fn=os.setsid, env=env
        )
        self.processes.append(("api_server", api_proc))
        log.info(f"  - API Server (PID: {api_proc.pid}) 啟動中...")

        # --- 為所有服務建立日誌監控 ---
        for name, proc in self.processes:
            thread = threading.Thread(target=self._enqueue_output, args=(proc.stdout, name), daemon=True)
            thread.start()

        return True

    def _run_backend_health_check(self) -> bool:
        """輪詢後端健康檢查端點，直到其就緒或超時。"""
        log.info(f"🩺 步驟 4/4: 執行後端健康檢查 (目標: {self.api_url}/api/health)...")
        start_time = time.time()
        health_check_timeout = 30

        while time.time() - start_time < health_check_timeout:
            try:
                with urllib.request.urlopen(f"{self.api_url}/api/health", timeout=5) as response:
                    if response.status == 200:
                        log.info("✅ 後端健康檢查成功。")
                        return True
                    else:
                        body = response.read().decode('utf-8', 'ignore')
                        log.warning(f"  - 健康檢查未通過，狀態碼: {response.status}。回應: {body}。正在重試...")
            except Exception as e:
                # 在健康檢查期間，我們預期會看到日誌輸出，所以重置看門狗計時器
                self.last_log_time = time.time()
                log.warning(f"  - 健康檢查請求失敗: {e}。正在重試...")
            time.sleep(2)

        log.error("❌ 後端健康檢查超時。服務未能進入健康狀態。")
        return False

    def _find_free_port(self) -> int:
        """尋找一個空閒的 TCP 埠號。"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def _shutdown(self):
        """使用 os.killpg 優雅地關閉所有子程序組。"""
        log.info("🛑 正在關閉所有服務...")
        for name, proc in reversed(self.processes):
            if proc.poll() is None:
                log.info(f"  - 正在終止 {name} (PID: {proc.pid})...")
                try:
                    os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGTERM)
                    proc.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    log.warning(f"  - {name} (PID: {proc.pid}) 未能正常終止，強制擊殺。")
                    os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGKILL)
        log.info("👋 所有服務已關閉。")

    def run(self):
        """
        執行整個伺服器啟動流程，並透過日誌看門狗和全局超時監控其運行狀態。
        """
        start_time = time.time()
        try:
            if not self._install_dependencies(): return
            if not self._initialize_db(): return
            if not self._start_services(): return
            if not self._run_backend_health_check(): return

            log.info("✅✅✅ 伺服器已成功啟動！ ✅✅✅")
            log.info(f"API 伺服器正在監聽: {self.api_url}")
            log.info(f"日誌看門狗已啟動 (超時: {LOG_WATCHDOG_TIMEOUT} 秒)。")
            log.info(f"全局超時已設定 (限制: {GLOBAL_TIMEOUT} 秒)。")
            log.info("現在可以開始進行手動測試。按下 Ctrl+C 來關閉所有服務。")

            while True:
                # 檢查全局超時
                if time.time() - start_time > GLOBAL_TIMEOUT:
                    log.error(f"🔥🔥🔥 全局超時！已達到 {GLOBAL_TIMEOUT} 秒的執行時間上限。")
                    raise RuntimeError("全局超時觸發。")

                # 檢查是否有子程序意外終止
                for name, proc in self.processes:
                    if proc.poll() is not None:
                        log.error(f"🔥 服務 '{name}' (PID: {proc.pid}) 已意外終止！")
                        raise RuntimeError(f"服務 {name} 異常退出。")

                # 處理日誌佇列
                had_output = False
                while not self.log_queue.empty():
                    name, line = self.log_queue.get_nowait()
                    print(f"[{name}] {line}")
                    had_output = True

                if had_output:
                    self.last_log_time = time.time()

                # 檢查看門狗是否超時
                if time.time() - self.last_log_time > LOG_WATCHDOG_TIMEOUT:
                    log.error(f"🔥🔥🔥 日誌看門狗超時！超過 {LOG_WATCHDOG_TIMEOUT} 秒無任何日誌輸出。")
                    raise RuntimeError("日誌看門狗觸發，系統可能已無回應。")

                time.sleep(0.5)

        except (KeyboardInterrupt, RuntimeError) as e:
            if isinstance(e, KeyboardInterrupt):
                log.info("\n🛑 偵測到使用者手動中斷 (Ctrl+C)。")
            else:
                log.error(f"\n🛑 執行期間發生錯誤: {e}")
        except Exception as e:
            log.error(f"執行流程中發生未預期嚴重錯誤: {e}", exc_info=True)
        finally:
            self._shutdown()
            log.info("🔥 啟動器已關閉。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="本地後端服務啟動器。")
    parser.add_argument(
        "--no-mock",
        action="store_false",
        dest="mock_mode",
        help="如果設置，則服務將以真實模式運行（而非模擬模式）。"
    )
    args = parser.parse_args()

    launcher = LocalServerLauncher(mock_mode=args.mock_mode)
    launcher.run()

    log.info("🎉 啟動器正常退出。")
    sys.exit(0)
