# -*- coding: utf-8 -*-
"""
善狼專案 - 背景依賴安裝器 (Background Installer) v2

核心職責 (v2 - Refactored by Jules):
1.  **不再讀取 requirements 檔案**，以避免依賴定義分散和過濾邏輯脆弱的問題。
2.  **直接在腳本中定義依賴列表**，使其成為單一事實來源 (Single Source of Truth)。
3.  **使用在 POC 中驗證過的指令**，優先安裝 CPU 版本的 PyTorch，然後再安裝其餘依賴。
4.  **日誌輸出**：向標準輸出 (stdout) 打印詳細、易於理解的進度訊息。
5.  **啟動主服務**：在所有依賴安裝完成後，啟動真正的後端主服務。
"""
import subprocess
import sys
import os

# --- 依賴定義 (單一事實來源) ---

# PyTorch CPU-only 的安裝指令
PYTORCH_CPU_COMMAND = [
    sys.executable, "-m", "pip", "install",
    "torch", "torchvision", "torchaudio",
    "--index-url", "https://download.pytorch.org/whl/cpu"
]

# AI 相關的重量級依賴 (不含 torch)
AI_DEPS = [
    "numpy<2.0",  # 確保版本相容性
    "opencc-python-reimplemented==0.1.7",
    "faster-whisper==0.10.1",
    "ctranslate2>=4.0,<5",
    "huggingface_hub>=0.13",
    "tokenizers>=0.13,<1",
    "onnxruntime>=1.14,<2",
    "av==10.0.0",
    "tqdm"
]

# 系統級依賴 (for av)
SYSTEM_DEPS_COMMAND = [
    "sudo", "apt-get", "install", "-y",
    "python-dev-is-python3",
    "pkg-config",
    "libavformat-dev",
    "libavcodec-dev",
    "libavdevice-dev",
    "libavutil-dev",
    "libswscale-dev",
    "libswresample-dev",
    "libavfilter-dev"
]

# 核心服務依賴
CORE_DEPS = [
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
        sys.exit(process.returncode) # 執行失敗則中止腳本
    log(f"✅ {step_name} 成功")


def main():
    """腳本主入口"""
    project_root = get_project_root()
    is_light_mode = "--light-mode" in sys.argv

    log("背景安裝程序已啟動 (v2 - Refactored by Jules)。")
    if is_light_mode:
        log("偵測到 --light-mode。注意：安裝的套件相同，但主程式應載入輕量模型。")

    # --- 關鍵步驟：安裝依賴 ---
    # 步驟 1: 安裝系統級依賴 (FFmpeg for av)
    run_command(["sudo", "apt-get", "update", "-y"], "步驟 1/5：更新 apt 套件列表")
    run_command(SYSTEM_DEPS_COMMAND, "步驟 2/5：安裝 FFmpeg 開發函式庫")

    # 步驟 2: 強制安裝 CPU 版本的 PyTorch (來自 POC 的驗證結果)
    run_command(PYTORCH_CPU_COMMAND, "步驟 3/5：安裝 PyTorch (CPU 版本)")

    # 步驟 3: 安裝其餘的 AI 依賴
    run_command([sys.executable, "-m", "pip", "install"] + AI_DEPS, "步驟 4/5：安裝 AI 相關依賴")

    # 步驟 4: 安裝核心服務依賴
    run_command([sys.executable, "-m", "pip", "install"] + CORE_DEPS, "步驟 5/5：安裝核心服務依賴")

    log("✅ 所有依賴均已成功安裝。")

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
