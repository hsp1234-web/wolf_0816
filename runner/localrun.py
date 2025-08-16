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


GLOBAL_TIMEOUT = 120
LOG_WATCHDOG_TIMEOUT = 20

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('LocalRun')

class LocalTestRunner:
    """
    負責在本地環境中完整執行端對端測試的類別。
    它會處理依賴安裝、服務啟動、日誌監控、測試執行和最終清理。
    """

    def __init__(self, mock_mode=True):
        self.mock_mode = mock_mode
        self.processes = []
        self.api_port = None
        self.api_url = None

    def _install_dependencies(self):
        """安裝專案依賴。"""
        log.info("📋 步驟 1/5: 檢查並安裝 Python 依賴...")
        req_file = ROOT_DIR / "requirements-server.txt"
        if not req_file.exists():
            log.warning(f"⚠️ 未找到依賴檔案 {req_file}，跳過安裝。")
            return True
        try:
            command = [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            log.info("✅ 依賴安裝完成。")
            return True
        except subprocess.CalledProcessError as e:
            log.error(f"❌ 依賴安裝失敗:\n{e.stderr}")
            return False

    def _initialize_db(self):
        """呼叫資料庫初始化函式，確保資料表已建立。"""
        log.info("🛠️ 步驟 2/5: 初始化資料庫...")
        try:
            initialize_database()
            log.info("✅ 資料庫初始化成功。")
            return True
        except Exception as e:
            log.error(f"❌ 資料庫初始化失敗: {e}", exc_info=True)
            return False

    def _start_services(self):
        """啟動所有必要的後端服務。"""
        log.info(f"🚀 步驟 3/5: 啟動後端服務 (模式: {'模擬' if self.mock_mode else '真實'})")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")

        db_manager_cmd = [sys.executable, str(ROOT_DIR / "src" / "db" / "manager.py")]
        db_proc = subprocess.Popen(
            db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', preexec_fn=os.setsid, env=env
        )
        self.processes.append(("db_manager", db_proc))
        log.info(f"  - DB Manager (PID: {db_proc.pid}) 啟動中...")

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
        return True

    def _run_backend_health_check(self) -> bool:
        """輪詢後端健康檢查端點，直到其就緒或超時。"""
        log.info(f"🩺 步驟 4/5: 執行後端健康檢查 (目標: {self.api_url}/api/health)...")
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
                log.warning(f"  - 健康檢查請求失敗: {e}。正在重試...")
            time.sleep(2)

        log.error("❌ 後端健康檢查超時。服務未能進入健康狀態。")
        return False

    def _run_full_integration_test(self):
        """執行完整的端對端整合測試。"""
        log.info("🧪 步驟 5/5: 執行整合測試...")
        # JULES'S FIX (2025-08-16): 改為自動探索 e2e_tests/ 目錄下的所有測試，
        # 而非指向單一檔案，這樣更具擴展性。
        test_directory = ROOT_DIR / "e2e_tests"
        if not test_directory.exists():
            log.error(f"❌ 測試目錄不存在: {test_directory}")
            return False

        test_cmd = [sys.executable, "-m", "pytest", str(test_directory)]
        env = {"TARGET_URL": self.api_url, "PYTHONPATH": str(ROOT_DIR / "src")}

        try:
            result = subprocess.run(
                test_cmd, capture_output=True, text=True, encoding='utf-8',
                timeout=90, env={**os.environ, **env}
            )
            if result.returncode == 0:
                log.info("✅ 整合測試成功！")
                print(result.stdout)
                return True
            else:
                log.error(f"❌ 整合測試失敗，返回碼: {result.returncode}")
                print("--- [Pytest STDOUT] ---")
                print(result.stdout)
                if result.stderr:
                    log.error("--- [Pytest STDERR] ---")
                    print(result.stderr)
                return False
        except subprocess.TimeoutExpired:
            log.error("❌ 整合測試執行超時！")
            return False
        except Exception:
            log.error("❌ 執行整合測試時發生未預期的錯誤:", exc_info=True)
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

    def run(self) -> bool:
        """
        執行整個測試流程，並返回最終結果。
        """
        overall_success = False
        try:
            if not self._install_dependencies(): return False
            if not self._initialize_db(): return False
            if not self._start_services(): return False
            if not self._run_backend_health_check(): return False
            if not self._run_full_integration_test(): return False

            log.info("✅ 系統已通過核心驗證，準備就緒。")
            overall_success = True
            return True

        except Exception as e:
            log.error(f"執行流程中發生未預期嚴重錯誤: {e}", exc_info=True)
            return False
        finally:
            self._shutdown()
            if not overall_success:
                log.error("🔥 啟動或驗證流程未成功完成。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="本地端對端測試啟動器 v2。")
    parser.add_argument(
        "--no-mock",
        action="store_false",
        dest="mock_mode",
        help="如果設置，則服務將以真實模式運行（而非模擬模式）。"
    )
    args = parser.parse_args()

    runner = LocalTestRunner(mock_mode=args.mock_mode)
    success = runner.run()

    if success:
        log.info("🎉 測試流程圓滿成功！")
        sys.exit(0)
    else:
        log.error("🔥 測試流程失敗。")
        sys.exit(1)
