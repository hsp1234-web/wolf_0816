# -*- coding: utf-8 -*-
"""
智慧啟動器 (Smart Launcher)

此腳本為應用程式的唯一入口點。其主要職責是：
1. 檢查 `dependencies.tar.gz` 是否存在。
2. (後續步驟) 將依賴解壓縮到一個暫存目錄。
3. (後續步驟) 將該暫存目錄注入到 sys.path。
4. (後續步驟) 啟動主應用程式。

這樣做可以確保應用程式在一個乾淨、隔離且一致的環境中運行。
"""

import os
import sys
import tarfile
import tempfile
import shutil

def main():
    """主執行函數"""
    print("--- 智慧啟動器 ---")

    # 定義依賴壓縮檔的路徑
    deps_archive_path = "dependencies.tar.gz"

    # 步驟 1: 檢查依賴壓縮檔是否存在
    print(f"1/4: 正在檢查依賴檔案 '{deps_archive_path}'...")
    if not os.path.exists(deps_archive_path):
        print(f"錯誤：依賴壓縮檔 '{deps_archive_path}' 不存在。", file=sys.stderr)
        print("請先執行 'scripts/bake_dependencies.sh' 來產生依賴檔。", file=sys.stderr)
        sys.exit(1)

    print("✅ 依賴檔案已找到。")

    # --- 步驟 2 & 3: 解壓縮依賴與注入路徑 ---

    # 建立一個不會自動刪除的暫存目錄
    # 這樣可以確保在應用程式運行的整個生命週期中，依賴檔案都存在
    # 我們依賴作業系統的 /tmp 清理機制來處理它
    deps_path = tempfile.mkdtemp(prefix="baked_deps_")
    print(f"2/4: 正在將依賴解壓縮至暫存目錄: {deps_path}")

    try:
        # 使用 tarfile 模組解壓縮
        with tarfile.open(deps_archive_path, "r:gz") as tar:
            tar.extractall(path=deps_path)
        print("✅ 解壓縮完成。")
    except (tarfile.TarError, IOError) as e:
        print(f"錯誤：解壓縮 '{deps_archive_path}' 時發生嚴重錯誤: {e}", file=sys.stderr)
        # 如果解壓縮失敗，清理已建立的目錄
        shutil.rmtree(deps_path)
        sys.exit(1)

    # 將解壓縮後的目錄添加到 sys.path 的最前端
    # 這確保 Python 在尋找模組時會優先查看我們的依賴目錄
    sys.path.insert(0, deps_path)
    print(f"3/4: 成功將依賴路徑注入到 sys.path。")
    print(f"   - 新的優先路徑: {sys.path[0]}")

    # --- 步驟 4: 啟動主應用程式 ---
    print("\n--- 啟動應用程式 ---")
    print("正在從 src.core.mini_server 導入 'app'...")

    try:
        # 因為依賴路徑已經被注入，現在我們可以安全地導入 uvicorn
        # 同時，因為 src 目錄在專案根目錄，我們可以直接導入 src 下的模組
        import uvicorn
        from src.core.mini_server import app

        print("✅ 應用程式 'app' 導入成功。")
        print("伺服器即將在 http://0.0.0.0:8000 啟動...")

        # 使用 uvicorn 啟動 Starlette/FastAPI 應用
        # 這是一個阻塞操作，伺服器會一直運行直到手動停止
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

    except ImportError as e:
        print(f"錯誤：無法導入應用程式或 uvicorn。請確認 'src/core/mini_server.py' 存在且 uvicorn 已被包含在依賴中。詳細資訊: {e}", file=sys.stderr)
        # 清理已建立的目錄
        shutil.rmtree(deps_path)
        sys.exit(1)
    except Exception as e:
        print(f"錯誤：啟動應用程式時發生未預期的錯誤: {e}", file=sys.stderr)
        # 清理已建立的目錄
        shutil.rmtree(deps_path)
        sys.exit(1)


if __name__ == "__main__":
    main()
