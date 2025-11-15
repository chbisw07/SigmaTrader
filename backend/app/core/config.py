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
    tradingview_webhook_secret: str | None = None

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

    return Settings()


__all__ = ["Settings", "get_settings"]
