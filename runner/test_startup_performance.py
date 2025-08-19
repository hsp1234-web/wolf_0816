import subprocess
import time
import sys
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime

# --- 設定 ---
ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "launcher_logs.db"
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
TEMP_BUILD_DIR = ROOT_DIR / "temp_build"
RUNNER_SCRIPT = ROOT_DIR / "runner" / "run_colab_main.py"
BUILD_SCRIPT = ROOT_DIR / "scripts" / "build_artifacts.sh"
TIMEOUT_SECONDS = 90  # 每個測試情境的最長等待時間

def get_startup_time_from_db(db_path: Path) -> float:
    """從 SQLite 日誌資料庫中計算啟動時間。"""
    if not db_path.is_file():
        raise FileNotFoundError("找不到日誌資料庫。")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 獲取第一條日誌的時間戳 (啟動開始)
        cursor.execute("SELECT timestamp FROM logs ORDER BY id ASC LIMIT 1")
        start_row = cursor.fetchone()
        if not start_row:
            raise ValueError("資料庫中沒有日誌。")
        start_time = datetime.fromisoformat(start_row[0])

        # 獲取伺服器就緒的時間戳
        cursor.execute("SELECT timestamp FROM logs WHERE message LIKE '%主應用程式已成功接管埠號並運行%' ORDER BY id ASC LIMIT 1")
        ready_row = cursor.fetchone()
        if not ready_row:
            raise ValueError("找不到伺服器就緒的日誌訊息。")
        ready_time = datetime.fromisoformat(ready_row[0])

        duration = (ready_time - start_time).total_seconds()
        return duration
    finally:
        conn.close()

def run_test_scenario(mode: str) -> float:
    """執行一個測試情境並回傳啟動時間。"""
    print(f"\n--- 執行測試情境: {mode} ---")

    # --- 準備環境 ---
    print("清理舊的日誌與成品...")
    if DB_PATH.exists():
        DB_PATH.unlink()

    if mode == 'no-prebake':
        if ARTIFACTS_DIR.exists():
            shutil.rmtree(ARTIFACTS_DIR)
        if TEMP_BUILD_DIR.exists():
            shutil.rmtree(TEMP_BUILD_DIR)
        print("已移除預烘烤成品。")

    elif mode == 'with-prebake':
        print("正在產生預烘烤成品...")
        build_process = subprocess.run([str(BUILD_SCRIPT)], capture_output=True, text=True)
        if build_process.returncode != 0:
            print("!!! 建立預烘烤成品失敗 !!!")
            print(build_process.stdout)
            print(build_process.stderr)
            return -1.0
        print("✅ 預烘烤成品已建立。")

    # --- 執行啟動器 ---
    print(f"正在以 '{mode}' 模式啟動應用程式...")
    start_time = time.monotonic()
    process = subprocess.Popen([sys.executable, str(RUNNER_SCRIPT)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')

    while True:
        elapsed = time.monotonic() - start_time
        if elapsed > TIMEOUT_SECONDS:
            print(f"!!! 測試超時 ({TIMEOUT_SECONDS}秒) !!!")
            print("--- Subprocess STDOUT ---")
            print(process.stdout.read())
            print("--- Subprocess STDERR ---")
            print(process.stderr.read())
            print("-------------------------")
            process.terminate()
            process.wait()
            return -1.0

        # 檢查資料庫中是否已有成功日誌
        if DB_PATH.exists():
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM logs WHERE message LIKE '%主應用程式已成功接管埠號並運行%'")
                if cursor.fetchone():
                    print("偵測到伺服器就緒信號，等待5秒以確保所有日誌寫入...")
                    time.sleep(5) # 給予一點額外時間確保日誌寫入
                    process.terminate()
                    process.wait()
                    break
                conn.close()
            except sqlite3.Error:
                # 資料庫可能正在寫入，稍後重試
                pass

        time.sleep(1)

    # --- 分析結果 ---
    print("正在從日誌資料庫分析啟動時間...")
    try:
        duration = get_startup_time_from_db(DB_PATH)
        print(f"✅ 情境 '{mode}' 的啟動時間為: {duration:.2f} 秒")
        return duration
    except Exception as e:
        print(f"!!! 分析日誌時發生錯誤: {e} !!!")
        return -1.0


def main():
    """主函數：執行所有測試並產生報告。"""
    print("="*50)
    print("      啟動效能對比測試      ")
    print("="*50)

    # 執行無預烘烤的對照組
    no_prebake_time = run_test_scenario('no-prebake')

    # 執行有預烘烤的實驗組
    with_prebake_time = run_test_scenario('with-prebake')

    # --- 產生報告 ---
    print("\n\n" + "="*50)
    print("         測試結果報告         ")
    print("="*50)

    if no_prebake_time > 0 and with_prebake_time > 0:
        savings = no_prebake_time - with_prebake_time
        savings_percent = (savings / no_prebake_time) * 100

        table = f"""
| 啟動模式 (Startup Mode) | 所需時間 (Time Taken) | 備註 (Notes) |
| :---------------------- | :-------------------- | :------------- |
| 標準安裝 (Normal Install) | {no_prebake_time:.2f} 秒              | 每次都需重新安裝依賴與建置前端 |
| 預烘烤策略 (Pre-baked)  | {with_prebake_time:.2f} 秒              | 直接使用預先打包的檔案，僅解壓縮 |
| **節省時間 (Time Saved)** | **{savings:.2f} 秒 (~{savings_percent:.0f}%)** |                |
"""
        print("\n請將以下 Markdown 表格複製到 plan.md 中：")
        print("\n" + table.strip())
    else:
        print("\n測試未能成功完成，無法產生比較報告。")
        print(f"標準安裝時間: {no_prebake_time:.2f}s, 預烘烤時間: {with_prebake_time:.2f}s")

if __name__ == "__main__":
    main()
