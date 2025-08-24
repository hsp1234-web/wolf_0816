import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    """
    管理 API 閘道器的所有設定。
    會從 .env 檔案和環境變數中讀取設定。
    """
    # model_config 的 'extra' 設為 'ignore' 可以避免 .env 中有多餘變數時 pydantic 報錯
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # 定義 API 運作模式，'real' 為真實模式，'mock' 為模擬模式
    # 使用 Literal 來限制變數的可能值
    API_MODE: Literal['real', 'mock'] = "real"

    # 上傳檔案的儲存目錄
    # 根據 AGENTS.md 的安全準則，我們使用一個已存在的目錄來避免建立新目錄。
    UPLOADS_DIR: str = "youtube_downloads"

    @property
    def is_mock_mode(self) -> bool:
        """
        一個方便的屬性，用於判斷目前是否為模擬模式。
        """
        return self.API_MODE == "mock"

# 建立一個全域的設定實例，供應用程式的其他部分使用
settings = Settings()

# 為了方便本地測試，可以在此處印出設定
if __name__ == "__main__":
    print("--- API 閘道器設定 ---")
    print(f"API 模式 (API_MODE): {settings.API_MODE}")
    print(f"是否為模擬模式 (is_mock_mode): {settings.is_mock_mode}")
    print("--------------------------")
