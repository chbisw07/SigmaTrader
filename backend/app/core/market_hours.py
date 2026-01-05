from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Set

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.config_files import get_config_dir
from app.models import MarketCalendar

IST_OFFSET = timedelta(hours=5, minutes=30)

DEFAULT_MARKET_OPEN = time(9, 15)
DEFAULT_MARKET_CLOSE = time(15, 30)
DEFAULT_PROXY_CLOSE_OFFSET_MINUTES = 5
DEFAULT_PREFERRED_WINDOW_MINUTES = 5


def _now_ist() -> datetime:
    utc_now = datetime.now(UTC)
    return (utc_now + IST_OFFSET).replace(tzinfo=None)


@lru_cache(maxsize=1)
def _load_indian_holidays() -> Set[str]:
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


def _time_to_hhmm(t: time | None) -> str | None:
    if t is None:
        return None
    return f"{t.hour:02d}:{t.minute:02d}"


@dataclass(frozen=True)
class ResolvedMarketSession:
    exchange: str
    date: date
    session_type: str
    open_time: time | None
    close_time: time | None
    proxy_close_time: time | None
    preferred_sell_window: tuple[time | None, time | None]
    preferred_buy_window: tuple[time | None, time | None]
    mis_force_flatten_window: tuple[time | None, time | None]

    def is_trading_day(self) -> bool:
        return (
            self.session_type != "CLOSED"
            and self.open_time is not None
            and self.close_time is not None
        )

    def is_trading_time(self, now_ist: datetime) -> bool:
        if not self.is_trading_day():
            return False
        if now_ist.date() != self.date:
            return False
        assert self.open_time is not None and self.close_time is not None
        minutes = now_ist.hour * 60 + now_ist.minute
        start = self.open_time.hour * 60 + self.open_time.minute
        end = self.close_time.hour * 60 + self.close_time.minute
        return start <= minutes <= end

    def as_dict(self) -> dict:
        return {
            "exchange": self.exchange,
            "date": self.date.isoformat(),
            "session_type": self.session_type,
            "open_time": _time_to_hhmm(self.open_time),
            "close_time": _time_to_hhmm(self.close_time),
            "proxy_close_time": _time_to_hhmm(self.proxy_close_time),
            "preferred_sell_window": tuple(
                map(_time_to_hhmm, self.preferred_sell_window)
            ),
            "preferred_buy_window": tuple(
                map(_time_to_hhmm, self.preferred_buy_window)
            ),
            "mis_force_flatten_window": tuple(
                map(_time_to_hhmm, self.mis_force_flatten_window)
            ),
        }


def default_market_session(*, exchange: str, day: date) -> ResolvedMarketSession:
    open_t = DEFAULT_MARKET_OPEN
    close_t = DEFAULT_MARKET_CLOSE
    proxy_dt = datetime.combine(day, close_t) - timedelta(
        minutes=DEFAULT_PROXY_CLOSE_OFFSET_MINUTES
    )
    proxy_t = proxy_dt.time()
    sell_start = open_t
    sell_end = (
        datetime.combine(day, open_t)
        + timedelta(minutes=DEFAULT_PREFERRED_WINDOW_MINUTES)
    ).time()
    buy_start = proxy_t
    buy_end = close_t
    return ResolvedMarketSession(
        exchange=str(exchange).upper(),
        date=day,
        session_type="NORMAL",
        open_time=open_t,
        close_time=close_t,
        proxy_close_time=proxy_t,
        preferred_sell_window=(sell_start, sell_end),
        preferred_buy_window=(buy_start, buy_end),
        mis_force_flatten_window=(buy_start, buy_end),
    )


def _market_calendar_enabled(db: Session) -> bool:
    try:
        return "market_calendar" in inspect(db.get_bind()).get_table_names()
    except Exception:
        return False


