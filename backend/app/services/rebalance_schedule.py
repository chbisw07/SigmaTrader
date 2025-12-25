from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import HTTPException, status

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - very old Python fallback
    ZoneInfo = None  # type: ignore[assignment]


ScheduleFrequency = Literal["WEEKLY", "MONTHLY", "QUARTERLY", "CUSTOM_DAYS"]
RollToTradingDay = Literal["NEXT", "PREV", "NONE"]


@dataclass(frozen=True)
class RebalanceScheduleConfig:
    frequency: ScheduleFrequency = "MONTHLY"
    time_local: str = "15:10"  # HH:MM
    timezone: str = "Asia/Kolkata"

    weekday: int | None = 4  # Monday=0 ... Sunday=6 (default Friday)
    day_of_month: int | Literal["LAST"] | None = "LAST"
    interval_days: int | None = 30

    roll_to_trading_day: RollToTradingDay = "NEXT"


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_load(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except Exception:
        return {}
    return val if isinstance(val, dict) else {}


def _parse_hhmm(raw: str) -> tuple[int, int]:
    s = (raw or "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if not m:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="time_local must be in HH:MM format.",
        )
    hh = int(m.group(1))
    mm = int(m.group(2))
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="time_local must be a valid 24h time.",
        )
    return hh, mm


def _get_tz(name: str):
    if ZoneInfo is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Timezone support is not available in this Python runtime.",
        )
    tz_name = (name or "").strip() or "Asia/Kolkata"
    try:
        return ZoneInfo(tz_name)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timezone: {tz_name}",
        ) from exc


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day


def _roll_weekend(dt_local: datetime, roll: RollToTradingDay) -> datetime:
    if roll == "NONE":
        return dt_local
    wd = dt_local.weekday()
    if wd <= 4:
        return dt_local
    if roll == "NEXT":
        # Saturday -> +2, Sunday -> +1
        delta = 7 - wd
        return dt_local + timedelta(days=delta)
    if roll == "PREV":
        # Saturday -> -1, Sunday -> -2
        delta = wd - 4
        return dt_local - timedelta(days=delta)
    return dt_local


def normalize_schedule_config(raw: dict[str, Any] | None) -> RebalanceScheduleConfig:
    data = raw or {}

    freq = str(data.get("frequency") or "MONTHLY").strip().upper()
    if freq not in {"WEEKLY", "MONTHLY", "QUARTERLY", "CUSTOM_DAYS"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="frequency must be WEEKLY, MONTHLY, QUARTERLY, or CUSTOM_DAYS.",
        )

    time_local = str(data.get("time_local") or "15:10").strip()
    _parse_hhmm(time_local)

    tz = str(data.get("timezone") or "Asia/Kolkata").strip() or "Asia/Kolkata"

    roll = str(data.get("roll_to_trading_day") or "NEXT").strip().upper()
    if roll not in {"NEXT", "PREV", "NONE"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="roll_to_trading_day must be NEXT, PREV, or NONE.",
        )

    weekday_val = data.get("weekday")
    weekday: int | None = None
    if weekday_val is not None and weekday_val != "":
        try:
            weekday = int(weekday_val)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="weekday must be an integer between 0 and 6.",
            ) from exc
        if weekday < 0 or weekday > 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="weekday must be an integer between 0 and 6.",
            )

    dom_val = data.get("day_of_month")
    day_of_month: int | Literal["LAST"] | None = None
    if dom_val is None or dom_val == "":
        day_of_month = None
    elif isinstance(dom_val, str) and dom_val.strip().upper() == "LAST":
        day_of_month = "LAST"
    else:
        try:
            dom_i = int(dom_val)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="day_of_month must be an integer (1-31) or 'LAST'.",
            ) from exc
        if dom_i < 1 or dom_i > 31:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="day_of_month must be an integer (1-31) or 'LAST'.",
            )
        day_of_month = dom_i

    interval_val = data.get("interval_days")
    interval_days: int | None = None
    if interval_val is not None and interval_val != "":
        try:
            interval_days = int(interval_val)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="interval_days must be a positive integer.",
            ) from exc
        if interval_days <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="interval_days must be a positive integer.",
            )

    # Defaults by frequency
    if freq == "WEEKLY" and weekday is None:
        weekday = 4
    if freq in {"MONTHLY", "QUARTERLY"} and day_of_month is None:
        day_of_month = "LAST"
    if freq == "CUSTOM_DAYS" and interval_days is None:
        interval_days = 30

    return RebalanceScheduleConfig(
        frequency=freq,  # type: ignore[arg-type]
        time_local=time_local,
        timezone=tz,
        weekday=weekday,
        day_of_month=day_of_month,
        interval_days=interval_days,
        roll_to_trading_day=roll,  # type: ignore[arg-type]
    )


