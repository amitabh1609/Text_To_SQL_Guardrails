from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    database_url: str = Field(..., alias="DATABASE_URL")

    log_level: str = Field("INFO", alias="LOG_LEVEL")
    max_rows: int = Field(1000, alias="MAX_ROWS")
    back_translation_threshold: float = Field(0.75, alias="BACK_TRANSLATION_THRESHOLD")
    multi_query_enabled: bool = Field(True, alias="MULTI_QUERY_ENABLED")
    llm_model: str = Field("claude-sonnet-4-6", alias="LLM_MODEL")


def get_config() -> AppConfig:
    return AppConfig()
