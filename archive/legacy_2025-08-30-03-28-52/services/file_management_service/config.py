# services/file_management_service/config.py
# 使用 Pydantic-Settings 來管理設定

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    定義服務的設定模型。
    Pydantic 會自動從 .env 檔案或環境變數中讀取這些值。
    """
    # 設定 .env 檔案的路徑和編碼
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # 上傳檔案的儲存目錄
    UPLOADS_DIR: str = "uploads"

# 建立一個全域可用的設定實例
settings = Settings()
