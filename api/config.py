from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    PROJECT_NAME: str = "Lumi API"
    PROJECT_VERSION: str = "0.1.0"

    DATABASE_URL: str = Field(..., alias="DATABASE_URL")

    REDIS_URL: str = Field(..., alias="REDIS_URL")

    OPENAI_API_KEY: str = Field(..., alias="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field(..., alias="OPENAI_MODEL")
    EMBEDDING_MODEL_NAME: str = Field("text-embedding-ada-002", alias="EMBEDDING_MODEL_NAME")

    WEBHOOK_VERIFY_TOKEN: str = Field(..., alias="WEBHOOK_VERIFY_TOKEN")
    WH_TOKEN: str = Field(..., alias="WH_TOKEN")
    WH_PHONE_ID: str = Field(..., alias="WH_PHONE_ID")

    X_ADMIN_TOKEN: str = Field(..., alias="X_ADMIN_TOKEN")
    SENTRY_DSN: str | None = Field(default=None, alias="SENTRY_DSN")

    CORS_ALLOWED_ORIGINS: str = Field(
        "https://luminiteq.com,https://api.luminiteq.com", alias="CORS_ALLOWED_ORIGINS"
    )

    LOG_LEVEL: str = Field("INFO", alias="LOG_LEVEL")


settings = Settings()  # type: ignore[call-arg]
