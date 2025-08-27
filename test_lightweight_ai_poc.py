import subprocess
import sys
import time

# ==============================================================================
#  POC 腳本：輕量級 AI 依賴安裝與驗證
# ==============================================================================
#
# **目的**:
# 此腳本旨在建立一個最小化、可重現的測試案例，用於驗證啟動「門面伺服器」
# 及其間接依賴（如 `transcriber` 模組）所需的所有 Python 套件。
# 我們將在此處調試並確認一份「黃金依賴列表」，成功後再應用於主專案。
#
# **方法**:
# 1. 定義一份完整的依賴列表。
# 2. 使用 subprocess 呼叫 pip 來安裝它們。
# 3. 嘗試 import 關鍵函式庫來驗證安裝是否成功。
# 4. 不依賴任何外部專案檔案，完全自足。
#
# ==============================================================================

# 這是我們根據錯誤日誌和 `faster-whisper` 原始碼分析得出的完整依賴列表
# 我們將驗證這個列表是否能成功安裝並解決問題
DEPENDENCIES = [
    # --- 基礎伺服器需求 ---
    "fastapi==0.110.0",
    "uvicorn==0.29.0",
    "websockets==12.0",

    # --- 為了解決 NumPy 2.0 衝突 ---
    "numpy<2.0",

    # --- 轉錄模組 (transcriber) 的直接依賴 ---
    "torch",
    "opencc-python-reimplemented",
    "faster-whisper",

    # --- `faster-whisper` 的間接依賴 (來自其 requirements.txt) ---
    "ctranslate2>=4.0,<5",
    "huggingface_hub>=0.13",
    "tokenizers>=0.13,<1",
    "onnxruntime>=1.14,<2",
    "av>=11",
    "tqdm",
]

def log(level, message):
    """簡單的日誌函式"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    print(f"[{timestamp}] [{level.upper()}] {message}")

def install_dependencies():
    """使用 pip 安裝所有定義的依賴"""
    log("info", "準備開始安裝所有依賴...")
    for dep in DEPENDENCIES:
        log("info", f"--> 正在安裝: {dep}")
        try:
            # 使用 --no-cache-dir 確保每次都是乾淨的安裝
            # 使用 -q 減少不必要的日誌輸出
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", dep],
                check=True,
                capture_output=True, # 捕獲輸出以便在出錯時顯示
                text=True
            )
            log("success", f"✅ 成功安裝: {dep}")
        except subprocess.CalledProcessError as e:
            log("error", f"❌ 安裝失敗: {dep}")
            log("error", f"PIP STDOUT: {e.stdout}")
            log("error", f"PIP STDERR: {e.stderr}")
            return False
    log("success", "所有依賴均已成功安裝！")
    return True

def verify_imports():
    """嘗試導入關鍵函式庫以驗證安裝"""
    log("info", "準備開始驗證關鍵函式庫的導入...")

    key_libraries = [
        "fastapi",
        "uvicorn",
        "websockets",
        "numpy",
        "opencc",
        "torch",
        "faster_whisper",
        "ctranslate2",
        "huggingface_hub",
        "tokenizers",
        "onnxruntime",
        "av",
        "tqdm",
    ]

    for lib in key_libraries:
        try:
            log("info", f"--> 正在嘗試導入: {lib}")
            __import__(lib)
            log("success", f"✅ 成功導入: {lib}")
        except ImportError as e:
            log("error", f"❌ 導入失敗: {lib}")
            log("error", f"錯誤訊息: {e}")
            return False

    log("success", "所有關鍵函式庫均已成功導入！")
    return True

if __name__ == "__main__":
    start_time = time.time()
    log("info", "--- 輕量級 AI 依賴 POC 腳本開始執行 ---")

    if not install_dependencies():
        log("critical", "依賴安裝階段失敗，POC 終止。")
        sys.exit(1)

    if not verify_imports():
        log("critical", "函式庫導入驗證階段失敗，POC 終止。")
        sys.exit(1)

    end_time = time.time()
    log("success", "🎉 POC 成功！所有依賴均已成功安裝和驗證。")
    log("info", f"總耗時: {end_time - start_time:.2f} 秒")
    sys.exit(0)
