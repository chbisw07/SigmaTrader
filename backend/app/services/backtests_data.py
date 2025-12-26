from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.market_data import load_series


@dataclass(frozen=True)
class UniverseSymbolRef:
    exchange: str
    symbol: str

    @property
    def key(self) -> str:
        return f"{self.exchange}:{self.symbol}"


def _norm_symbol_ref(exchange: str | None, symbol: str) -> UniverseSymbolRef:
    exch_u = (exchange or "NSE").strip().upper() or "NSE"
    sym_u = (symbol or "").strip().upper()
    if not sym_u:
        raise ValueError("symbol is required")
    return UniverseSymbolRef(exchange=exch_u, symbol=sym_u)


def load_eod_close_matrix(
    db: Session,
    settings: Settings,
    *,
    symbols: List[UniverseSymbolRef],
    start: datetime,
    end: datetime,
    allow_fetch: bool = True,
) -> Tuple[List[date], Dict[str, List[Optional[float]]], List[str]]:
    """Load an EOD close-price matrix aligned by date.

    - Returns aligned dates and per-symbol close series.
    - Missing days are represented as None per symbol.
    - Uses the existing candle DB cache (and can fetch when allowed).
    """

    if start >= end:
        raise ValueError("start must be before end")

    unique: list[UniverseSymbolRef] = []
    seen: set[str] = set()
    for s in symbols:
        if s.key in seen:
            continue
        seen.add(s.key)
        unique.append(s)

    per_symbol: dict[str, dict[date, float]] = {}
    missing_symbols: list[str] = []
    all_dates: set[date] = set()

    for s in unique:
        rows = load_series(
            db,
            settings,
            symbol=s.symbol,
            exchange=s.exchange,
            timeframe="1d",
            start=start,
            end=end,
            allow_fetch=allow_fetch,
        )
        if not rows:
            missing_symbols.append(s.key)
            continue
        by_date: dict[date, float] = {}
        for r in rows:
            ts = r.get("ts")
            close = r.get("close")
            if ts is None or close is None:
                continue
            d = ts.date()
            try:
                c = float(close)
            except (TypeError, ValueError):
                continue
            if c <= 0:
                continue
            by_date[d] = c
            all_dates.add(d)
        if by_date:
            per_symbol[s.key] = by_date
        else:
            missing_symbols.append(s.key)

    dates = sorted(all_dates)
    matrix: dict[str, list[Optional[float]]] = {}
    for key, by_date in per_symbol.items():
        matrix[key] = [by_date.get(d) for d in dates]

    return dates, matrix, missing_symbols


def load_eod_open_close_matrix(
    db: Session,
    settings: Settings,
    *,
    symbols: List[UniverseSymbolRef],
    start: datetime,
    end: datetime,
    allow_fetch: bool = True,
) -> tuple[
    List[date],
    Dict[str, List[Optional[float]]],
    Dict[str, List[Optional[float]]],
    List[str],
]:
    """Load aligned EOD open/close matrices by date.

    - Returns aligned dates and per-symbol open/close series.
    - Missing days are represented as None per symbol.
    - Uses the existing candle DB cache (and can fetch when allowed).
    """

    if start >= end:
        raise ValueError("start must be before end")

    unique: list[UniverseSymbolRef] = []
    seen: set[str] = set()
    for s in symbols:
        if s.key in seen:
            continue
        seen.add(s.key)
        unique.append(s)

    per_symbol_open: dict[str, dict[date, float]] = {}
    per_symbol_close: dict[str, dict[date, float]] = {}
    missing_symbols: list[str] = []
    all_dates: set[date] = set()

    for s in unique:
        rows = load_series(
            db,
            settings,
            symbol=s.symbol,
            exchange=s.exchange,
            timeframe="1d",
            start=start,
            end=end,
            allow_fetch=allow_fetch,
        )
        if not rows:
            missing_symbols.append(s.key)
            continue
        by_date_open: dict[date, float] = {}
        by_date_close: dict[date, float] = {}
        for r in rows:
            ts = r.get("ts")
            o = r.get("open")
            c = r.get("close")
            if ts is None:
                continue
            d = ts.date()
            try:
                ov = float(o) if o is not None else None
            except (TypeError, ValueError):
                ov = None
            try:
                cv = float(c) if c is not None else None
            except (TypeError, ValueError):
                cv = None
            if ov is not None and ov > 0:
                by_date_open[d] = ov
                all_dates.add(d)
            if cv is not None and cv > 0:
                by_date_close[d] = cv
                all_dates.add(d)
        if by_date_open or by_date_close:
            per_symbol_open[s.key] = by_date_open
            per_symbol_close[s.key] = by_date_close
        else:
            missing_symbols.append(s.key)

    dates = sorted(all_dates)
    opens: dict[str, list[Optional[float]]] = {}
    closes: dict[str, list[Optional[float]]] = {}
    for key in {**per_symbol_close, **per_symbol_open}.keys():
        opens[key] = [per_symbol_open.get(key, {}).get(d) for d in dates]
        closes[key] = [per_symbol_close.get(key, {}).get(d) for d in dates]

    return dates, opens, closes, missing_symbols


__all__ = [
    "UniverseSymbolRef",
    "_norm_symbol_ref",
    "load_eod_open_close_matrix",
    "load_eod_close_matrix",
]
