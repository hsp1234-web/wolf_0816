# runner/main_runner.py
import subprocess
import sys
import os
import re
import time
import logging
from pathlib import Path

# --- 設定 ---
# 取得專案根目錄 (此檔案位於 runner/，所以根目錄是上一層)
ROOT_DIR = Path(__file__).resolve().parent.parent
# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout # 將日誌輸出到 stdout，以便 Colabpro.py 可以捕捉
)
log = logging.getLogger('MainRunner')


def install_dependencies():
    """使用 uv 安裝伺服器依賴。"""
    log.info("--- [步驟 1/3] 正在安裝伺服器依賴 ---")
    # 使用新的、僅包含生產環境依賴的檔案
    requirements_path = ROOT_DIR / "requirements-prod-server.txt"
    if not requirements_path.exists():
        log.error(f"❌ 找不到生產環境依賴檔案: {requirements_path}")
        return False

    try:
        # 步驟 1a: 確保 uv 本身已安裝
        log.info("確保 'uv' 已安裝...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "uv"],
            check=True, capture_output=True, text=True, encoding='utf-8'
        )
        log.info("✅ 'uv' 已是最新狀態。")

        # 步驟 1b: 使用 uv 安裝依賴
        command = [
            sys.executable, "-m", "uv", "pip", "install",
            "-r", str(requirements_path),
            "--system"
        ]
        log.info(f"執行安裝命令: {' '.join(command)}")
        subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        log.info("✅ 伺服器依賴安裝成功。")

        # Playwright 是測試依賴，不應在此處安裝
        # log.info("正在安裝 Playwright 所需的瀏覽器...")
        # browser_command = [sys.executable, "-m", "playwright", "install"]
        # subprocess.run(browser_command, check=True, capture_output=True, text=True, encoding='utf-8')
        # log.info("✅ Playwright 瀏覽器安裝成功。")

        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ 依賴安裝失敗。返回碼: {e.returncode}")
        log.error(f"   stdout: {e.stdout}")
        log.error(f"   stderr: {e.stderr}")
        return False
    except Exception as e:
        log.error(f"❌ 依賴安裝過程中發生未預期的錯誤: {e}", exc_info=True)
        return False

def launch_and_monitor_orchestrator():
    """
    啟動並持續監控核心協調器，處理其日誌輸出並在找到URL時報告。
    這個函數將會持續運行，直到協調器終止或被中斷。
    """
    log.info("--- [步驟 2/3] 正在啟動並監控核心協調器 ---")
    orchestrator_script = ROOT_DIR / "src" / "core" / "orchestrator.py"
    if not orchestrator_script.exists():
        log.error(f"❌ 找不到協調器腳本: {orchestrator_script}")
        return False

    env = os.environ.copy()
    src_path = str(ROOT_DIR / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    env["API_MODE"] = "mock"

    command = [sys.executable, str(orchestrator_script)]
    log.info(f"執行協調器命令: {' '.join(command)}")

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # 將 stderr 合併到 stdout
        text=True,
        encoding='utf-8',
        env=env
    )

    url_pattern = re.compile(r"PROXY_URL:\s*(https?://[^\s]+)")
    url_found = False
    # JULES'S FIX: 核心修復邏輯
    # 持續讀取 orchestrator 的輸出，永不停止。
    # 這可以防止 stdout 管道被填滿，從而避免 orchestrator 子程序被阻塞或崩潰。
    try:
        for line in iter(proc.stdout.readline, ''):
            clean_line = line.strip()
            log.info(f"[Orchestrator]: {clean_line}")

            if not url_found:
                match = url_pattern.search(clean_line)
                if match:
                    server_url = match.group(1)
                    log.info(f"✅ 從協調器成功解析到 URL: {server_url}")
                    # 這是我們與外部世界的「合約」
                    log.info("--- [步驟 3/3] 輸出最終 URL ---")
                    print(f"FINAL_URL: {server_url}", flush=True)
                    url_found = True # 標記已找到，避免重複打印

        # 等待子程序自然結束
        proc.wait()

    except KeyboardInterrupt:
        log.info("收到手動中斷信號，正在關閉協調器...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.info("✅ 協調器已關閉。")
    except Exception as e:
        log.error(f"監控協調器時發生未預期錯誤: {e}", exc_info=True)
        if proc.poll() is None:
            proc.kill()
        return False

    if proc.returncode is not None and proc.returncode != 0:
        log.error(f"協調器意外終止，返回碼: {proc.returncode}")
        return False

    log.info("協調器已正常關閉。")
    return True

def main():
    """主執行函數"""
    # 步驟 1: 安裝依賴
    if not install_dependencies():
        sys.exit(1)

    # 步驟 2 & 3 & 4 都被整合到這個函數中
    if not launch_and_monitor_orchestrator():
        log.critical("❌ 主伺服器啟動或運行失敗。")
        sys.exit(1)

if __name__ == "__main__":
    main()
