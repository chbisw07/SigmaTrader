from __future__ import annotations

from datetime import UTC, datetime

from app.core.market_hours import IST_OFFSET


def utc_now() -> datetime:
    return datetime.now(UTC)


def ist_naive_to_utc(dt_ist: datetime) -> datetime:
    """Convert an IST-naive datetime into a tz-aware UTC datetime."""

    if dt_ist.tzinfo is not None:
        return dt_ist.astimezone(UTC)
    return (dt_ist - IST_OFFSET).replace(tzinfo=UTC)


def to_utc(dt: datetime, *, assume_ist_if_naive: bool = True) -> datetime:
    """Return tz-aware UTC for any datetime.

    - tz-aware inputs are converted to UTC.
    - tz-naive inputs are treated as IST by default (common for UI inputs and
      market-data timestamps in this repo), then converted to UTC.
    """

    if dt.tzinfo is None:
        if assume_ist_if_naive:
            return ist_naive_to_utc(dt)
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_utc_or_none(
    dt: datetime | None,
    *,
    assume_ist_if_naive: bool = True,
) -> datetime | None:
    if dt is None:
        return None
    return to_utc(dt, assume_ist_if_naive=assume_ist_if_naive)
