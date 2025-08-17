# -*- coding: utf-8 -*-
import subprocess
import sys
import time
import logging
import tarfile
import shutil
from pathlib import Path
import sysconfig

# --- 複製自 test_baseline.py 的部分 ---
import queue
import socket
import os
import urllib.request
import threading
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from db.database import initialize_database
# --- 複製結束 ---

# --- 全域設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent
CACHE_ARCHIVE = ROOT_DIR / "dependencies.tar.gz"
GLOBAL_TIMEOUT = 100

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('PrebakingTestRunner')


class TestRunner:
    """
    (預烘烤策略測試版本)
    此版本測試透過解壓縮預先建立的依賴快取包來啟動服務的效能。
    """
    def __init__(self):
        self.processes = []
        self.api_port = None
        self.api_url = None
        self.log_queue = queue.Queue()
        self.exit_code = 0
        self.timings = {}

    def _time_execution(self, step_name: str, func, *args, **kwargs) -> bool:
        log.info(f"--- 開始步驟: {step_name} ---")
        start_time = time.monotonic()
        try:
            result = func(*args, **kwargs)
            if not result:
                log.error(f"步驟 '{step_name}' 回傳失敗狀態。")
                return False
        except Exception as e:
            log.error(f"步驟 '{step_name}' 拋出未處理的異常: {e}", exc_info=True)
            return False

        end_time = time.monotonic()
        duration = end_time - start_time
        self.timings[step_name] = duration
        log.info(f"--- 結束步驟: {step_name} (耗時: {duration:.2f} 秒) ---")
        return True

    def _extract_dependencies(self):
        """解壓縮依賴快取包，取代安裝步驟。"""
        log.info("📋 步驟 1/6: 從快取解壓縮依賴...")
        if not CACHE_ARCHIVE.is_file():
            log.error(f"❌ 依賴快取包不存在: {CACHE_ARCHIVE}")
            log.error("請先執行 `python create_cache.py` 來產生快取包。")
            return False

        # 為了準確模擬，先清理舊的依賴目錄
        site_packages_path = Path(sysconfig.get_paths()["purelib"])
        node_modules_path = ROOT_DIR / "vue-app" / "node_modules"
        log.info(f"  - 正在清理舊目錄 (如果存在): {site_packages_path.name}, vue-app/node_modules")
        if site_packages_path.exists():
            shutil.rmtree(site_packages_path)
        if node_modules_path.exists():
            shutil.rmtree(node_modules_path)

        try:
            log.info(f"  - 正在解壓縮 {CACHE_ARCHIVE} ...")
            with tarfile.open(CACHE_ARCHIVE, "r:gz") as tar:
                # 我們需要解壓縮到正確的位置
                # site-packages 解壓縮到它的父目錄
                # node_modules 解壓縮到 vue-app/
                tar.extractall(path=site_packages_path.parent)
                tar.extractall(path=ROOT_DIR)

            log.info("✅ 依賴解壓縮完成。")
            return True
        except Exception as e:
            log.error(f"❌ 解壓縮依賴時發生錯誤: {e}", exc_info=True)
            return False

    def _build_frontend(self):
        """建置 Vue.js 前端應用程式。"""
        log.info("🏗️ 步驟 2/6: 建置 Vue.js 前端應用程式...")
        vue_app_dir = ROOT_DIR / "vue-app"
        try:
            # bun install 已被解壓縮步驟取代，但 build 仍是必要的
            log.info(f"  - 在 {vue_app_dir} 中執行 `bun run build`...")
            subprocess.run(["bun", "run", "build"], cwd=vue_app_dir, check=True, capture_output=True, text=True, timeout=120)
            log.info("✅ Vue.js 前端應用程式建置完成。")
            return True
        except Exception as e:
            log.error(f"❌ 前端建置失敗: {e}")
            return False

    # --- 後續步驟與 test_baseline.py 相同 ---
    def _initialize_db(self):
        log.info("🛠️ 步驟 3/6: 初始化資料庫...")
        try:
            initialize_database(); return True
        except Exception as e:
            log.error(f"❌ 資料庫初始化失敗: {e}", exc_info=True); return False

    def _enqueue_output(self, stream, process_name):
        for line in iter(stream.readline, ''): self.log_queue.put((process_name, line.strip()))
        stream.close()

    def _start_services(self):
        log.info("🚀 步驟 4/6: 啟動後端服務 (強制模擬模式)...")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR / "src") + os.pathsep + env.get("PYTHONPATH", "")
        env["API_MODE"] = "mock"
        db_manager_cmd = [sys.executable, str(ROOT_DIR / "src" / "db" / "manager.py")]
        db_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=env)
        self.processes.append(("db_manager", db_proc))
        time.sleep(2)
        self.api_port = self._find_free_port()
        self.api_url = f"http://127.0.0.1:{self.api_port}"
        api_server_cmd = [sys.executable, str(ROOT_DIR / "src" / "api" / "api_server.py"), "--port", str(self.api_port)]
        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=env)
        self.processes.append(("api_server", api_proc))
        for name, proc in self.processes:
            threading.Thread(target=self._enqueue_output, args=(proc.stdout, name), daemon=True).start()
        return True

    def _run_health_check(self) -> bool:
        log.info(f"🩺 步驟 5/6: 執行後端健康檢查 (目標: {self.api_url}/api/health)...")
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                with urllib.request.urlopen(f"{self.api_url}/api/health", timeout=2) as response:
                    if response.status == 200: log.info("✅ 後端健康檢查成功。"); return True
            except Exception: pass
            if any(p.poll() is not None for _, p in self.processes): return False
            time.sleep(1)
        return False

    def _run_tests(self):
        log.info("🧪 步驟 6/6: 執行 Playwright E2E 測試...")
        env = os.environ.copy(); env["API_URL"] = self.api_url
        pytest_cmd = [sys.executable, "-m", "pytest", str(ROOT_DIR / "e2e_tests")]
        result = subprocess.run(pytest_cmd, capture_output=True, text=True, encoding='utf-8', env=env, timeout=60)
        if result.returncode != 0:
            log.error(f"❌ E2E 測試失敗，返回碼: {result.returncode}\n{result.stdout}\n{result.stderr}")
            self.exit_code = 1
        else:
            log.info("✅ 所有 E2E 測試通過！")
        return self.exit_code == 0

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s: s.bind(("", 0)); return s.getsockname()[1]

    def _shutdown(self):
        log.info("🛑 正在關閉所有服務...")
        for _, proc in reversed(self.processes):
            if proc.poll() is None:
                try: os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGTERM)
                except Exception: pass
        time.sleep(1)

    def _print_logs(self):
        while not self.log_queue.empty(): print(f"[{self.log_queue.get_nowait()}]")

    def _print_timing_report(self, overall_start_time):
        log.info("="*50); log.info("📊 效能計時報告 (預烘烤策略測試)"); log.info("="*50)
        total_till_health_check = sum(d for s, d in self.timings.items() if s != "執行 E2E 測試")
        for step, duration in self.timings.items(): log.info(f"  - {step:<25}: {duration:.2f} 秒")
        log.info("-" * 50)
        log.info(f"  - {'服務就緒總時間 (到健康檢查通過)':<25}: {total_till_health_check:.2f} 秒")
        log.info(f"  - {'測試流程總耗時':<25}: {time.monotonic() - overall_start_time:.2f} 秒")
        log.info("="*50)

    def run(self):
        overall_start_time = time.monotonic()
        try:
            steps = [
                ("解壓縮依賴", self._extract_dependencies),
                ("建置前端", self._build_frontend),
                ("初始化資料庫", self._initialize_db),
                ("啟動服務", self._start_services),
                ("健康檢查", self._run_health_check),
                ("執行 E2E 測試", self._run_tests)
            ]
            for name, step_func in steps:
                if not self._time_execution(name, step_func):
                    self.exit_code = 1; break
        finally:
            self._shutdown()
            self._print_timing_report(overall_start_time)
            sys.exit(self.exit_code)

if __name__ == "__main__":
    runner = TestRunner()
    runner.run()
