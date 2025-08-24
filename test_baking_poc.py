# -*- coding: utf-8 -*-
"""
端對端 (E2E) 驗證腳本 for 「預先烘烤依賴」 POC

此腳本的目標是自動化地驗證整個流程：
1. 清理舊的產物。
2. 執行烘烤腳本 `scripts/bake_dependencies.sh` 來產生 `dependencies.tar.gz`。
3. 在背景啟動 `run.py` 伺服器。
4. 發送一個 HTTP 請求到伺服器，驗證其是否成功啟動並回應。
5. 清理背景進程。
"""

import os
import subprocess
import time
import sys
import requests

def run_command(command, check=True):
    """一個輔助函數，用於執行命令並即時顯示其輸出。"""
    print(f"\n--- 執行指令: {' '.join(command)} ---")
    process = subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    # 顯示指令的輸出，方便偵錯
    if process.stdout:
        print(process.stdout)
    if process.stderr:
        print(process.stderr, file=sys.stderr)
    return process

def main():
    """主測試執行函數"""
    server_process = None
    try:
        # --- 步驟 1: 清理 ---
        print("--- 步驟 1/5: 清理舊的產物 ---")
        if os.path.exists("dependencies.tar.gz"):
            os.remove("dependencies.tar.gz")
            print("✅ 已刪除舊的 'dependencies.tar.gz'。")
        else:
            print("ℹ️ 無舊的 'dependencies.tar.gz' 需要清理。")

        # --- 步驟 2: 執行烘烤腳本 ---
        print("\n--- 步驟 2/5: 執行烘烤腳本 ---")
        run_command(["bash", "scripts/bake_dependencies.sh"])
        assert os.path.exists("dependencies.tar.gz"), "烘烤失敗：'dependencies.tar.gz' 未被建立。"
        print("✅ 烘烤腳本執行成功，產物已建立。")

        # --- 步驟 3: 啟動伺服器 ---
        print("\n--- 步驟 3/5: 在背景啟動應用程式伺服器 ---")
        # 使用 Popen 在背景啟動伺服器
        server_process = subprocess.Popen(
            [sys.executable, "run.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        print(f"✅ 伺服器程序已啟動，PID: {server_process.pid}。")

        # --- 步驟 4: 驗證伺服器 ---
        print("\n--- 步驟 4/5: 驗證伺服器是否正常回應 ---")
        url = "http://127.0.0.1:8000/"
        max_retries = 10
        wait_time = 2  # 每次重試的等待時間 (秒)
        response = None

        # 加入重試邏輯，因為伺服器可能需要一些時間來啟動
        for i in range(max_retries):
            print(f"嘗試連線到 {url} (第 {i+1}/{max_retries} 次)...")
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    print(f"✅ 成功收到回應！狀態碼: {response.status_code}")
                    # 檢查回應內容是否為 HTML
                    content_type = response.headers.get('content-type', '')
                    assert 'text/html' in content_type, f"預期 content-type 為 'text/html'，但收到了 '{content_type}'"
                    print("✅ 回應的 Content-Type 正確。")
                    break
            except requests.ConnectionError:
                time.sleep(wait_time)

        if response is None or response.status_code != 200:
            print("❌ 驗證失敗：無法在指定時間內從伺服器獲得 200 OK 回應。", file=sys.stderr)
            raise RuntimeError("伺服器驗證失敗。")

        print("\n🎉 端對端驗證成功！整個流程運作正常。")

    except Exception as e:
        print(f"\n💥 測試過程中發生錯誤: {e}", file=sys.stderr)
        # 重新拋出異常，讓腳本以非零狀態碼退出，表示失敗
        raise

    finally:
        # --- 步驟 5: 清理 ---
        print("\n--- 步驟 5/5: 清理背景程序 ---")
        if server_process:
            print(f"正在終止伺服器程序 (PID: {server_process.pid})...")
            server_process.terminate()
            try:
                # 等待程序終止，並讀取其剩餘的輸出以供偵錯
                stdout, stderr = server_process.communicate(timeout=5)
                print("--- 伺服器剩餘 stdout: ---")
                print(stdout)
                print("--- 伺服器剩餘 stderr: ---")
                print(stderr, file=sys.stderr)
            except subprocess.TimeoutExpired:
                print("伺服器程序未能優雅終止，將強制結束。", file=sys.stderr)
                server_process.kill()
            print("✅ 伺服器程序已清理。")

if __name__ == "__main__":
    main()
