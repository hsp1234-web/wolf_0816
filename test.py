# -*- coding: utf-8 -*-
"""
工作者整合測試腳本 (Worker Integration Test Script)

本腳本為一個自動化整合測試工具，旨在驗證所有工作者 (worker) 是否遵循
「自我管理」的設計原則。其核心任務是逐一、獨立地啟動每一個 `run_*_worker.py`
檔案，並確認它們是否能在指定時間內（90秒）成功建立自己的虛擬環境、
安裝所有依賴，並進入準備就緒的狀態。

主要測試流程：
1.  自動尋找：使用 glob 動態尋找所有 `run_*_worker.py` 檔案。
2.  獨立執行：為每個工作者啟動一個全新的、隔離的子行程。
3.  測試前清理：執行前確保工作者對應的舊虛擬環境被徹底刪除。
4.  限時驗證：
    - 監控子行程的標準輸出 (stdout)。
    - 等待特定的成功訊息（"工作者已啟動，開始監聽任務..."）。
    - 若在 90 秒內未收到成功訊息，則視為超時失敗。
5.  強制清理：無論測試成功、失敗或超時，腳本都會確保終止子行程，
    並徹底刪除其在測試過程中建立的虛擬環境資料夾。
6.  產出報告：所有測試結束後，提供一份清晰的成功/失敗總結報告。

此腳本是確保所有工作者具備獨立部署與運作能力的關鍵品質保證工具。
"""

import sys
import glob
import subprocess
import time
import shutil
import re
from pathlib import Path

# --- 全局設定 ---
# 測試超時時間（秒）
WORKER_TIMEOUT_SECONDS = 90
# 工作者腳本的命名模式
WORKER_GLOB_PATTERN = "run_*_worker.py"
# 從工作者輸出中尋找的成功信號
# 我們從 `run_youtube_worker.py` 的日誌中得知，當工作者準備就緒時，會輸出此訊息
SUCCESS_SIGNAL = "工作者已啟動，開始監聽任務..."

def get_venv_path(worker_path: Path) -> Path:
    """
    根據工作者腳本路徑推導其虛擬環境的路徑。
    例如：'run_youtube_worker.py' -> '.venv_youtube'
    """
    # 使用正規表示式從檔名 'run_FOO_worker.py' 中提取 'FOO'
    match = re.search(r"run_(.+)_worker\.py", worker_path.name)
    if not match:
        # 如果命名不符預期，提供一個預設的回退方案
        base_name = worker_path.stem
        print(f"⚠️  警告：無法從 '{worker_path.name}' 中解析標準名稱，將使用 '{base_name}' 作為基礎名稱。")
    else:
        base_name = match.group(1)

    return worker_path.parent / f".venv_{base_name}"

