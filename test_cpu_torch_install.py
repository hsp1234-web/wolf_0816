import subprocess
import sys
import time
import logging

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('CPU安裝測試')

# --- 依賴列表 ---
# 這次，我們將 PyTorch 相關的分開處理
BASE_DEPS = [
    "numpy<2.0",
    "opencc-python-reimplemented",
    "faster-whisper",
    "ctranslate2>=4.0,<5",
    "huggingface_hub>=0.13",
    "tokenizers>=0.13,<1",
    "onnxruntime>=1.14,<2", # faster-whisper 可能需要 onnxruntime
    "av>=11",
    "tqdm",
]

# PyTorch CPU-only 的安裝指令
# 我們將 torch, torchvision, torchaudio 一起安裝，因為它們通常是協同工作的
PYTORCH_CPU_COMMAND = [
    sys.executable, "-m", "pip", "install",
    "torch", "torchvision", "torchaudio",
    "--index-url", "https://download.pytorch.org/whl/cpu"
]


def execute_pip_install(command, step_name):
    """執行一個 pip 安裝指令並記錄日誌"""
    log.info(f"--- {step_name} ---")
    log.info(f"執行中: {' '.join(command)}")
    try:
        process = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        log.info(f"STDOUT: {process.stdout}")
        if process.stderr:
            log.warning(f"STDERR: {process.stderr}")
        log.info(f"✅ {step_name} 成功")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ {step_name} 失敗！")
        log.error(f"返回碼: {e.returncode}")
        log.error(f"--- STDOUT ---")
        log.error(e.stdout)
        log.error(f"--- STDERR ---")
        log.error(e.stderr)
        log.error("----------------")
        return False

def run_cpu_install_poc():
    """主 POC 執行函數"""
    log.info("--- CPU 版本 PyTorch 安裝 POC 開始 ---")

    # 步驟 1: 安裝 PyTorch CPU 版本
    if not execute_pip_install(PYTORCH_CPU_COMMAND, "安裝 PyTorch CPU-only"):
        return False

    # 步驟 2: 安裝其餘的依賴
    # 將基礎依賴列表轉換為 pip install 指令
    pip_command = [sys.executable, "-m", "pip", "install"] + BASE_DEPS
    if not execute_pip_install(pip_command, "安裝其餘基礎依賴"):
        return False

    # 步驟 3: 驗證導入
    log.info("--- 驗證導入 ---")
    try:
        import torch
        import faster_whisper
        log.info("✅ torch 和 faster_whisper 導入成功！")
        # 額外驗證：檢查 torch 是否真的是 CPU 版本
        if torch.cuda.is_available():
            log.warning("⚠️ 警告：torch.cuda.is_available() 返回 True，可能安裝的不是純 CPU 版本。")
        else:
            log.info("✅ torch.cuda.is_available() 返回 False，確認為 CPU 版本。")

    except ImportError as e:
        log.error(f"❌ 導入驗證失敗: {e}")
        return False

    log.info("🎉 POC 成功！已成功安裝 CPU 版本的 PyTorch 及其相關依賴。")
    return True


if __name__ == "__main__":
    start_time = time.time()
    success = run_cpu_install_poc()
    end_time = time.time()

    log.info(f"總耗時: {end_time - start_time:.2f} 秒")
    if success:
        log.info("POC 執行成功。")
        sys.exit(0)
    else:
        log.error("POC 執行失敗。")
        sys.exit(1)
