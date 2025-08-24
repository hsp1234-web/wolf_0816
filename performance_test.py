# -*- coding: utf-8 -*-
"""
首次啟動性能 POC (概念驗證) 測試腳本

本腳本旨在精確測量在一個完全乾淨的環境中，從開始執行到後端伺服器
完全啟動並能回應請求所需的總時間。

此腳本會依序執行以下步驟：
1. 環境準備：刪除舊的產出物，確保「冷啟動」。
2. 烘烤流程：執行 `scripts/bake_dependencies.sh` 並計時。
3. 啟動與驗證：在背景啟動 `run.py`，並透過輪詢健康檢查端點來計時。
4. 結果報告與清理：輸出性能指標，並終止伺服器、清理產出物。
"""
import os
import subprocess
import time
import sys
import requests
import shutil

# --- 組態設定 ---
BAKE_SCRIPT_PATH = "scripts/bake_dependencies.sh"
RUN_PY_PATH = "run.py"
HEALTH_CHECK_URL = "http://127.0.0.1:8000/"
MAX_WAIT_SECONDS = 300  # 5 分鐘
POLL_INTERVAL_SECONDS = 1

# --- 腳本中使用的檔案與目錄 ---
DEPS_ARCHIVE = "dependencies.tar.gz"
BUILD_DIR = "_build"


def cleanup():
    """清理測試前後可能存在的產出物，確保環境乾淨。"""
    print("--- 正在執行環境清理 ---")
    try:
        if os.path.exists(DEPS_ARCHIVE):
            os.remove(DEPS_ARCHIVE)
            print(f"訊息：已刪除舊的 '{DEPS_ARCHIVE}'。")
        if os.path.exists(BUILD_DIR):
            shutil.rmtree(BUILD_DIR)
            print(f"訊息：已刪除舊的 '{BUILD_DIR}' 目錄。")
        print("✅ 環境清理完成。")
    except OSError as e:
        print(f"錯誤：清理檔案時發生錯誤: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """測試腳本主執行函數"""
    server_process = None
    total_start_time = time.monotonic()

    # --- 第一步：環境準備 ---
    cleanup()
    print("\n") # 增加間隔

    # --- 第二步：執行烘烤流程 ---
    print("--- [階段 1/2] 開始執行依賴烘烤流程 ---")
    bake_start_time = time.monotonic()

    try:
        # 執行烘烤腳本，並等待其完成
        # 使用 check=True 會在腳本返回非零退出碼時拋出例外
        subprocess.run(
            ["bash", BAKE_SCRIPT_PATH],
            check=True,
            capture_output=True,
            text=True
        )
    except FileNotFoundError:
        print(f"錯誤：找不到烘烤腳本 '{BAKE_SCRIPT_PATH}'。", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print("錯誤：依賴烘烤腳本執行失敗。", file=sys.stderr)
        print(f"返回碼: {e.returncode}", file=sys.stderr)
        print(f"標準輸出:\n{e.stdout}", file=sys.stderr)
        print(f"標準錯誤:\n{e.stderr}", file=sys.stderr)
        sys.exit(1)

    bake_end_time = time.monotonic()
    bake_duration = bake_end_time - bake_start_time
    print("✅ 依賴烘烤成功。")
    print("\n") # 增加間隔


    # --- 第三步：執行啟動與驗證流程 ---
    print("--- [階段 2/2] 開始執行應用程式啟動與驗證 ---")
    launch_start_time = bake_end_time # 啟動時間從烘烤結束後開始計算

    try:
        # 在背景啟動 run.py 伺服器
        server_process = subprocess.Popen(
            [sys.executable, RUN_PY_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print(f"訊息：應用程式 '{RUN_PY_PATH}' 已在背景啟動 (PID: {server_process.pid})。")
        print(f"訊息：正在輪詢健康檢查端點 '{HEALTH_CHECK_URL}'...")

        # 進入輪詢迴圈
        while True:
            # 檢查是否超時
            if time.monotonic() - launch_start_time > MAX_WAIT_SECONDS:
                print(f"錯誤：等待伺服器啟動超過 {MAX_WAIT_SECONDS} 秒，測試失敗。", file=sys.stderr)
                # 終止伺服器並以失敗碼退出
                server_process.terminate()
                server_process.wait()
                sys.exit(1)

            try:
                # 發送 HTTP GET 請求
                response = requests.get(HEALTH_CHECK_URL, timeout=1)
                if response.status_code == 200:
                    print("✅ 健康檢查成功 (HTTP 200 OK)，伺服器已可用！")
                    break  # 成功，跳出迴圈
            except requests.ConnectionError:
                # 連線失敗是預期中的，繼續等待
                pass
            except requests.Timeout:
                # 請求超時也是預期中的
                pass

            # 等待一秒後重試
            time.sleep(POLL_INTERVAL_SECONDS)

    except FileNotFoundError:
        print(f"錯誤：找不到啟動腳本 '{RUN_PY_PATH}'。", file=sys.stderr)
        if server_process:
            server_process.terminate()
        sys.exit(1)
    except Exception as e:
        print(f"錯誤：啟動或驗證過程中發生未預期錯誤: {e}", file=sys.stderr)
        if server_process:
            server_process.terminate()
        sys.exit(1)

    service_ready_time = time.monotonic()

    # --- 第四步：結果報告與清理 ---
    print("\n--- 測試完成，正在產生報告與清理 ---")

    # 終止伺服器
    if server_process:
        server_process.terminate()
        # 等待程序確實終止
        try:
            server_process.wait(timeout=5)
            print(f"訊息：背景伺服器 (PID: {server_process.pid}) 已成功終止。")
        except subprocess.TimeoutExpired:
            print(f"警告：終止伺服器 (PID: {server_process.pid}) 超時，可能需要手動清理。", file=sys.stderr)
            server_process.kill()

    # 計算各項指標
    launch_duration = service_ready_time - launch_start_time
    total_duration = service_ready_time - total_start_time

    # 輸出最終報告
    print("\n" + "="*50)
    print("  首次啟動性能 POC 測試結果報告")
    print("="*50)
    print(f"  - 烘烤耗時 (Baking Time)   : {bake_duration:.2f} 秒")
    print(f"  - 啟動耗時 (Launch Time)    : {launch_duration:.2f} 秒")
    print(f"  - 首次啟動總耗時 (Total)  : {total_duration:.2f} 秒")
    print("="*50 + "\n")

    # 最後再清理一次，刪除本次測試產生的壓縮檔
    cleanup()

if __name__ == "__main__":
    main()
