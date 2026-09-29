from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration settings."""

    app_name: str = "ChameleonOS"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False
    
    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000

    # Database configuration (SQLite default)
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'chameleon.db'}"

    # Security
    secret_key: str = "chameleonos-secret-key-change-in-production"

    # API configuration
    api_v1_str: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
