# -*- coding: utf-8 -*-
"""
善狼專案 - 背景依賴安裝器 (Background Installer) v3

核心職責 (v3 - Refactored by Jules, guided by user):
1.  **採用兩階段安裝策略**，從根本上解決 PyTorch 版本衝突與系統資源問題。
2.  **階段一：強制安裝 PyTorch CPU 版本**：使用官方的 CPU-only 索引，確保安裝的是輕量級的 PyTorch，避免因下載 CUDA 版本而導致系統掛起。
3.  **階段二：安裝應用依賴**：在 PyTorch 已被正確安裝的前提下，安裝 `faster-whisper>=1.0.0`。這利用了 pip 的依賴解析機制——即然 `torch` 已存在，便不會再次下載。同時，新版 `faster-whisper` 移除了對 `av` 的依賴，解決了其編譯問題。
4.  **啟動主服務**：在所有依賴安裝完成後，啟動真正的後端主服務。
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

def run_command(command: list, step_name: str):
    """執行一個子程序命令，並即時打印其輸出"""
    log(f"--- {step_name} ---")
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
        log(f"❌ 命令執行失敗，返回碼：{process.returncode}")
        sys.exit(process.returncode)
    log(f"✅ {step_name} 成功")

def main():
    """腳本主入口"""
    project_root = get_project_root()
    is_light_mode = "--light-mode" in sys.argv

    log("背景安裝程序已啟動 (v3 - 兩階段安裝策略)。")
    if is_light_mode:
        log("偵測到 --light-mode。")

    # --- 階段一: 強制安裝 PyTorch CPU 版本 ---
    pytorch_cpu_command = [
        sys.executable, "-m", "pip", "install",
        "torch", "torchvision", "torchaudio",
        "--index-url", "https://download.pytorch.org/whl/cpu"
    ]
    run_command(pytorch_cpu_command, "階段 1/2：安裝 PyTorch (CPU 版本)")

    # --- 階段二: 安裝應用程式核心依賴 ---
    # `faster-whisper` 會自動處理 `ctranslate2` 等依賴。
    # 核心服務依賴也一併安裝。
    app_deps = [
        "faster-whisper>=1.0.0",
        "numpy<2.0",
        "opencc-python-reimplemented==0.1.7",
        "tqdm",
        # Core service dependencies
        "fastapi==0.110.0",
        "uvicorn==0.29.0",
        "httpx==0.27.0",
        "python-multipart==0.0.9",
        "pytz==2024.1",
        "jsonpatch==1.33",
        "requests==2.31.0",
        "websockets==12.0",
        "pydantic-settings==2.2.1",
        "psutil==5.9.8",
    ]
    run_command([sys.executable, "-m", "pip", "install"] + app_deps, "階段 2/2：安裝應用程式依賴")

    log("✅ 所有依賴均已成功安裝。")

    # --- 啟動主服務 ---
    log("所有依賴安裝完成，正在準備啟動主功能伺服器...")
    main_server_path = os.path.join(project_root, "services", "api_gateway", "main.py")
    if not os.path.exists(main_server_path):
        log(f"錯誤：主服務檔案 '{main_server_path}' 不存在。")
        sys.exit(1)

    log(f"正在啟動主服務：{main_server_path}")
    os.execvp(
        sys.executable,
        [
            sys.executable, "-m", "uvicorn",
            "services.api_gateway.main:app",
            "--host", "0.0.0.0",
            "--port", "8008"
        ]
    )

if __name__ == "__main__":
    main()
