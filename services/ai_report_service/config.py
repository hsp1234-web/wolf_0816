from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Google Gemini API 的金鑰
    GEMINI_API_KEY: str = "default_key_if_not_set"

settings = Settings()
