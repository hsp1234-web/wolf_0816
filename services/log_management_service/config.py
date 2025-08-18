# services/log_management_service/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    定義服務的設定模型。
    """
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # 存放日誌檔案的路徑
    LOG_FILE_PATH: str = "logs/service.log"

settings = Settings()
