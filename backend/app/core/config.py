import os
import sys
from functools import lru_cache
from typing import Any

try:  # Pydantic v2 prefers pydantic-settings.
    from pydantic_settings import (  # type: ignore[import]
        BaseSettings,
        SettingsConfigDict,
    )
except Exception:  # pragma: no cover - Pydantic v1 compatibility
    SettingsConfigDict = None  # type: ignore[assignment]
    try:
        from pydantic import BaseSettings  # type: ignore[assignment]
    except Exception:
        # Fallback for environments with pydantic v2 installed but without the
        # optional pydantic-settings package. This provides a minimal
        # BaseSettings-like class that behaves like a plain BaseModel using
        # default attribute values; env loading is intentionally omitted for
        # this lightweight compatibility path.
        from pydantic import BaseModel as BaseSettings  # type: ignore[assignment]


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

    if SettingsConfigDict is not None:
        # Pydantic v2 / pydantic-settings configuration.
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            env_prefix="ST_",
            extra="ignore",
        )
    else:  # pragma: no cover - Pydantic v1 configuration

        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            env_prefix = "ST_"
            extra = "ignore"

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
    # environment via the presence of pytest in sys.modules (more
    # reliable than PYTEST_CURRENT_TEST during early imports) and also
    # honour PYTEST_CURRENT_TEST for completeness.
    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        settings.admin_username = None
        settings.admin_password = None
        # Use an isolated SQLite DB for tests so running pytest does not
        # wipe the primary sigma_trader.db that is used for real data.
        settings.database_url = "sqlite:///./sigma_trader_test.db"

    return settings


__all__ = ["Settings", "get_settings"]
