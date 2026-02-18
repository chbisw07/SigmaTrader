import os
import sys
from functools import lru_cache
from pathlib import Path
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

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_ROOT.parent
_ENV_FILES = tuple(
    str(p)
    for p in (
        _REPO_ROOT / ".env",
        _REPO_ROOT / "backend" / ".env",
    )
    if p.exists()
)


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env files."""

    app_name: str = "SigmaTrader API"
    environment: str = "dev"
    debug: bool = True
    version: str = "0.1.0"
    # Keep the default SQLite DB colocated with the backend so it is stable
    # regardless of the process working directory.
    database_url: str = f"sqlite:///{_BACKEND_ROOT / 'sigma_trader.db'}"
    database_echo: bool = False
    zerodha_api_key: str | None = None
    crypto_key: str | None = None
    tradingview_webhook_secret: str | None = None
    admin_username: str | None = None
    admin_password: str | None = None
    enable_legacy_alerts: bool = False
    screener_sync_limit: int = 1000
    canonical_market_data_broker: str = "zerodha"
    instrument_master_sync_interval_hours: int = 24
    smartapi_instrument_master_url: str = (
        "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    )
    # DSL profile controls the allowed function surface when compiling new
    # expressions ("recommended" is intentionally small; "extended" keeps all
    # experimental functions).
    dsl_profile: str = "recommended"  # recommended|extended
    # Managed risk exits (SigmaTrader-managed SL / trailing SL / trailing profit).
    managed_risk_enabled: bool = True
    managed_risk_poll_interval_sec: float = 2.0
    managed_risk_max_per_cycle: int = 200
    # Product-specific risk engine: centralized enforcement for CNC/MIS profiles
    # + drawdown thresholds (enabled via DB-backed Risk Globals).
    # Holdings Exit Automation (new): conservative by default, gated behind a flag.
    holdings_exit_enabled: bool = False
    # Engine poll interval for evaluating subscriptions (seconds).
    holdings_exit_poll_interval_sec: float = 5.0
    # Safety cap for work per cycle to avoid long stalls on large portfolios.
    holdings_exit_max_per_cycle: int = 200
    # Optional allowlist for rollout: comma-separated symbol keys like
    # "NSE:INFY,BSE:TCS" (also accepts bare symbols like "INFY").
    holdings_exit_allowlist_symbols: str | None = None

    # --- AI Trading Manager (feature-flagged; Phase 0 must be merge-safe) ---
    ai_assistant_enabled: bool = False
    ai_execution_enabled: bool = False
    # Hard kill switch: when enabled, blocks any broker-write execution paths even
    # if ai_execution_enabled is true.
    ai_execution_kill_switch: bool = False
    # Phase 3+: allow selecting an AI broker adapter implementation when
    # broker-truth access is enabled (kite_mcp_enabled). Defaults to Zerodha.
    ai_broker_name: str = "zerodha"  # zerodha|angelone
    kite_mcp_enabled: bool = False
    monitoring_enabled: bool = False
    # Public-facing base URL for backend (used to build OAuth callback URLs).
    # Example: https://sigmatrader.in
    backend_base_url: str | None = None

    if SettingsConfigDict is not None:
        # Pydantic v2 / pydantic-settings configuration.
        model_config = SettingsConfigDict(
            env_file=_ENV_FILES or ".env",
            env_file_encoding="utf-8",
            env_prefix="ST_",
            extra="ignore",
        )
    else:  # pragma: no cover - Pydantic v1 configuration

        class Config:
            env_file = _ENV_FILES or ".env"
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

    # Lightweight env override for optional settings backends.
    # When pydantic-settings (or BaseSettings) is unavailable, Settings falls
    # back to BaseModel and does not automatically read env vars. Keep critical
    # settings usable in that mode.
    raw_crypto = os.getenv("ST_CRYPTO_KEY")
    if raw_crypto is not None:
        settings.crypto_key = str(raw_crypto).strip() or None

    raw_tv_secret = os.getenv("ST_TRADINGVIEW_WEBHOOK_SECRET")
    if raw_tv_secret is not None:
        settings.tradingview_webhook_secret = str(raw_tv_secret).strip() or None

    raw_admin_user = os.getenv("ST_ADMIN_USERNAME")
    if raw_admin_user is not None:
        settings.admin_username = str(raw_admin_user).strip() or None

    raw_admin_pass = os.getenv("ST_ADMIN_PASSWORD")
    if raw_admin_pass is not None:
        settings.admin_password = str(raw_admin_pass).strip() or None

    raw_holdings_exit = os.getenv("ST_HOLDINGS_EXIT_ENABLED")
    if raw_holdings_exit is not None:
        settings.holdings_exit_enabled = str(raw_holdings_exit).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    raw_allow = os.getenv("ST_HOLDINGS_EXIT_ALLOWLIST_SYMBOLS")
    if raw_allow is not None:
        settings.holdings_exit_allowlist_symbols = str(raw_allow).strip() or None

    def _parse_bool(name: str) -> bool | None:
        raw = os.getenv(name)
        if raw is None:
            return None
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    # AI Trading Manager flags: keep usable even in the BaseModel fallback where
    # env loading is not automatic.
    raw_ai_assistant = _parse_bool("ST_AI_ASSISTANT_ENABLED")
    if raw_ai_assistant is not None:
        settings.ai_assistant_enabled = raw_ai_assistant

    raw_ai_exec = _parse_bool("ST_AI_EXECUTION_ENABLED")
    if raw_ai_exec is not None:
        settings.ai_execution_enabled = raw_ai_exec

    raw_ai_kill = _parse_bool("ST_AI_EXECUTION_KILL_SWITCH")
    if raw_ai_kill is not None:
        settings.ai_execution_kill_switch = raw_ai_kill

    raw_kite_mcp = _parse_bool("ST_KITE_MCP_ENABLED")
    if raw_kite_mcp is not None:
        settings.kite_mcp_enabled = raw_kite_mcp

    raw_ai_broker = os.getenv("ST_AI_BROKER_NAME")
    if raw_ai_broker is not None:
        settings.ai_broker_name = str(raw_ai_broker).strip().lower() or settings.ai_broker_name

    raw_monitoring = _parse_bool("ST_MONITORING_ENABLED")
    if raw_monitoring is not None:
        settings.monitoring_enabled = raw_monitoring

    raw_poll = os.getenv("ST_HOLDINGS_EXIT_POLL_INTERVAL_SEC")
    if raw_poll is not None:
        try:
            settings.holdings_exit_poll_interval_sec = float(raw_poll)
        except Exception:
            pass

    raw_max = os.getenv("ST_HOLDINGS_EXIT_MAX_PER_CYCLE")
    if raw_max is not None:
        try:
            settings.holdings_exit_max_per_cycle = int(raw_max)
        except Exception:
            pass

    # During pytest runs we want admin-protected APIs to remain easily
    # accessible without configuring HTTP Basic credentials and we do not
    # want to mutate the main development database. Detect the test
    # environment via the presence of pytest in sys.modules (more
    # reliable than PYTEST_CURRENT_TEST during early imports) and also
    # honour PYTEST_CURRENT_TEST for completeness.
    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        settings.admin_username = None
        settings.admin_password = None
        # Ensure auth/session signing works under pytest even when
        # pydantic-settings is unavailable (env loading disabled in fallback).
        settings.crypto_key = settings.crypto_key or "pytest-crypto-key"
        # Keep legacy indicator-alert APIs available under pytest so existing
        # tests can exercise that code path while the product migrates to v3.
        settings.enable_legacy_alerts = True
        # Use an isolated SQLite DB for tests so running pytest does not
        # wipe the primary sigma_trader.db that is used for real data.
        settings.database_url = f"sqlite:///{_BACKEND_ROOT / 'sigma_trader_test.db'}"

    return settings


__all__ = ["Settings", "get_settings"]
