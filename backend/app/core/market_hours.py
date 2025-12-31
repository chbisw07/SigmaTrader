from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Set

from app.config_files import get_config_dir

IST_OFFSET = timedelta(hours=5, minutes=30)


def _now_ist() -> datetime:
    """Return current time in IST as a timezone-aware datetime."""

    utc_now = datetime.now(UTC)
    return utc_now + IST_OFFSET


@lru_cache(maxsize=1)
def _load_indian_holidays() -> Set[str]:
    """Load a simple holiday calendar for Indian markets.

    The expected JSON shape is either:
    - A dict mapping YYYY-MM-DD -> description, or
    - A list of YYYY-MM-DD strings.

    When the file is missing or invalid, an empty set is returned so
    that the app falls back to weekday/time-based rules.
    """

    path: Path = get_config_dir() / "indian_holidays.json"
    if not path.exists():
        return set()

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError:
        return set()

    dates: Set[str] = set()
    if isinstance(raw, dict):
        dates.update(str(d) for d in raw.keys())
    elif isinstance(raw, list):
        dates.update(str(d) for d in raw)
    return dates


def is_market_open_now() -> bool:
    """Return True if Indian cash market (NSE/BSE) is considered open.

    Rules (v1):
    - Timezone: IST (UTC+5:30).
    - Weekends (Saturday/Sunday) are always closed.
    - Holidays are read from indian_holidays.json when present.
    - Trading session: 09:15–15:30 IST inclusive.

    MIS auto square-off at 15:20 is not modelled explicitly yet; we
    treat the market as open until 15:30 for both MIS and CNC.
    """

    now_ist = _now_ist()

    # Weekends
    if now_ist.weekday() >= 5:
        return False

    # Holidays
    if now_ist.date().isoformat() in _load_indian_holidays():
        return False

    # Session window
    minutes = now_ist.hour * 60 + now_ist.minute
    start = 9 * 60 + 15  # 09:15
    end = 15 * 60 + 30  # 15:30
    if minutes < start or minutes > end:
        return False

    return True


def is_preopen_now(now_ist: datetime | None = None) -> bool:
    """Return True if Indian pre-open session is currently active.

    Pre-open session (cash market): 09:00–09:15 IST (end-exclusive).
    This is useful for fetching indicative prices before continuous trading
    begins.
    """

    current = now_ist or _now_ist()

    # Weekends
    if current.weekday() >= 5:
        return False

    # Holidays
    if current.date().isoformat() in _load_indian_holidays():
        return False

    minutes = current.hour * 60 + current.minute
    start = 9 * 60  # 09:00
    end = 9 * 60 + 15  # 09:15 (exclusive)
    return start <= minutes < end


__all__ = ["is_market_open_now", "is_preopen_now"]
