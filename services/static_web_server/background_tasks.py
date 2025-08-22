import asyncio
import sys
from pathlib import Path
import logging

# --- 基本設定 ---
# 由於此檔案被 main.py 導入，我們可以從 main.py 的視角來設定路徑
# main.py 的父目錄是 services/static_web_server/
# 我們需要往上兩層才能到達專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
VENV_DIR = ROOT_DIR / "venvs" # 使用正式的 venvs 目錄
LOG_PREFIX = "[BackgroundTask]"

# 使用 logging 模組，以便未來可以更好地控制日誌輸出
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
def log(message):
    logging.info(f"{LOG_PREFIX} {message}")

async def run_subprocess_async(command, **kwargs):
    """一個非同步執行子程序並記錄輸出的輔助函式。"""
    log(f"執行指令: {' '.join(command)}")
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **kwargs
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        log(f"❌ 指令執行失敗。返回碼: {proc.returncode}")
        log(f"   [stdout]:\n{stdout.decode('utf-8', 'ignore')}")
        log(f"   [stderr]:\n{stderr.decode('utf-8', 'ignore')}")
        raise subprocess.CalledProcessError(proc.returncode, command, stdout, stderr)
    log("✅ 指令執行成功。")
    return stdout.decode(), stderr.decode()

async def setup_venv_and_install_deps_async(venv_name: str, requirements_path: Path) -> Path:
    """
    (非同步版本) 建立一個獨立的虛擬環境並安裝指定的依賴。
    返回該虛擬環境的 Python 解譯器路徑。
    """
    log(f"--- 開始為 '{venv_name}' 設定虛擬環境 ---")
    venv_path = VENV_DIR / venv_name

    # 確保 uv 已安裝在全域環境 (此處假設 Colabpro 已處理)

    # 建立虛擬環境
    log(f"檢查或建立虛擬環境於: {venv_path}")
    await run_subprocess_async([sys.executable, "-m", "uv", "venv", str(venv_path)])

    # 判斷作業系統，取得正確的 Python 解譯器路徑
    python_executable = venv_path / "Scripts" / "python.exe" if sys.platform == "win32" else venv_path / "bin" / "python"

    # 安裝依賴
    log(f"在 '{venv_name}' 環境中安裝依賴: {requirements_path}")
    if not requirements_path.exists():
        log(f"❌ 找不到依賴檔案: {requirements_path}")
        raise FileNotFoundError(f"找不到依賴檔案: {requirements_path}")

    await run_subprocess_async([
        sys.executable, "-m", "uv", "pip", "install",
        "-r", str(requirements_path),
        "--python", str(python_executable)
    ])

    log(f"✅ '{venv_name}' 環境設定完成。")
    return python_executable

async def install_heavy_dependencies():
    """
    主要的背景任務，用於安裝所有重量級的服務依賴。
    """
    log("--- [背景任務] 開始執行重量級依賴安裝 ---")
    await asyncio.sleep(2) # 故意延遲，模擬伺服器已啟動後才開始執行

    service_list = [
        "local_ai_model_service",
        "media_preview_service",
        "notification_service",
        # 更多服務可以加在這裡
    ]

    for service_name in service_list:
        try:
            log(f"--- 開始設定 '{service_name}' ---")
            req_path = ROOT_DIR / "services" / service_name / "requirements.txt"
            if req_path.exists():
                await setup_venv_and_install_deps_async(service_name, req_path)
            else:
                log(f"ℹ️ 服務 '{service_name}' 沒有 requirements.txt，跳過。")
        except Exception as e:
            log(f"❌ 設定服務 '{service_name}' 失敗: {e}")
            # 在真實世界中，這裡可能需要更複雜的錯誤回報機制

    await asyncio.sleep(1)
    log("✅ [背景任務] 所有重量級依賴已安裝完成。")
