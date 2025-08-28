import subprocess
import sys
import os
import signal
import time
from pathlib import Path
import threading

# 修正 Python 的導入路徑，以便能找到 'workers' 模組
project_root_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root_path))

from workers.hardware_monitor_worker import run_hardware_monitor

# 全域變數
processes = [] # 追蹤子進程
threads = [] # 追蹤執行緒
stop_app = threading.Event() # 用於優雅關閉的信號
API_SERVER_PORT = 8000 # 與 Colabpro.py 中的設定保持一致

def log(message):
    """簡單的日誌函式，將輸出到 stderr，避免干擾 stdout 的埠號回報。"""
    print(f"[run_services] {message}", file=sys.stderr, flush=True)

def stream_output(process, name):
    """讀取並記錄子進程的輸出。"""
    if not process or not process.stdout:
        return
    for line in iter(process.stdout.readline, ''):
        log(f"[{name}] {line.strip()}")

def cleanup(signum=None, frame=None):
    """清理函式，用於終止所有子進程和執行緒。"""
    log("收到關閉信號，正在終止所有服務...")
    stop_app.set() # 通知所有執行緒停止

    # 終止子進程
    for p in reversed(processes):
        if p.poll() is None:
            log(f"正在終止 PID: {p.pid}...")
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    time.sleep(2)
    for p in reversed(processes):
        if p.poll() is None:
            log(f"強制終止 PID: {p.pid}...")
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass

    # 等待執行緒結束
    log("正在等待所有執行緒結束...")
    for t in threads:
        t.join(timeout=5)

    log("所有服務已清理。")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    project_root = Path(__file__).parent.parent

    try:
        # --- 步驟 1: 啟動資料庫管理器 ---
        log("步驟 1: 啟動資料庫管理器...")
        db_manager_command = [sys.executable, str(project_root / "src/db/manager.py")]
        db_proc = subprocess.Popen(
            db_manager_command, text=True, encoding='utf-8',
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            preexec_fn=os.setsid
        )
        processes.append(db_proc)
        threading.Thread(target=stream_output, args=(db_proc, "DB_Manager"), daemon=True).start()
        log("等待資料庫管理器初始化...")
        time.sleep(5)
        if db_proc.poll() is not None:
            raise RuntimeError(f"資料庫管理器啟動失敗，返回碼: {db_proc.poll()}")
        log("資料庫管理器已在背景啟動。")

        # --- 步驟 2: 啟動統一 API 伺服器 ---
        log(f"步驟 2: 啟動統一 API 伺服器於埠號 {API_SERVER_PORT}...")
        server_env = os.environ.copy()
        if os.environ.get("LIGHT_MODE", "0") == "1":
            server_env["LIGHT_MODE"] = "1"
            log("輕量測試模式已啟用。")
        static_dir_path = project_root / "vue-app" / "dist"
        server_env["STATIC_DIR"] = str(static_dir_path.resolve())
        server_command = [
            sys.executable, "-m", "uvicorn", "src.api_server:app",
            "--host", "0.0.0.0", "--port", str(API_SERVER_PORT)
        ]
        api_proc = subprocess.Popen(
            server_command, text=True, encoding='utf-8', env=server_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
            cwd=project_root
        )
        processes.append(api_proc)
        threading.Thread(target=stream_output, args=(api_proc, "API_Server"), daemon=True).start()
        time.sleep(5) # 等待伺服器綁定埠號
        if api_proc.poll() is not None:
            raise RuntimeError(f"API 伺服器啟動失敗，返回碼: {api_proc.poll()}")
        log(f"API 伺服器已在 http://127.0.0.1:{API_SERVER_PORT} 啟動")
        print(f"APP_PORT:{API_SERVER_PORT}", flush=True)

        # --- 步驟 3: 啟動背景工作者 ---
        log("步驟 3: 啟動背景工作者...")
        worker_command = [sys.executable, str(project_root / "workers/transcription_worker.py")]
        worker_proc = subprocess.Popen(
            worker_command, text=True, encoding='utf-8',
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            preexec_fn=os.setsid
        )
        processes.append(worker_proc)
        threading.Thread(target=stream_output, args=(worker_proc, "Worker"), daemon=True).start()
        log("轉錄工作者已在背景啟動。")

        # --- 步驟 4: 啟動硬體監控執行緒 ---
        log("步驟 4: 啟動硬體監控...")
        os.environ['API_PORT'] = str(API_SERVER_PORT) # 將 API 埠號傳遞給監控器
        monitor_thread = threading.Thread(target=run_hardware_monitor, args=(stop_app,), daemon=True)
        monitor_thread.start()
        threads.append(monitor_thread)
        log("硬體監控已在背景執行緒中啟動。")

        # --- 步驟 5: 等待主服務 (API Server) 結束 ---
        log("所有服務已啟動。監控 API 伺服器狀態...")
        api_proc.wait()
        log("API 伺服器已停止。")

    except Exception as e:
        log(f"發生致命錯誤: {e}")
    finally:
        cleanup()

if __name__ == "__main__":
    main()
