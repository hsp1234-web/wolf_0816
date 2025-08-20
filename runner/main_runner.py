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

def launch_orchestrator():
    """啟動核心協調器並捕捉其輸出的 URL。"""
    log.info("--- [步驟 2/3] 正在啟動核心協調器 ---")
    orchestrator_script = ROOT_DIR / "src" / "core" / "orchestrator.py"
    if not orchestrator_script.exists():
        log.error(f"❌ 找不到協調器腳本: {orchestrator_script}")
        return None

    # 設定子程序的環境變數，確保它能找到 src 目錄下的模組
    env = os.environ.copy()
    src_path = str(ROOT_DIR / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    env["API_MODE"] = "mock" # 為了與測試環境一致，預設使用 mock 模式

    command = [sys.executable, str(orchestrator_script)]
    log.info(f"執行協調器命令: {' '.join(command)}")

    # 我們需要非阻塞地讀取 stdout，以解析 URL
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, # 將 stderr 也導出以利除錯
        text=True,
        encoding='utf-8',
        env=env
    )

    # 從 orchestrator 的 stdout 中解析出 PROXY_URL
    url_pattern = re.compile(r"PROXY_URL:\s*(https?://[^\s]+)")
    server_url = None

    # 設定一個合理的超時，例如 60 秒
    timeout = 60
    start_time = time.time()

    for line in iter(proc.stdout.readline, ''):
        log.info(f"[Orchestrator]: {line.strip()}")
        match = url_pattern.search(line)
        if match:
            server_url = match.group(1)
            log.info(f"✅ 從協調器成功解析到 URL: {server_url}")
            # 注意：我們在這裡不中斷，讓協調器繼續運行
            # 主函式將負責回傳 URL 並保持此程序運行
            return server_url, proc

        if time.time() - start_time > timeout:
            log.error(f"❌ 等待協調器輸出 URL 超時 ({timeout} 秒)。")
            # 關閉超時的進程
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            return None, None

    # 如果迴圈結束（程序終止）但未找到 URL
    log.error("❌ 協調器進程已結束，但未能從其輸出中找到 URL。")
    return None, None

def main():
    """主執行函數"""
    # 步驟 1: 安裝依賴
    if not install_dependencies():
        sys.exit(1) # 如果安裝失敗，則退出

    # 步驟 2: 啟動協調器
    server_url, orchestrator_proc = launch_orchestrator()
    if not server_url or not orchestrator_proc:
        log.critical("❌ 無法啟動主伺服器。")
        sys.exit(1)

    # 步驟 3: 輸出最終 URL 給外部程序 (例如 Colabpro.py 或測試框架)
    # 這是我們與外部世界的「合約」
    log.info("--- [步驟 3/3] 輸出最終 URL ---")
    print(f"FINAL_URL: {server_url}", flush=True)

    # 步驟 4: 等待協調器進程結束
    # 在真實場景中，Colabpro.py 會在接收到 URL 後繼續監控
    # 在這個腳本的獨立執行模式下，我們只需等待它被手動中斷
    try:
        orchestrator_proc.wait()
    except KeyboardInterrupt:
        log.info("收到手動中斷信號，正在關閉協調器...")
        orchestrator_proc.terminate()
        try:
            orchestrator_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            orchestrator_proc.kill()
        log.info("✅ 協調器已關閉。")

if __name__ == "__main__":
    main()
