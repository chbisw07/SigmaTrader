import os
from functools import lru_cache
from typing import Any

from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env files."""

    app_name: str = "SigmaTrader API"
    environment: str = "dev"
    debug: bool = True
    version: str = "0.1.0"
    database_url: str = "sqlite:///./sigma_trader.db"
    database_echo: bool = False
    zerodha_api_key: str | None = None
    crypto_key: str | None = None
    tradingview_webhook_secret: str | None = None
    admin_username: str | None = None
    admin_password: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "ST_"

    def dict_for_logging(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "environment": self.environment,
            "debug": self.debug,
            "version": self.version,
            "database_url": self.database_url,
        }


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""

    settings = Settings()

    # During pytest runs we want admin-protected APIs to remain easily
    # accessible without configuring HTTP Basic credentials and we do not
    # want to mutate the main development database. Detect the test
    # environment via PYTEST_CURRENT_TEST and adjust settings accordingly.
    if os.getenv("PYTEST_CURRENT_TEST"):
        settings.admin_username = None
        settings.admin_password = None
        # Use an isolated SQLite DB for tests so running pytest does not
        # wipe the primary sigma_trader.db that is used for real data.
        settings.database_url = "sqlite:///./sigma_trader_test.db"

    return settings


__all__ = ["Settings", "get_settings"]
