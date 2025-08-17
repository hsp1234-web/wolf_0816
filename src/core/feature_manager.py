# src/core/feature_manager.py
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Dict, List

log = logging.getLogger('feature_manager')
log.setLevel(logging.INFO)
if not log.handlers:
    log.addHandler(logging.StreamHandler(sys.stdout))

# 以此檔案為基準，定義專案根目錄
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class FeatureManager:
    """
    管理 AI 功能的可用性，並在背景安裝必要的依賴。
    """
    def __init__(self, features: List[str]):
        self.features = {feature: "unavailable" for feature in features}
        self.lock = threading.Lock()
        # 從環境變數讀取模擬延遲，用於測試
        self.mock_delay = int(os.environ.get("MOCK_INSTALL_DELAY", "0"))

    def get_status(self) -> Dict[str, str]:
        """獲取所有功能的當前狀態。"""
        with self.lock:
            return self.features.copy()

    def get_feature_status(self, feature_name: str) -> str:
        """獲取單一功能的狀態。"""
        with self.lock:
            return self.features.get(feature_name, "unknown")

    def _set_status(self, feature: str, status: str):
        """安全地設定功能狀態。"""
        with self.lock:
            if feature in self.features:
                self.features[feature] = status
                log.info(f"功能狀態更新: {feature} -> {status}")

    def _check_and_install(self, feature: str):
        """
        檢查並安裝單一功能的依賴。
        這是一個阻塞操作，應該在單獨的執行緒中執行。
        """
        self._set_status(feature, "installing")
        log.info(f"[{feature}] 開始檢查和安裝...")

        try:
            # 模擬安裝延遲，用於 E2E 測試
            if self.mock_delay > 0:
                log.info(f"[{feature}] 偵測到 MOCK_INSTALL_DELAY，將等待 {self.mock_delay} 秒...")
                time.sleep(self.mock_delay)

            # 根據功能名稱決定要檢查和安裝的套件
            if feature == "whisper":
                # 檢查 whisper 是否已安裝
                # 我們透過嘗試匯入 torch 和 openai-whisper 來判斷
                # 注意：這是一個簡化的檢查
                try:
                    import torch
                    import whisper
                    log.info(f"[{feature}] 依賴 'torch' 和 'whisper' 已存在。")
                except ImportError:
                    log.info(f"[{feature}] 缺少 'torch' 或 'whisper'，開始安裝...")
                    # JULES: 使用 requirements-features.txt 來安裝
                    req_path = os.path.join(ROOT_DIR, 'requirements-features.txt')
                    if not os.path.exists(req_path):
                         raise FileNotFoundError(f"找不到 requirements-features.txt 於 {req_path}")

                    subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', req_path], check=True)
                    log.info(f"[{feature}] 成功從 requirements-features.txt 安裝依賴。")

            elif feature == "ytdlp":
                # 檢查 yt-dlp 是否已安裝
                try:
                    import yt_dlp
                    log.info(f"[{feature}] 依賴 'yt-dlp' 已存在。")
                except ImportError:
                    log.info(f"[{feature}] 缺少 'yt-dlp'，開始安裝...")
                    subprocess.run([sys.executable, '-m', 'pip', 'install', 'yt-dlp'], check=True)
                    log.info(f"[{feature}] 成功安裝 'yt-dlp'。")

            else:
                raise ValueError(f"未知的 feature: {feature}")

            self._set_status(feature, "ready")

        except Exception as e:
            log.error(f"[{feature}] 安裝過程中發生錯誤: {e}", exc_info=True)
            self._set_status(feature, "failed")

    def initialize_features(self):
        """
        為每個功能啟動一個背景執行緒來進行檢查和安裝。
        """
        log.info("開始初始化所有 AI 功能...")
        for feature in self.features.keys():
            thread = threading.Thread(target=self._check_and_install, args=(feature,))
            thread.daemon = True
            thread.start()

# 為應用程式建立一個 FeatureManager 的單例
# 我們在此處定義應用程式所需的核心 AI 功能
feature_manager = FeatureManager(features=["whisper", "ytdlp"])
