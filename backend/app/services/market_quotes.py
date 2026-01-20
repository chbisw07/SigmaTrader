from __future__ import annotations

import time
from threading import Lock
from typing import Dict, Iterable, Tuple

from sqlalchemy.orm import Session

from app.clients.zerodha import ZerodhaClient
from app.core.config import Settings
from app.services.market_data import (
    MarketDataError,
    _get_kite_client,
    _map_app_symbol_to_zerodha_symbol,
)

QuoteKey = Tuple[str, str]  # (exchange, symbol) both uppercased


class QuotePayload(dict):
    """Small dict wrapper for clarity (ltp/prev_close)."""


_CACHE_TTL_SECONDS = 3.0
_cache_lock = Lock()
_cache: Dict[QuoteKey, tuple[float, dict[str, float | None]]] = {}


def _now_monotonic() -> float:
    return time.monotonic()


def _fetch_zerodha_quotes(
    db: Session,
    settings: Settings,
    instruments: list[tuple[str, str]],
) -> Dict[tuple[str, str], Dict[str, float | None]]:
    kite = _get_kite_client(db, settings)
    client = ZerodhaClient(kite)
    return client.get_quote_bulk(instruments)


def get_bulk_quotes(
    db: Session,
    settings: Settings,
    keys: Iterable[QuoteKey],
) -> Dict[QuoteKey, dict[str, float | None]]:
    """Fetch and cache quotes for (exchange,symbol) keys.

    Output values contain:
      - last_price (float)
      - prev_close (float|None)
    """

    canonical = (
        (getattr(settings, "canonical_market_data_broker", None) or "zerodha")
        .strip()
        .lower()
    )
    if canonical != "zerodha":
        raise MarketDataError(f"Unsupported canonical broker for quotes: {canonical}")

    req: list[QuoteKey] = []
    for exch, sym in keys:
        e = (exch or "NSE").strip().upper()
        s = (sym or "").strip().upper()
        if not s:
            continue
        req.append((e, s))
    if not req:
        return {}

    now = _now_monotonic()
    hits: Dict[QuoteKey, dict[str, float | None]] = {}
    missing: list[QuoteKey] = []

    with _cache_lock:
        for k in req:
            cached = _cache.get(k)
            if cached is None:
                missing.append(k)
                continue
            ts, payload = cached
            if now - ts > _CACHE_TTL_SECONDS:
                missing.append(k)
                continue
            hits[k] = dict(payload)

    if not missing:
        return hits

    # Map app symbols to broker tradingsymbols for quote calls.
    mapped: list[tuple[str, str]] = []
    back_map: dict[tuple[str, str], QuoteKey] = {}
    for exch, sym in missing:
        broker_sym = _map_app_symbol_to_zerodha_symbol(exch, sym)
        mapped_key = (exch, broker_sym)
        mapped.append(mapped_key)
        back_map[mapped_key] = (exch, sym)

    fetched = _fetch_zerodha_quotes(db, settings, mapped)
    out: Dict[QuoteKey, dict[str, float | None]] = dict(hits)

    now2 = _now_monotonic()
    to_cache: Dict[QuoteKey, dict[str, float | None]] = {}
    for mapped_key, payload in fetched.items():
        orig_key = back_map.get(mapped_key)
        if orig_key is None:
            continue
        norm = {
            "last_price": float(payload.get("last_price") or 0.0),
            "prev_close": payload.get("prev_close"),
        }
        out[orig_key] = norm
        to_cache[orig_key] = norm

    with _cache_lock:
        for k, payload in to_cache.items():
            _cache[k] = (now2, payload)

    return out


__all__ = ["QuoteKey", "get_bulk_quotes"]

