from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    PROJECT_NAME: str = "Lumi API"
    PROJECT_VERSION: str = "0.1.0"

    DATABASE_URL: str

    REDIS_URL: str

    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    AI_REQUEST_TIMEOUT_SECONDS: float = 30.0
    AI_MAX_TOKENS_COMPLETION: int = 512
    AI_TEMPERATURE: float = 0.2
    AI_ENABLE: bool | None = None
    OPENAI_BASE_URL: str | None = None

    VERIFY_TOKEN: str
    WH_TOKEN: str
    WH_PHONE_ID: str

    X_ADMIN_TOKEN: str

    CORS_ALLOWED_ORIGINS: str = "https://luminiteq.com,https://api.luminiteq.com"

    LOG_LEVEL: str = "INFO"


settings = Settings()  # type: ignore[call-arg]
