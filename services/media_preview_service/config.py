from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # 可預覽媒體檔案的根目錄
    MEDIA_ROOT_DIR: Path = Path("uploads")

settings = Settings()
