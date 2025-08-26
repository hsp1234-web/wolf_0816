# -*- coding: utf-8 -*-
"""
一個獨立的 Python 腳本，用於在 Colab 環境中預先烘烤所有依賴項。

此腳本會：
1. 安裝所有必要的 Python 套件到一個暫存目錄。
2. 將專案的原始碼也複製到該目錄中。
3. 將整個目錄打包成一個 'dependencies.tar.gz' 檔案。
4. 將壓縮檔移動到 Colab 的根目錄 `/content/`。
5. 在整個過程中即時、詳細地顯示所有日誌。
"""
import subprocess
import sys
import os
from pathlib import Path

# --- 設定 ---
# 顏色代碼，用於美化輸出
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

# 將 requirements-unified.txt 的內容直接嵌入腳本中
# 這樣就不需要依賴外部檔案，使其完全獨立
REQUIREMENTS_CONTENT = """
fastapi
uvicorn
httpx
pytest
trio
python-multipart
pytz
jsonpatch
requests
websockets
pydantic-settings
psutil
torch
faster-whisper
opencc-python-reimplemented
"""

# --- 核心函式 ---

def run_command_realtime(command, cwd=None):
    """
    執行一個 shell 指令，並即時將其 stdout 和 stderr 串流輸出到主控台。
    這是實現「瀑布流」日誌的核心。
    """
    print(f"{BLUE}▶️  正在執行指令: {' '.join(command)}{RESET}")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        bufsize=1  # 設定行緩衝
    )

    # 逐行讀取並打印輸出
    for line in iter(process.stdout.readline, ''):
        sys.stdout.write(line)
        sys.stdout.flush()

    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command)

def main():
    """主執行流程"""
    print(f"{GREEN}--- 🚀 開始預烘烤依賴包 ---{RESET}")

    # 檢查是否在 Colab 環境中
    in_colab = 'google.colab' in sys.modules
    if not in_colab:
        print(f"{YELLOW}⚠️  警告：未在 Google Colab 環境中執行。檔案將儲存至當前目錄。{RESET}")

    # 定義路徑
    # 將所有操作都在 /content 目錄下進行，以避免權限問題
    base_dir = Path("/content") if in_colab else Path.cwd()
    project_dir = base_dir / "wolf_project" # 假設專案已 clone 到這裡
    build_dir = base_dir / "_build"
    deps_dir = build_dir / "deps"
    output_archive = base_dir / "dependencies.tar.gz"
    requirements_file = base_dir / "temp_requirements.txt"

    try:
        # --- 步驟 1: 準備環境 ---
        print(f"\n{BLUE}--- 步驟 1/5: 準備環境 ---{RESET}")

        # 建立暫存的需求檔案
        print(f"正在建立暫存需求檔案: {requirements_file}")
        requirements_file.write_text(REQUIREMENTS_CONTENT.strip())

        # 建立暫存目錄
        print(f"正在建立暫存建置目錄: {deps_dir}")
        deps_dir.mkdir(parents=True, exist_ok=True)

        # --- 步驟 2: 檢查並安裝 uv ---
        print(f"\n{BLUE}--- 步驟 2/5: 檢查並安裝 uv ---{RESET}")
        try:
            run_command_realtime(["uv", "--version"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("uv 未找到，正在透過 pip 安裝...")
            run_command_realtime([sys.executable, "-m", "pip", "install", "-q", "uv"])
            run_command_realtime(["uv", "--version"])

        # --- 步驟 3: 安裝依賴 ---
        print(f"\n{BLUE}--- 步驟 3/5: 使用 uv 安裝依賴 (此步驟可能需要較長時間) ---{RESET}")
        run_command_realtime([
            "uv", "pip", "install",
            "-r", str(requirements_file),
            "--target", str(deps_dir)
        ])

        # --- 步驟 4: 複製原始碼 ---
        print(f"\n{BLUE}--- 步驟 4/5: 複製專案原始碼 ---{RESET}")
        # 為了讓此腳本獨立，我們假設它在 Colab 中與專案資料夾位於同一層級
        if not project_dir.is_dir():
             raise FileNotFoundError(f"錯誤：專案目錄 '{project_dir}' 不存在。請先執行 Colabpro.py 的第一部分來下載專案。")

        print(f"正在從 '{project_dir}' 複製 'src', 'services', 'workers'...")
        for subdir in ["src", "services", "workers", "vue-app", "youtube_downloads"]:
            source = project_dir / subdir
            if source.is_dir():
                # 使用 shell 的 cp -r 命令，比 python 的 shutil 更快
                run_command_realtime(["cp", "-r", str(source), str(deps_dir)])
                print(f"  - 已複製: {subdir}")
            else:
                print(f"{YELLOW}  - 警告: 來源目錄 '{source}' 不存在，跳過複製。{RESET}")

        # --- 步驟 5: 打包 ---
        print(f"\n{BLUE}--- 步驟 5/5: 將所有檔案打包成 .tar.gz ---{RESET}")
        run_command_realtime([
            "tar", "-czf", str(output_archive),
            "-C", str(deps_dir), "."
        ])

        # --- 完成 ---
        print("\n" + "="*50)
        print(f"{GREEN}✅  成功！依賴包已成功建立。{RESET}")
        print(f"   檔案路徑: {GREEN}{output_archive}{RESET}")
        print("   您可以將此路徑複製，或在左側檔案瀏覽器中找到它，然後上傳到 Google Drive。")
        print("="*50 + "\n")

    except FileNotFoundError as e:
        print(f"\n❌ 錯誤：找不到必要的檔案或目錄。 {e}", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 錯誤：一個關鍵指令執行失敗，返回碼: {e.returncode}。", file=sys.stderr)
        print(f"   失敗的指令: {' '.join(e.cmd)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 發生未預期的錯誤: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # 清理暫存檔案
        if 'requirements_file' in locals() and requirements_file.exists():
            requirements_file.unlink()
        if 'build_dir' in locals() and build_dir.exists():
            print("正在清理暫存建置目錄...")
            run_command_realtime(["rm", "-rf", str(build_dir)])

if __name__ == "__main__":
    main()
