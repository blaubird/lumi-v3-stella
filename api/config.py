from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    PROJECT_NAME: str = "Lumi API"
    PROJECT_VERSION: str = "0.1.0"

    DATABASE_URL: str

    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "ft:gpt-4.1-nano-2025-04-14:luminiteq:flora:Bdezn8Rp"
    EMBEDDING_MODEL_NAME: str = "text-embedding-ada-002"

    VERIFY_TOKEN: str
    WH_TOKEN: str
    WH_PHONE_ID: str

    X_ADMIN_TOKEN: str

    CORS_ALLOWED_ORIGINS: str = "https://luminiteq.com,https://api.luminiteq.com"

    LOG_LEVEL: str = "INFO"


settings = Settings()  # type: ignore[call-arg]
