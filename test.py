# -*- coding: utf-8 -*-
"""
工作者整合測試暨前端測試腳本

本腳本為一個自動化整合測試工具，具備兩種模式：
1.  **後端工作者測試** (預設模式):
    旨在驗證所有工作者 (worker) 是否遵循「自我管理」的設計原則。
    其核心任務是逐一、獨立地啟動每一個 `run_*_worker.py` 檔案，
    並確認它們是否能在指定時間內成功建立虛擬環境、安裝依賴並進入準備就緒狀態。

2.  **前端點擊日誌測試** (透過 --frontend-only 旗標啟動):
    執行一個特定的 Playwright 端對端測試，用於驗證前端應用程式的全域點擊
    日誌功能是否如預期般運作。

主要測試流程 (後端):
-   自動尋找 `run_*_worker.py` 檔案。
-   為每個工作者啟動隔離的子行程進行測試。
-   測試前後進行環境清理。
-   監控輸出以驗證工作者是否成功啟動。
-   產出最終的成功/失敗總結報告。

此腳本是確保專案品質的關鍵工具。
"""

import sys
import glob
import subprocess
import time
import shutil
import re
import argparse
from pathlib import Path

# --- 全局設定 ---
# 測試超時時間（秒）
WORKER_TIMEOUT_SECONDS = 90
# 工作者腳本的命名模式
WORKER_GLOB_PATTERN = "run_*_worker.py"
# 從工作者輸出中尋找的成功信號
SUCCESS_SIGNAL = "工作者已啟動，開始監聽"
# 前端測試檔案路徑
FRONTEND_TEST_FILE = "e2e_tests/test_click_logging.py"

def get_venv_path(worker_path: Path) -> Path:
    """
    根據工作者腳本路徑推導其虛擬環境的路徑。
    """
    match = re.search(r"run_(.+)_worker\.py", worker_path.name)
    if not match:
        base_name = worker_path.stem
        print(f"⚠️  警告：無法從 '{worker_path.name}' 中解析標準名稱，將使用 '{base_name}' 作為基礎名稱。")
    else:
        base_name = match.group(1)
    return worker_path.parent / f".venv_{base_name}"

def run_frontend_test():
    """
    執行前端點擊日誌的 Playwright 測試。
    """
    print("=" * 70)
    print("=== 開始執行前端點擊日誌測試 ===")
    print("=" * 70)

    test_file_path = Path(FRONTEND_TEST_FILE)
    if not test_file_path.exists():
        print(f"❌ 錯誤：找不到前端測試檔案 '{FRONTEND_TEST_FILE}'。")
        sys.exit(1)

    print(f"將使用 Pytest 執行: {test_file_path}")

    # 使用 -s 旗標來顯示測試中的 print 語句
    command = [sys.executable, "-m", "pytest", "-s", str(test_file_path)]

    try:
        # 將 stdout 和 stderr 都導向當前進程，以便即時看到輸出
        result = subprocess.run(command, check=True, text=True, encoding='utf-8')
        print("\n🎉 前端測試成功通過！")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 前端測試失敗。返回碼: {e.returncode}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"❌ 錯誤：找不到 Python 解譯器 '{sys.executable}' 或 pytest。請確保 pytest 已安裝。")
        sys.exit(1)

def test_worker(worker_path: Path) -> bool:
    """
    對單一工作者腳本進行完整的啟動、驗證與清理測試。
    """
    print("-" * 70)
    print(f"▶️  正在測試: {worker_path.name}")
    print("-" * 70)
    venv_path = get_venv_path(worker_path)
    print(f"   - 預期虛擬環境路徑: {venv_path}")

    if venv_path.exists():
        print(f"   - 發現殘留的虛擬環境，正在清理: {venv_path}")
        try:
            shutil.rmtree(venv_path)
            print(f"   - 清理完畢。")
        except OSError as e:
            print(f"❌ 錯誤：無法刪除舊的虛擬環境 '{venv_path}'。錯誤訊息: {e}", file=sys.stderr)
            return False

    start_time = time.monotonic()
    print(f"   - 於 {time.strftime('%H:%M:%S')} 啟動子行程...")
    print(f"   - 超時設定: {WORKER_TIMEOUT_SECONDS} 秒")

    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(worker_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1
        )

        while True:
            elapsed_time = time.monotonic() - start_time
            if elapsed_time > WORKER_TIMEOUT_SECONDS:
                print(f"\n❌ 失敗：測試超時（超過 {WORKER_TIMEOUT_SECONDS} 秒）。", file=sys.stderr)
                return False

            if proc.poll() is not None:
                print(f"\n❌ 失敗：子行程意外終止，返回碼: {proc.returncode}。", file=sys.stderr)
                remaining_output = proc.stdout.read()
                print("--- 子行程剩餘輸出 ---", file=sys.stderr)
                print(remaining_output, file=sys.stderr)
                print("----------------------", file=sys.stderr)
                return False

            try:
                line = proc.stdout.readline()
                if not line:
                    continue
                print(f"   [輸出] {line.strip()}")
                if SUCCESS_SIGNAL in line:
                    print(f"\n✅ 成功！在 {elapsed_time:.2f} 秒內偵測到成功信號。")
                    return True
            except Exception:
                pass

    except FileNotFoundError:
        print(f"❌ 錯誤：找不到 Python 解譯器 '{sys.executable}' 或工作者腳本 '{worker_path}'。", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ 執行測試時發生未預期的錯誤: {e}", file=sys.stderr)
        return False
    finally:
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
    主執行函式，根據命令列參數決定執行後端或前端測試。
    """
    parser = argparse.ArgumentParser(description="整合測試腳本，可用於後端工作者或前端 E2E 測試。")
    parser.add_argument(
        '--frontend-only',
        action='store_true',
        help='如果設定此旗標，將只執行前端點擊日誌測試。'
    )
    args = parser.parse_args()

    if args.frontend_only:
        run_frontend_test()
    else:
        run_worker_tests()

def run_worker_tests():
    """
    執行後端工作者的整合測試。
    """
    print("=" * 70)
    print("=== 開始執行後端工作者整合測試 ===")
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
