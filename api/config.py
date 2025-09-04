from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", populate_by_name=True
    )

    PROJECT_NAME: str = "Lumi API"
    PROJECT_VERSION: str = "0.1.0"

    DATABASE_URL: str = Field(..., alias="DATABASE_URL")

    REDIS_URL: str = Field(..., alias="REDIS_URL")

    OPENAI_API_KEY: str = Field(..., alias="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field(..., alias="OPENAI_MODEL")
    EMBEDDING_MODEL_NAME: str = "text-embedding-ada-002"

    WEBHOOK_VERIFY_TOKEN: str = Field(..., alias="WEBHOOK_VERIFY_TOKEN")
    WH_TOKEN: str = Field(..., alias="WH_TOKEN")
    WH_PHONE_ID: str = Field(..., alias="WH_PHONE_ID")

    X_ADMIN_TOKEN: str = Field(..., alias="X_ADMIN_TOKEN")
    SENTRY_DSN: str | None = Field(None, alias="SENTRY_DSN")
    INSTAGRAM_TOKEN: str | None = Field(None, alias="INSTAGRAM_TOKEN")
    TELEGRAM_BOT_TOKEN: str | None = Field(None, alias="TELEGRAM_BOT_TOKEN")

    CORS_ALLOWED_ORIGINS: str = "https://luminiteq.com,https://api.luminiteq.com"

    LOG_LEVEL: str = "INFO"


settings = Settings()  # type: ignore[call-arg]
