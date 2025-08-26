# -*- coding: utf-8 -*-
"""
善狼專案 - 背景依賴安裝器 (Background Installer)

核心職責：
1.  **解析模式**：根據傳入的 `--light-mode` 參數，決定安裝策略。
2.  **原地安裝**：使用 pip 直接將依賴安裝到環境中，取代舊的 tarball 流程。
3.  **日誌輸出**：向標準輸出 (stdout) 打印詳細、易於理解的進度訊息，供門面伺服器捕獲。
4.  **CPU優先**：確保 PyTorch 安裝的是 CPU 版本，以加快下載和安裝速度。
5.  **啟動主服務**：在所有依賴安裝完成後，啟動真正的後端主服務。
"""
import subprocess
import sys
import os

def get_project_root():
    """獲取專案根目錄的絕對路徑"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def log(message: str):
    """打印日誌訊息並刷新輸出緩衝區，確保即時性"""
    print(f"安裝器：{message}", flush=True)

def run_command(command: list):
    """執行一個子程序命令，並即時打印其輸出"""
    log(f"正在執行命令：{' '.join(command)}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    for line in iter(process.stdout.readline, ''):
        print(line.strip(), flush=True)

    process.wait()
    if process.returncode != 0:
        log(f"命令執行失敗，返回碼：{process.returncode}")
        sys.exit(process.returncode) # 執行失敗則中止腳本

def main():
    """腳本主入口"""
    project_root = get_project_root()
    is_light_mode = "--light-mode" in sys.argv

    log("背景安裝程序已啟動。")

    if is_light_mode:
        log("偵測到 --light-mode，將使用 'requirements-test.txt' 進行安裝。")
        requirements_file = os.path.join(project_root, "requirements-test.txt")
    else:
        log("標準模式，將使用 'requirements-unified.txt' 進行安裝。")
        requirements_file = os.path.join(project_root, "requirements-unified.txt")

    if not os.path.exists(requirements_file):
        log(f"錯誤：依賴檔案 '{requirements_file}' 不存在。")
        sys.exit(1)

    # --- 關鍵步驟：安裝依賴 ---

    # 步驟 1: 強制安裝 CPU 版本的 PyTorch
    # 我們從依賴檔案中單獨挑出 torch 來特別處理
    log("步驟 1/2：正在安裝 PyTorch (CPU 版本)...")
    torch_install_command = [
        sys.executable, "-m", "pip", "install",
        "--progress-bar", "off",
        "torch==2.2.2", # 版本號從依賴檔案中獲取
        "--index-url", "https://download.pytorch.org/whl/cpu"
    ]
    run_command(torch_install_command)
    log("PyTorch (CPU 版本) 安裝完成。")

    # 步驟 2: 安裝其餘的所有依賴
    # 為了確保 torch 不會被從預設的 PyPI 重新安裝，我們從需求檔案中過濾掉它
    log("步驟 2/2：正在安裝其餘依賴...")

    try:
        with open(requirements_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 過濾掉包含 'torch' 的那一行
        filtered_lines = [line for line in lines if 'torch' not in line]

        # 建立一個暫時的依賴檔案
        temp_req_path = os.path.join(os.path.dirname(requirements_file), "temp_requirements.txt")
        with open(temp_req_path, 'w', encoding='utf-8') as f:
            f.writelines(filtered_lines)

        pip_command = [
            sys.executable, "-m", "pip", "install",
            "--progress-bar", "off",
            "-r", temp_req_path
        ]
        run_command(pip_command)
        log("所有依賴均已成功安裝。")

    finally:
        # 清理暫時檔案
        if 'temp_req_path' in locals() and os.path.exists(temp_req_path):
            os.remove(temp_req_path)
            log(f"已清理暫時檔案：{temp_req_path}")

    # --- 啟動主服務 ---
    log("所有依賴安裝完成，正在準備啟動主功能伺服器...")
    main_server_path = os.path.join(project_root, "services", "api_gateway", "main.py")
    if not os.path.exists(main_server_path):
        log(f"錯誤：主服務檔案 '{main_server_path}' 不存在。")
        sys.exit(1)

    # 使用 uvicorn 啟動主服務
    # 注意：這裡的執行會替換當前的程序
    log(f"正在啟動主服務：{main_server_path}")
    os.execvp(
        sys.executable,
        [
            sys.executable, "-m", "uvicorn",
            "services.api_gateway.main:app",
            "--host", "0.0.0.0",
            "--port", "8008" # 使用一個不同於門面伺服器的埠號
        ]
    )


if __name__ == "__main__":
    main()