def resolve_market_session(
    db: Session,
    *,
    day: date,
    exchange: str,
) -> ResolvedMarketSession:
    exch = str(exchange).upper()

    if day.weekday() >= 5:
        return ResolvedMarketSession(
            exchange=exch,
            date=day,
            session_type="CLOSED",
            open_time=None,
            close_time=None,
            proxy_close_time=None,
            preferred_sell_window=(None, None),
            preferred_buy_window=(None, None),
            mis_force_flatten_window=(None, None),
        )

    cal_row = None
    if _market_calendar_enabled(db):
        cal_row = (
            db.query(MarketCalendar)
            .filter(MarketCalendar.date == day)
            .filter(MarketCalendar.exchange == exch)
            .one_or_none()
        )

    if cal_row is None and day.isoformat() in _load_indian_holidays():
        return ResolvedMarketSession(
            exchange=exch,
            date=day,
            session_type="CLOSED",
            open_time=None,
            close_time=None,
            proxy_close_time=None,
            preferred_sell_window=(None, None),
            preferred_buy_window=(None, None),
            mis_force_flatten_window=(None, None),
        )

    base = default_market_session(exchange=exch, day=day)
    if cal_row is None:
        return base

    st = str(cal_row.session_type or "NORMAL").upper()
    if st == "CLOSED":
        return ResolvedMarketSession(
            exchange=exch,
            date=day,
            session_type="CLOSED",
            open_time=None,
            close_time=None,
            proxy_close_time=None,
            preferred_sell_window=(None, None),
            preferred_buy_window=(None, None),
            mis_force_flatten_window=(None, None),
        )

    open_t = cal_row.open_time or base.open_time
    close_t = cal_row.close_time or base.close_time
    if open_t is None or close_t is None:
        return base

    proxy_dt = datetime.combine(day, close_t) - timedelta(
        minutes=DEFAULT_PROXY_CLOSE_OFFSET_MINUTES
    )
    proxy_t = proxy_dt.time()
    sell_start = open_t
    sell_end = (
        datetime.combine(day, open_t)
        + timedelta(minutes=DEFAULT_PREFERRED_WINDOW_MINUTES)
    ).time()
    buy_start = proxy_t
    buy_end = close_t
    return ResolvedMarketSession(
        exchange=exch,
        date=day,
        session_type=st,
        open_time=open_t,
        close_time=close_t,
        proxy_close_time=proxy_t,
        preferred_sell_window=(sell_start, sell_end),
        preferred_buy_window=(buy_start, buy_end),
        mis_force_flatten_window=(buy_start, buy_end),
    )


def is_trading_time(
    db: Session,
    *,
    now_ist: datetime,
    exchange: str,
) -> bool:
    session = resolve_market_session(db, day=now_ist.date(), exchange=exchange)
    return session.is_trading_time(now_ist)


def is_market_open(
    db: Session,
    *,
    now_ist: datetime,
    exchange: str,
) -> bool:
    return is_trading_time(db, now_ist=now_ist, exchange=exchange)


def is_market_open_now() -> bool:
    """Legacy helper (v1): returns True if market is open now using JSON holidays."""

    now_ist = _now_ist()

    if now_ist.weekday() >= 5:
        return False
    if now_ist.date().isoformat() in _load_indian_holidays():
        return False

    minutes = now_ist.hour * 60 + now_ist.minute
    start = DEFAULT_MARKET_OPEN.hour * 60 + DEFAULT_MARKET_OPEN.minute
    end = DEFAULT_MARKET_CLOSE.hour * 60 + DEFAULT_MARKET_CLOSE.minute
    return start <= minutes <= end


def is_preopen_now(now_ist: datetime | None = None) -> bool:
    """Legacy helper (v1): Indian pre-open session (09:00–09:15 IST)."""

    current = now_ist or _now_ist()

    if current.weekday() >= 5:
        return False
    if current.date().isoformat() in _load_indian_holidays():
        return False

    minutes = current.hour * 60 + current.minute
    start = 9 * 60  # 09:00
    end = 9 * 60 + 15  # 09:15 (exclusive)
    return start <= minutes < end


__all__ = [
    "DEFAULT_MARKET_CLOSE",
    "DEFAULT_MARKET_OPEN",
    "DEFAULT_PREFERRED_WINDOW_MINUTES",
    "DEFAULT_PROXY_CLOSE_OFFSET_MINUTES",
    "IST_OFFSET",
    "ResolvedMarketSession",
    "default_market_session",
    "is_market_open",
    "is_market_open_now",
    "is_preopen_now",
    "is_trading_time",
    "resolve_market_session",
]
