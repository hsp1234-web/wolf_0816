# -*- coding: utf-8 -*-
#@title 📥🐺 善狼一鍵啟動器 (v11) 🐺
#@markdown ---
#@markdown ### **(1) 專案來源設定**
#@markdown > **請提供 Git 倉庫的網址、要下載的分支或標籤，以及本地資料夾名稱。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/wolf_0816.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "688" #@param {type:"string"}
#@markdown **專案資料夾名稱 (PROJECT_FOLDER_NAME)**
PROJECT_FOLDER_NAME = "wolf_project" #@param {type:"string"}
#@markdown **強制刷新後端程式碼 (FORCE_REPO_REFRESH)**
#@markdown > **如果勾選，每次執行都會先刪除舊的專案資料夾，再重新下載。**
FORCE_REPO_REFRESH = False #@param {type:"boolean"}
#@markdown ---
#@markdown ### **(2) 通用設定**
#@markdown > **此處為儀表板顯示相關的常用設定。**
#@markdown ---
#@markdown **儀表板更新頻率 (秒)**
UI_REFRESH_SECONDS = 0.5 #@param {type:"number"}
#@markdown **時區設定**
TIMEZONE = "Asia/Taipei" #@param {type:"string"}
#@markdown **自動清理畫面 (ENABLE_CLEAR_OUTPUT)**
#@markdown > **勾選後，儀表板會自動刷新，介面較為清爽。取消勾選則會保留所有日誌，方便除錯。**
ENABLE_CLEAR_OUTPUT = True #@param {type:"boolean"}
#@markdown ---
#@markdown > **確認所有設定無誤後，點擊此儲存格左側的「執行」按鈕來啟動所有程序。**
#@markdown ---

# ======================================================================================
# ==                                  開發者日誌                                  ==
# ======================================================================================
#
# 版本: 11.0 (架構: 關注點分離)
# 日期: 2025-08-25T04:05:00+08:00
#
# 本次變更重點:
# 1. **架構重構**: 將此檔案重構為一個「輕量級」啟動器。
# 2. **關注點分離**: 所有複雜的啟動邏輯（依賴準備、伺服器啟動、通道建立、UI 刷新）
#    皆已移至核心啟動腳本 `run.py`。
# 3. **職責單一**: 此檔案現在的唯一職責是提供 Colab UI 參數，並呼叫 `run.py`。
#
# ======================================================================================

# ==============================================================================
# SECTION 0: 環境準備與核心依賴導入
# ==============================================================================
import sys
import os
import shutil
import subprocess
from pathlib import Path
import traceback

# ==============================================================================
# PART 1: GIT 下載器功能
# ==============================================================================
def download_repository(project_folder_name, repo_url, branch):
    """下載或更新指定的 Git 倉庫。"""
    project_path = Path(project_folder_name)

    print(f"準備下載專案至 '{project_folder_name}'...")
    print(f"  - 倉庫: {repo_url}")
    print(f"  - 分支: {branch}")

    if FORCE_REPO_REFRESH and project_path.exists():
        print(f"偵測到舊的專案資料夾，正在強制刪除: {project_path}")
        try:
            shutil.rmtree(project_path)
            print("✅ 舊資料夾已成功刪除。")
        except OSError as e:
            print(f"❌ 刪除舊資料夾失敗: {e}。請手動刪除後再試。")
            return None

    if project_path.exists():
        print(f"✅ 專案資料夾 '{project_path}' 已存在，將跳過下載。")
        return str(project_path.resolve())

    print("🚀 開始從 Git 下載...")
    try:
        subprocess.run(
            ["git", "clone", "--branch", branch, "--depth", "1", repo_url, str(project_path)],
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ 專案程式碼下載成功！")
        return str(project_path.resolve())
    except subprocess.CalledProcessError as e:
        print(f"❌ Git clone 失敗: {e.stderr}")
        return None

# ==============================================================================
# PART 2: 主啟動器邏輯
# ==============================================================================
def launch_application(project_path_str: str, deps_path_str: str):
    """
    在指定的專案路徑中，執行核心的 run.py 腳本，並傳入所有必要的參數。
    """
    project_path = Path(project_path_str)
    run_script_path = project_path / "run.py"

    if not run_script_path.exists():
        print(f"❌ 錯誤：在專案目錄中找不到核心啟動腳本 'run.py'。")
        print(f"請確認 '{TARGET_BRANCH_OR_TAG}' 分支中包含 'run.py' 檔案。")
        return

    print("\n---")
    print(f"📂 執行目錄: {project_path}")
    print(f"🚀 即將執行核心啟動器: {run_script_path}")
    print("---\n")

    try:
        # 設定 PYTHONUNBUFFERED=1 環境變數，確保 run.py 的輸出能即時顯示在 Colab 上
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # 準備要傳遞給 run.py 的指令行參數
        command = [
            sys.executable, str(run_script_path),
            "--deps-path", deps_path_str,
            "--refresh-rate", str(UI_REFRESH_SECONDS),
            "--timezone", TIMEZONE,
        ]
        if not ENABLE_CLEAR_OUTPUT:
            command.append("--no-clear-output")

        # 執行 run.py 並等待其完成
        subprocess.run(
            command,
            cwd=project_path,
            check=True,
            env=env
        )
    except subprocess.CalledProcessError as e:
        print(f"\n--- ❌ 核心啟動器執行失敗 (返回碼: {e.returncode}) ---")
    except KeyboardInterrupt:
        print("\n\n👋 偵測到手動中斷，程序已由使用者終止。")
    except Exception as e:
        print(f"\n--- ❌ 發生未預期的致命錯誤 ---")
        traceback.print_exc()

# ==============================================================================
# FINAL EXECUTION BLOCK
# ==============================================================================
if __name__ == '__main__':
    print("--- 善狼一鍵啟動器 ---")

    # 獲取當前工作目錄，以建構依賴檔案的絕對路徑
    # 這是為了修復在 chdir 後找不到依賴檔案的問題
    root_dir = Path.cwd()
    deps_archive_path = root_dir / "dependencies.tar.gz"

    if not deps_archive_path.exists():
        print(f"❌ 致命錯誤：依賴壓縮檔 '{deps_archive_path}' 不存在。")
        print("請確保 'dependencies.tar.gz' 檔案與此 Colab 筆記本位於同一目錄。")
    else:
        # 步驟 1: 下載專案程式碼
        project_path = download_repository(
            project_folder_name=PROJECT_FOLDER_NAME,
            repo_url=REPOSITORY_URL,
            branch=TARGET_BRANCH_OR_TAG
        )

        # 步驟 2: 如果下載成功，則啟動應用程式
        if project_path:
            # 將工作目錄切換到專案根目錄
            os.chdir(project_path)
            # 執行主應用程式，並傳入依賴檔案的絕對路徑
            launch_application(project_path, str(deps_archive_path))
        else:
            print("\n--- ❌ 由於專案下載失敗，啟動程序已中止 ---")

    print("\n--- 執行結束 ---")
