from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Core application settings
    PROJECT_NAME: str = "Lumi API"
    PROJECT_VERSION: str = "0.1.0"
    
    # Database settings
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    
    # OpenAI settings
    OPENAI_API_KEY: str = Field(..., env="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field("ft:gpt-4.1-nano-2025-04-14:luminiteq:flora:Bdezn8Rp", env="OPENAI_MODEL")
    EMBEDDING_MODEL_NAME: str = "text-embedding-ada-002"
    
    # WhatsApp Business API settings
    VERIFY_TOKEN: str = Field(..., env="VERIFY_TOKEN")
    WH_TOKEN: str = Field(..., env="WH_TOKEN")
    WH_PHONE_ID: str = Field(..., env="WH_PHONE_ID")
    
    # Admin settings
    X_ADMIN_TOKEN: str = Field(..., env="X_ADMIN_TOKEN")
    
    # CORS settings
    CORS_ALLOWED_ORIGINS: str = Field("https://luminiteq.com,https://api.luminiteq.com", env="CORS_ALLOWED_ORIGINS")
    
    # Logging settings
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Initialize settings
settings = Settings()


