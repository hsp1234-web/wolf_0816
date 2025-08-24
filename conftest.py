# -*- coding: utf-8 -*-
"""
Pytest 的設定檔案 (Configuration File)

此檔案用於定義全域的 Fixture，它們可以被專案中所有的測試自動發現和使用。
"""

import pytest
import os
import sys
import subprocess
import tarfile
import tempfile
import shutil

@pytest.fixture(scope="session", autouse=True)
def baked_env(request):
    """
    一個會話級的 fixture，在所有測試開始前自動執行一次。

    它的核心職責是模擬 `run.py` 的啟動過程，為整個測試會話
    準備一個乾淨、一致且包含所有依賴的執行環境。

    `autouse=True` 確保了無需在每個測試中手動引用此 fixture。
    """
    print("\n--- [Fixture: baked_env] 準備預先烘烤的依賴環境 ---")

    # 1. 執行烘烤腳本來產生依賴壓縮檔
    bake_script = "scripts/bake_dependencies.sh"
    print(f"--> 正在執行烘烤腳本: {bake_script}")
    # 使用 subprocess.run 執行，並在失敗時拋出例外
    subprocess.run(["bash", bake_script], check=True, capture_output=True)
    assert os.path.exists("dependencies.tar.gz"), "烘烤失敗：'dependencies.tar.gz' 未被建立。"
    print("--> 烘烤完成。")

    # 2. 建立暫存目錄，解壓縮依賴，並注入到 sys.path
    deps_archive_path = "dependencies.tar.gz"
    # 使用 mkdtemp 建立一個目錄，我們會在測試結束後手動清理它
    deps_path = tempfile.mkdtemp(prefix="pytest_baked_deps_")
    print(f"--> 正在將依賴解壓縮至: {deps_path}")
    try:
        with tarfile.open(deps_archive_path, "r:gz") as tar:
            # Python 3.12+ 的 tarfile.extractall 建議使用 filter
            # 為了相容性與安全，我們使用 'data' filter
            if sys.version_info >= (3, 12):
                tar.extractall(path=deps_path, filter='data')
            else:
                tar.extractall(path=deps_path)
    except Exception as e:
        # 如果解壓縮失敗，確保清理目錄
        shutil.rmtree(deps_path)
        pytest.fail(f"解壓縮依賴時發生錯誤: {e}")

    # 將依賴路徑注入到 sys.path 的最前端
    sys.path.insert(0, deps_path)
    print(f"--> 成功將依賴路徑注入到 sys.path: {deps_path}")

    # Fixture 的準備工作到此為止，`yield` 會將控制權交給測試執行器
    yield

    # --- Teardown ---
    # 在所有測試執行完畢後，這裡的程式碼會被執行
    print(f"\n--- [Fixture: baked_env] 清理環境 ---")
    # 從 sys.path 中移除我們新增的路徑
    if deps_path in sys.path:
        sys.path.remove(deps_path)
    # 刪除暫存目錄
    shutil.rmtree(deps_path)
    # 刪除依賴壓縮檔
    if os.path.exists(deps_archive_path):
        os.remove(deps_archive_path)
    print("--> 清理完成。")
