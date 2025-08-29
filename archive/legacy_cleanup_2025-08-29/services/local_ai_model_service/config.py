# services/local_ai_model_service/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    定義服務的設定模型。
    """
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # 模型快取目錄
    MODEL_CACHE_DIR: str = "models"

settings = Settings()
