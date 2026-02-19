from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = BASE_DIR / "config"


class AppConfig(BaseModel):
    brokers: list[str] = ["zerodha"]
    default_broker: str = "zerodha"


class KiteConnectSection(BaseModel):
    api_key: str
    api_secret: str


class KiteConfig(BaseModel):
    kite_connect: KiteConnectSection


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Invalid JSON in config file {path}: {exc}") from exc


def get_config_dir() -> Path:
    """Return the directory containing JSON config files.

    Uses ST_CONFIG_DIR if set, otherwise defaults to backend/config.
    """

    override = os.getenv("ST_CONFIG_DIR")
    if override:
        return Path(override)
    return DEFAULT_CONFIG_DIR


def load_app_config() -> AppConfig:
    """Load global application config from config.json."""

    path = get_config_dir() / "config.json"
    # When config.json is absent we can safely fall back to defaults; this keeps
    # local dev and pytest runs resilient while still allowing explicit configs.
    if not path.exists():
        return AppConfig()
    data = _load_json(path)
    try:
        return AppConfig(**data)
    except ValidationError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Invalid app config in {path}: {exc}") from exc


def load_kite_config() -> KiteConfig:
    """Load Zerodha Kite configuration from kite_config.json."""

    path = get_config_dir() / "kite_config.json"
    data = _load_json(path)
    try:
        return KiteConfig(**data)
    except ValidationError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Invalid kite config in {path}: {exc}") from exc


def load_zerodha_symbol_map() -> dict[str, dict[str, str]]:
    """Load Zerodha symbol mapping config, if present.

    The expected shape is::

        {
          "NSE": {
            "SCHNEIDER": "SCHNEIDER-EQ"
          },
          "BSE": {
            ...
          }
        }

    Keys are case-insensitive exchange and symbol codes. When the file does
    not exist we return an empty mapping so that callers can safely fall
    back to a 1:1 TradingView → broker symbol assumption.
    """

    path = get_config_dir() / "zerodha_symbol_map.json"
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Invalid JSON in config file {path}: {exc}") from exc

    result: dict[str, dict[str, str]] = {}
    for exch, symbols in raw.items():
        if not isinstance(symbols, dict):
            continue
        exch_norm = str(exch).upper()
        inner: dict[str, str] = {}
        for sym, mapped in symbols.items():
            inner[str(sym).upper()] = str(mapped)
        result[exch_norm] = inner
    return result


__all__ = [
    "AppConfig",
    "KiteConfig",
    "load_app_config",
    "load_kite_config",
    "load_zerodha_symbol_map",
]
