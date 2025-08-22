import sys
import subprocess
import time
import requests
from pathlib import Path
import os

# --- 設定 ---
# 測試的總超時時間 (秒)
TOTAL_TIMEOUT = 60 # 首次運行需要安裝大量依賴，稍微延長超時
# API 閘道的預期 URL
API_GATEWAY_URL = "http://127.0.0.1:8000"
# 專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent
# 靜態網頁伺服器相關路徑
STATIC_SERVER_DIR = ROOT_DIR / "services" / "static_web_server"
STATIC_SERVER_MAIN_PY = STATIC_SERVER_DIR / "main.py"
STATIC_SERVER_REQS = STATIC_SERVER_DIR / "requirements.txt"

def install_orchestrator_deps():
    """安裝作為協調器的 `static_web_server` 本身的依賴。"""
    print("--- [步驟 1/3] 安裝協調器 (static_web_server) 的依賴 ---")
    if not STATIC_SERVER_REQS.exists():
        print(f"❌ 找不到依賴檔案: {STATIC_SERVER_REQS}")
        return False
    try:
        # 使用 uv 來安裝，與專案其他部分保持一致
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "uv"],
            check=True
        )
        subprocess.run(
            [sys.executable, "-m", "uv", "pip", "install", "-r", str(STATIC_SERVER_REQS)],
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ 協調器依賴安裝成功。")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 依賴安裝失敗。返回碼: {e.returncode}")
        print(f"   [stdout]:\n{e.stdout}")
        print(f"   [stderr]:\n{e.stderr}")
        return False

def run_test():
    print(f"--- [步驟 2/3] 啟動服務並在 {TOTAL_TIMEOUT} 秒內驗證 ---")
    server_proc = None
    start_time = time.monotonic()
    try:
        # 我們使用 `uvicorn` 指令來啟動，這是 FastAPI 應用的標準方式
        command = [
            sys.executable, "-m", "uvicorn",
            "main:app",
            "--host", "0.0.0.0",
            # 固定使用 8080 作為協調器埠號，避免與其他服務衝突
            "--port", "8080"
        ]
        print(f"啟動指令: {' '.join(command)}")

        server_proc = subprocess.Popen(
            command,
            cwd=STATIC_SERVER_DIR,
            stdout=sys.stdout,
            stderr=sys.stderr
        )

        print(f"協調器已作為背景程序啟動 (PID: {server_proc.pid})。")
        print(f"--- [步驟 3/3] 開始輪詢 API 閘道: {API_GATEWAY_URL} ---")

        while time.monotonic() - start_time < TOTAL_TIMEOUT:
            try:
                response = requests.get(API_GATEWAY_URL, timeout=2)
                if response.status_code == 200:
                    print(f"\n\n✅ [成功] API 閘道已成功回應！")
                    print(f"  - 回應內容: {response.json()}")
                    print(f"  - 總耗時: {time.monotonic() - start_time:.2f} 秒")
                    return True
            except requests.exceptions.ConnectionError:
                print(".", end="", flush=True)
                time.sleep(2)
            except Exception as e:
                print(f"\n❌ 測試期間發生非預期錯誤: {e}")
                return False

        print(f"\n❌ [失敗] 在 {TOTAL_TIMEOUT} 秒內，API 閘道未能成功啟動。")
        return False
    finally:
        if server_proc and server_proc.poll() is None:
            print("\n正在清理，終止伺服器子程序...")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()
            print("子程序已終止。")

def main():
    print("====== [後端整合測試] 開始 ======")
    if not install_orchestrator_deps():
        print("====== [後端整合測試] 失敗 (依賴安裝階段) ======")
        sys.exit(1)

    if run_test():
        print("====== [後端整合測試] 通過 ======")
        sys.exit(0)
    else:
        print("====== [後端整合測試] 失敗 (服務啟動階段) ======")
        sys.exit(1)

if __name__ == "__main__":
    main()
