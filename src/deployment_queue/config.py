"""Configuration settings via pydantic-settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    snowflake_account: str
    snowflake_user: str
    snowflake_password: Optional[str] = None
    snowflake_private_key_path: Optional[str] = None
    snowflake_private_key_passphrase: Optional[str] = None
    snowflake_warehouse: str = "COMPUTE_WH"
    snowflake_database: str = "DEPLOYMENTS_DB"
    snowflake_schema: str = "PUBLIC"

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]
