# -*- coding: utf-8 -*-
"""
核心 Web 伺服器啟動器

此腳本的唯一職責是：
1. 根據傳入的路徑準備依賴環境。
2. 啟動 uvicorn 伺服器並監聽指定埠號。
3. 將正在監聽的埠號打印到 stdout，以便父程序可以捕獲它。
"""
import os
import sys
from pathlib import Path

import tarfile
import tempfile
import shutil
from pathlib import Path
import argparse
import socket

def find_available_port() -> int:
    """尋找一個可用的 TCP 埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def prepare_dependencies(deps_archive_path_str):
    """
    檢查並解壓縮指定的 `dependencies.tar.gz`，然後切換工作目錄到解壓後的路徑。
    """
    print("核心啟動器：正在準備依賴環境...")
    deps_archive_path = Path(deps_archive_path_str)
    if not deps_archive_path.is_file():
        print(f"核心啟動器錯誤：依賴壓縮檔 '{deps_archive_path}' 不存在或不是一個檔案。", file=sys.stderr)
        return False

    deps_path = tempfile.mkdtemp(prefix="baked_deps_")
    try:
        with tarfile.open(deps_archive_path, "r:gz") as tar:
            tar.extractall(path=deps_path)
    except (tarfile.TarError, IOError) as e:
        print(f"核心啟動器錯誤：解壓縮 '{deps_archive_path}' 時發生嚴重錯誤: {e}", file=sys.stderr)
        shutil.rmtree(deps_path)
        return False

    # 關鍵修正：切換工作目錄到解壓後的依賴目錄
    # 這可以確保 uvicorn 從正確的位置載入應用程式，而不是從原始專案目錄。
    os.chdir(deps_path)
    # 將當前目錄（即解壓後的目錄）加入 sys.path
    sys.path.insert(0, ".")
    print(f"核心啟動器：工作目錄已切換至 {deps_path} 並將其加入 sys.path。")
    return True

def main():
    """主執行函數"""
    parser = argparse.ArgumentParser(description="核心 Web 伺服器啟動器")
    parser.add_argument("--deps-path", required=True, help="預先烘烤的依賴壓縮檔 (dependencies.tar.gz) 的絕對路徑。")
    args = parser.parse_args()

    # 步驟 1: 準備依賴
    if not prepare_dependencies(args.deps_path):
        sys.exit(1)

    # 步驟 2: 啟動主應用程式
    try:
        import uvicorn
        from services.api_gateway.main import app

        port = find_available_port()
        if not port:
            print("核心啟動器錯誤：找不到可用的埠號。", file=sys.stderr)
            sys.exit(1)

        # 關鍵修正：將埠號設定為環境變數，以便背景執行緒 (如硬體監控) 可以存取
        os.environ["API_PORT"] = str(port)

        # 關鍵一步：將埠號打印到 stdout，以便父程序捕獲
        print(f"APP_PORT:{port}", flush=True)

        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    except ImportError as e:
        print(f"核心啟動器錯誤：無法導入應用程式或 uvicorn。詳細資訊: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"核心啟動器錯誤：啟動應用程式時發生未預期的錯誤: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