def schedule_config_to_json(cfg: RebalanceScheduleConfig) -> str:
    return _json_dump(
        {
            "frequency": cfg.frequency,
            "time_local": cfg.time_local,
            "timezone": cfg.timezone,
            "weekday": cfg.weekday,
            "day_of_month": cfg.day_of_month,
            "interval_days": cfg.interval_days,
            "roll_to_trading_day": cfg.roll_to_trading_day,
        }
    )


def compute_next_rebalance_at(
    *,
    cfg: RebalanceScheduleConfig,
    now_utc: datetime | None = None,
    last_run_at_utc: datetime | None = None,
) -> datetime:
    """Compute the next scheduled rebalance time in UTC.

    Notes:
    - v1: trading-day adjustment considers weekends only (no holiday calendar).
    - Stored timestamps are UTC-naive elsewhere in the codebase; this function
      returns an aware UTC datetime, matching `datetime.now(UTC)` usage.
    """

    tz = _get_tz(cfg.timezone)
    now = now_utc or datetime.now(UTC)
    now_local = now.astimezone(tz)
    hh, mm = _parse_hhmm(cfg.time_local)

    def at_time(d: datetime) -> datetime:
        return d.replace(hour=hh, minute=mm, second=0, microsecond=0)

    candidate_local: datetime
    freq = cfg.frequency

    if freq == "WEEKLY":
        weekday = int(cfg.weekday if cfg.weekday is not None else 4)
        base = at_time(now_local)
        days_ahead = (weekday - base.weekday()) % 7
        candidate_local = base + timedelta(days=days_ahead)
        if candidate_local <= now_local:
            candidate_local = candidate_local + timedelta(days=7)
    elif freq == "MONTHLY":
        year = now_local.year
        month = now_local.month
        dim = _days_in_month(year, month)
        dom = cfg.day_of_month
        day = dim if dom == "LAST" or dom is None else min(int(dom), dim)
        candidate_local = datetime(year, month, day, hh, mm, tzinfo=tz)
        if candidate_local <= now_local:
            # next month
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            dim = _days_in_month(year, month)
            day = dim if dom == "LAST" or dom is None else min(int(dom), dim)
            candidate_local = datetime(year, month, day, hh, mm, tzinfo=tz)
    elif freq == "QUARTERLY":
        year = now_local.year
        month = now_local.month
        quarter_start = 1 + 3 * ((month - 1) // 3)
        q_month = quarter_start
        dom = cfg.day_of_month
        dim = _days_in_month(year, q_month)
        day = dim if dom == "LAST" or dom is None else min(int(dom), dim)
        candidate_local = datetime(year, q_month, day, hh, mm, tzinfo=tz)
        if candidate_local <= now_local:
            q_month += 3
            if q_month > 12:
                q_month -= 12
                year += 1
            dim = _days_in_month(year, q_month)
            day = dim if dom == "LAST" or dom is None else min(int(dom), dim)
            candidate_local = datetime(year, q_month, day, hh, mm, tzinfo=tz)
    else:  # CUSTOM_DAYS
        interval = int(cfg.interval_days or 30)
        anchor = last_run_at_utc or now
        anchor_local = anchor.astimezone(tz)
        candidate_local = datetime(
            anchor_local.year,
            anchor_local.month,
            anchor_local.day,
            hh,
            mm,
            tzinfo=tz,
        ) + timedelta(days=interval)
        while candidate_local <= now_local:
            candidate_local = candidate_local + timedelta(days=interval)

    candidate_local = _roll_weekend(candidate_local, cfg.roll_to_trading_day)
    return candidate_local.astimezone(UTC)


__all__ = [
    "RebalanceScheduleConfig",
    "ScheduleFrequency",
    "RollToTradingDay",
    "normalize_schedule_config",
    "schedule_config_to_json",
    "compute_next_rebalance_at",
    "_json_load",
]