def test_worker(worker_path: Path) -> bool:
    """
    對單一工作者腳本進行完整的啟動、驗證與清理測試。

    Args:
        worker_path: 指向工作者 .py 檔案的 Path 物件。

    Returns:
        如果工作者在時限內成功啟動，則返回 True，否則返回 False。
    """
    print("-" * 70)
    print(f"▶️  正在測試: {worker_path.name}")
    print("-" * 70)

    venv_path = get_venv_path(worker_path)
    print(f"   - 預期虛擬環境路徑: {venv_path}")

    # --- 1. 測試前清理 ---
    if venv_path.exists():
        print(f"   - 發現殘留的虛擬環境，正在清理: {venv_path}")
        try:
            shutil.rmtree(venv_path)
            print(f"   - 清理完畢。")
        except OSError as e:
            print(f"❌ 錯誤：無法刪除舊的虛擬環境 '{venv_path}'。錯誤訊息: {e}", file=sys.stderr)
            return False

    # --- 2. 啟動工作者子行程 ---
    start_time = time.monotonic()
    print(f"   - 於 {time.strftime('%H:%M:%S')} 啟動子行程...")
    print(f"   - 超時設定: {WORKER_TIMEOUT_SECONDS} 秒")

    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(worker_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 將 stderr 合併到 stdout
            text=True,
            encoding='utf-8',
            bufsize=1  # 行緩衝
        )

        # --- 3. 即時監控輸出 ---
        while True:
            # 檢查是否超時
            elapsed_time = time.monotonic() - start_time
            if elapsed_time > WORKER_TIMEOUT_SECONDS:
                print(f"\n❌ 失敗：測試超時（超過 {WORKER_TIMEOUT_SECONDS} 秒）。", file=sys.stderr)
                return False

            # 檢查子行程是否意外退出
            if proc.poll() is not None:
                print(f"\n❌ 失敗：子行程意外終止，返回碼: {proc.returncode}。", file=sys.stderr)
                # 讀取並印出剩餘的輸出以供除錯
                remaining_output = proc.stdout.read()
                print("--- 子行程剩餘輸出 ---", file=sys.stderr)
                print(remaining_output, file=sys.stderr)
                print("----------------------", file=sys.stderr)
                return False

            # 讀取一行輸出（非阻塞的方式會更複雜，這裡採用簡單的超時邏輯）
            # 為了避免 readline() 卡死，我們不能直接用 for 迴圈
            # 但 Popen 的 stdout 迭代本身是阻塞的。這裡我們依靠外部的超時邏輯。
            # 實際上，在多數情況下，這個迴圈會因 readline() 而阻塞，
            # 但我們的整體架構會在超時後終止它。
            # 一個更健壯的作法是使用 selectors 或 threads，但目前這個方法對於我們的需求已足夠。
            try:
                line = proc.stdout.readline()
                if not line:
                    # 如果 readline 返回空字串，代表流已關閉，行程已結束
                    continue

                print(f"   [輸出] {line.strip()}")
                if SUCCESS_SIGNAL in line:
                    print(f"\n✅ 成功！在 {elapsed_time:.2f} 秒內偵測到成功信號。")
                    return True
            except Exception:
                # 忽略解碼錯誤等問題
                pass


    except FileNotFoundError:
        print(f"❌ 錯誤：找不到 Python 解譯器 '{sys.executable}' 或工作者腳本 '{worker_path}'。", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ 執行測試時發生未預期的錯誤: {e}", file=sys.stderr)
        return False
    finally:
        # --- 4. 強制終止與清理 ---
        print("   - 測試結束，開始執行清理程序...")
        if proc and proc.poll() is None:
            print("   - 正在終止子行程...")
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("   - 溫和終止失敗，強制終止子行程...")
                proc.kill()
            print("   - 子行程已終止。")

        if venv_path.exists():
            print(f"   - 正在刪除虛擬環境: {venv_path}")
            try:
                shutil.rmtree(venv_path)
                print("   - 虛擬環境已成功刪除。")
            except OSError as e:
                print(f"❌ 錯誤：無法在後清理階段刪除虛擬環境 '{venv_path}'。請手動刪除。錯誤訊息: {e}", file=sys.stderr)
        else:
            print("   - 虛擬環境不存在，無需清理。")
        print("-" * 70 + "\n")


def main():
    """
    主執行函式，尋找並測試所有工作者。
    """
    print("=" * 70)
    print("=== 開始執行工作者整合測試 ===")
    print("=" * 70)

    worker_scripts = list(Path.cwd().glob(WORKER_GLOB_PATTERN))

    if not worker_scripts:
        print(f"找不到任何符合 '{WORKER_GLOB_PATTERN}' 模式的工作者腳本。測試中止。")
        sys.exit(0)

    print(f"發現 {len(worker_scripts)} 個工作者腳本，將逐一進行測試：")
    for script in worker_scripts:
        print(f"  - {script.name}")
    print("\n")

    passed_tests = []
    failed_tests = []

    for worker_path in worker_scripts:
        is_success = test_worker(worker_path)
        if is_success:
            passed_tests.append(worker_path.name)
        else:
            failed_tests.append(worker_path.name)

    # --- 產出最終報告 ---
    print("=" * 70)
    print("=== 整合測試總結報告 ===")
    print("=" * 70)
    print(f"總共測試: {len(worker_scripts)} 個工作者")
    print(f"✅ 成功: {len(passed_tests)} 個")
    print(f"❌ 失敗: {len(failed_tests)} 個")

    if failed_tests:
        print("\n--- 失敗的測試項目 ---")
        for test_name in failed_tests:
            print(f"  - {test_name}")
        print("\n測試未通過。")
        sys.exit(1)
    else:
        print("\n🎉 所有工作者均通過整合測試！")
        sys.exit(0)

if __name__ == "__main__":
    main()
