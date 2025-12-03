"""Configuration settings via pydantic-settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Snowflake
    snowflake_account: str
    snowflake_user: str
    snowflake_password: Optional[str] = None
    snowflake_private_key_path: Optional[str] = None
    snowflake_private_key_passphrase: Optional[str] = None
    snowflake_warehouse: str = "COMPUTE_WH"
    snowflake_database: str = "DEPLOYMENTS_DB"
    snowflake_schema: str = "PUBLIC"

    # Authentication
    auth_enabled: bool = True
    github_oidc_issuer: str = "https://token.actions.githubusercontent.com"
    github_oidc_audience: str = "deployment-queue-api"

    # GitHub API (for CLI auth)
    github_api_url: str = "https://api.github.com"
    github_api_version: str = "2022-11-28"

    # Optional: Restrict to specific orgs (comma-separated)
    allowed_organisations: Optional[str] = None

    # For local development with auth disabled
    dev_organisation: str = "local-dev"

    # Cache TTLs (seconds)
    jwks_cache_ttl: int = 3600  # 1 hour
    org_membership_cache_ttl: int = 300  # 5 minutes

    # Server ports
    api_port: int = 8000
    management_port: int = 9090

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]
