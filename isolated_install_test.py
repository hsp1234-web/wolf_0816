# -*- coding: utf-8 -*-
"""
隔離依賴安裝測試腳本

目的：
在一個完全乾淨、隔離的虛擬環境中，驗證核心 AI 依賴的安裝流程。
使用 uv 來加速安裝過程。

步驟：
1. 建立一個臨時的虛擬環境。
2. 在虛擬環境中安裝 uv。
3. 使用 uv 依序安裝：
    a. Cython<3.0 和 wheel
    b. PyTorch (CPU 版本)
    c. 專案的 AI 相關依賴 (av, faster-whisper, etc.)
4. 報告成功或失敗，並在結束時清理環境。
"""
import subprocess
import sys
import os
import shutil
import uuid

# --- 設定 ---
LOG_PREFIX = "[隔離測試]"
VENV_DIR = f"/tmp/isolated_test_venv_{uuid.uuid4()}"

# --- 依賴定義 ---
PYTORCH_CPU_COMMAND = [
    "torch", "torchvision", "torchaudio",
    "--index-url", "https://download.pytorch.org/whl/cpu"
]
CYTHON_DEPS = ["cython<3.0", "wheel"]
AI_DEPS = [
    "numpy<2.0",
    "opencc-python-reimplemented==0.1.7",
    "faster-whisper==0.10.1",
    "ctranslate2>=4.0,<5",
    "huggingface_hub>=0.13",
    "tokenizers>=0.13,<1",
    "onnxruntime>=1.14,<2",
    "av==10.0.0",
    "tqdm"
]

def log(message):
    """打印日誌訊息"""
    print(f"{LOG_PREFIX} {message}", flush=True)

def run_command(command, step_name, env=None):
    """執行命令並記錄日誌"""
    log(f"--- {step_name} ---")
    log(f"執行中: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        env=env
    )
    for line in iter(process.stdout.readline, ''):
        print(line.strip(), flush=True)

    process.wait()
    if process.returncode != 0:
        log(f"❌ 命令執行失敗，返回碼：{process.returncode}")
        return False
    log(f"✅ {step_name} 成功")
    return True

def main():
    """主執行函數"""
    log("隔離依賴安裝測試已啟動。")

    # --- 步驟 1: 建立虛擬環境 ---
    if not run_command([sys.executable, "-m", "venv", VENV_DIR], "步驟 1/5：建立虛擬環境"):
        sys.exit(1)

    venv_python = os.path.join(VENV_DIR, "bin", "python")
    venv_pip = os.path.join(VENV_DIR, "bin", "pip")
    venv_uv = os.path.join(VENV_DIR, "bin", "uv")

    # 設定環境變數以供 uv 使用
    uv_env = os.environ.copy()
    uv_env["VIRTUAL_ENV"] = VENV_DIR

    try:
        # --- 步驟 2: 安裝 uv ---
        if not run_command([venv_pip, "install", "uv"], "步驟 2/5：安裝 uv"):
            sys.exit(1)

        # --- 步驟 3: 安裝 Cython ---
        if not run_command([venv_uv, "pip", "install"] + CYTHON_DEPS, "步驟 3/5：使用 uv 安裝 Cython", env=uv_env):
            sys.exit(1)

        # --- 步驟 4: 安裝 PyTorch ---
        if not run_command([venv_uv, "pip", "install"] + PYTORCH_CPU_COMMAND, "步驟 4/5：使用 uv 安裝 PyTorch (CPU)", env=uv_env):
            sys.exit(1)

        # --- 步驟 5: 安裝 AI 依賴 ---
        if not run_command([venv_uv, "pip", "install"] + AI_DEPS, "步驟 5/5：使用 uv 安裝核心 AI 依賴", env=uv_env):
            sys.exit(1)

        log("🎉🎉🎉 隔離依賴安裝測試成功！所有套件均已正確安裝。 🎉🎉🎉")
        exit_code = 0

    except SystemExit as e:
        log("🔥🔥🔥 隔離依賴安裝測試失敗。 🔥🔥🔥")
        exit_code = e.code

    finally:
        # --- 清理 ---
        log(f"正在清理虛擬環境: {VENV_DIR}")
        shutil.rmtree(VENV_DIR)
        log("清理完畢。")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
