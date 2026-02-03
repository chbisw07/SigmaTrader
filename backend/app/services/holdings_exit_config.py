from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.crypto import decrypt_token, encrypt_token
from app.models import BrokerSecret

HOLDINGS_EXIT_BROKER_NAME = "holdings_exit"
HOLDINGS_EXIT_CONFIG_KEY = "holdings_exit_config"

HoldingsExitConfigSource = Literal["db", "env_default", "db_invalid"]


@dataclass(frozen=True)
class HoldingsExitConfig:
    enabled: bool = False
    allowlist_symbols: str | None = None  # CSV: "NSE:INFY,BSE:TCS" or "INFY"

    @classmethod
    def from_dict(
        cls,
        raw: dict[str, Any] | None,
        *,
        env_defaults: "HoldingsExitConfig" | None = None,
    ) -> "HoldingsExitConfig":
        raw = raw or {}
        defaults = env_defaults or HoldingsExitConfig()

        enabled_raw = raw.get("enabled", defaults.enabled)
        enabled = bool(enabled_raw)

        allowlist_raw = raw.get("allowlist_symbols", defaults.allowlist_symbols)
        allowlist = str(allowlist_raw).strip() if allowlist_raw is not None else None
        if allowlist == "":
            allowlist = None

        return cls(enabled=enabled, allowlist_symbols=allowlist)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "allowlist_symbols": (self.allowlist_symbols or "").strip() or None,
        }


def get_holdings_exit_config_with_source(
    db: Session,
    settings: Settings,
) -> tuple[HoldingsExitConfig, HoldingsExitConfigSource]:
    """Return (config, source).

    Precedence:
    - DB override (BrokerSecret broker=holdings_exit key=holdings_exit_config, user_id=None)
    - Environment defaults via Settings (ST_HOLDINGS_EXIT_ENABLED/ST_HOLDINGS_EXIT_ALLOWLIST_SYMBOLS)
    """

    env_defaults = HoldingsExitConfig(
        enabled=bool(getattr(settings, "holdings_exit_enabled", False)),
        allowlist_symbols=str(getattr(settings, "holdings_exit_allowlist_symbols", "") or "")
        or None,
    )

    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == HOLDINGS_EXIT_BROKER_NAME,
            BrokerSecret.key == HOLDINGS_EXIT_CONFIG_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        return env_defaults, "env_default"

    try:
        raw = decrypt_token(settings, row.value_encrypted)
        parsed = json.loads(raw) if raw else {}
        if not isinstance(parsed, dict):
            parsed = {}
        return HoldingsExitConfig.from_dict(parsed, env_defaults=env_defaults), "db"
    except Exception:
        # Fail closed: do not allow the feature to run when the DB override is corrupt.
        return HoldingsExitConfig(enabled=False, allowlist_symbols=None), "db_invalid"


def set_holdings_exit_config(
    db: Session,
    settings: Settings,
    config: HoldingsExitConfig,
) -> BrokerSecret:
    payload = json.dumps(config.to_dict(), ensure_ascii=False)
    encrypted = encrypt_token(settings, payload)

    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == HOLDINGS_EXIT_BROKER_NAME,
            BrokerSecret.key == HOLDINGS_EXIT_CONFIG_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        row = BrokerSecret(
            user_id=None,
            broker_name=HOLDINGS_EXIT_BROKER_NAME,
            key=HOLDINGS_EXIT_CONFIG_KEY,
            value_encrypted=encrypted,
        )
        db.add(row)
    else:
        row.value_encrypted = encrypted
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


__all__ = [
    "HOLDINGS_EXIT_BROKER_NAME",
    "HOLDINGS_EXIT_CONFIG_KEY",
    "HoldingsExitConfig",
    "HoldingsExitConfigSource",
    "get_holdings_exit_config_with_source",
    "set_holdings_exit_config",
]

