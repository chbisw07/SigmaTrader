from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Lock, Thread
from typing import Dict, Iterable, List, Literal

from sqlalchemy import and_, func, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config_files import load_zerodha_symbol_map
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.core.market_hours import IST_OFFSET
from app.db.session import SessionLocal
from app.models import (
    BrokerConnection,
    BrokerInstrument,
    Candle,
    Listing,
    MarketInstrument,
    Security,
)
from app.services.broker_secrets import get_broker_secret

Timeframe = Literal["1m", "5m", "15m", "1h", "1d", "1mo", "1y"]

BASE_TIMEFRAME_MAP: dict[Timeframe, str] = {
    "1m": "1m",
    "5m": "1m",
    "15m": "1m",
    "1h": "1m",
    "1d": "1d",
    "1mo": "1d",
    "1y": "1d",
}

KITE_INTERVAL_MAP: dict[str, str] = {
    "1m": "minute",
    "1d": "day",
}

MAX_HISTORY_YEARS = 2
MAX_DAYS_PER_CALL = 60

_scheduler_started = False
_scheduler_stop_event = Event()
_history_lock = Lock()


class MarketDataError(RuntimeError):
    """Raised when market data operations cannot be completed."""


def _now_ist_naive() -> datetime:
    """Return current time in IST as a timezone-naive datetime.

    We consistently store candle timestamps as IST-naive values so that
    comparisons and filtering remain simple throughout the codebase.
    """

    return (datetime.now(UTC) + IST_OFFSET).replace(tzinfo=None)


def _to_ist_naive(dt: datetime) -> datetime:
    """Convert an arbitrary datetime to an IST-naive datetime."""

    if dt.tzinfo is None:
        return dt
    return (dt.astimezone(UTC) + IST_OFFSET).replace(tzinfo=None)


def ensure_instrument_from_holding_entry(
    db: Session,
    entry: dict,
    *,
    default_exchange: str = "NSE",
) -> None:
    """Upsert a MarketInstrument row based on a Zerodha holdings entry.

    This is a best-effort helper used by the holdings API so that the market
    data service has instrument tokens available for the same symbols.
    """

    token = entry.get("instrument_token")
    symbol = entry.get("tradingsymbol") or entry.get("symbol")
    exchange = entry.get("exchange") or default_exchange
    isin = entry.get("isin") or entry.get("ISIN")
    name = entry.get("name") or entry.get("company_name")

    if token is None or not isinstance(symbol, str) or not isinstance(exchange, str):
        return

    token_str = str(token)
    exchange_norm = exchange.upper()
    symbol_norm = symbol.strip().upper()

    listing = _get_or_create_listing(
        db,
        exchange=exchange_norm,
        symbol=symbol_norm,
        isin=(
            str(isin).strip().upper()
            if isinstance(isin, str) and isin.strip()
            else None
        ),
        name=str(name).strip() if isinstance(name, str) and name.strip() else None,
    )
    _upsert_broker_instrument(
        db,
        broker_name="zerodha",
        listing_id=listing.id,
        exchange=exchange_norm,
        broker_symbol=symbol_norm,
        instrument_token=token_str,
        isin=listing_isin(db, listing),
        active=True,
    )

    inst: MarketInstrument | None = (
        db.query(MarketInstrument)
        .filter(
            MarketInstrument.symbol == symbol_norm,
            MarketInstrument.exchange == exchange_norm,
        )
        .one_or_none()
    )

    if inst is None:
        inst = MarketInstrument(
            symbol=symbol_norm,
            exchange=exchange_norm,
            instrument_token=token_str,
            active=True,
        )
        db.add(inst)
    else:
        if inst.instrument_token != token_str or not inst.active:
            inst.instrument_token = token_str
            inst.active = True
            db.add(inst)


def listing_isin(db: Session, listing: Listing) -> str | None:
    if listing.security_id is None:
        return None
    sec = db.get(Security, listing.security_id)
    if sec is None:
        return None
    return sec.isin


def _invert_zerodha_symbol_map() -> dict[str, dict[str, str]]:
    raw = load_zerodha_symbol_map()
    inv: dict[str, dict[str, str]] = {}
    for exch, mapping in raw.items():
        inner: dict[str, str] = {}
        for tv_sym, broker_sym in mapping.items():
            inner[str(broker_sym).upper()] = str(tv_sym).upper()
        inv[str(exch).upper()] = inner
    return inv


def _map_app_symbol_to_zerodha_symbol(exchange: str, symbol: str) -> str:
    raw = load_zerodha_symbol_map()
    exch = exchange.upper()
    sym = symbol.upper()
    mapped = raw.get(exch, {}).get(sym)
    return str(mapped).upper() if mapped else sym


def _get_or_create_security(
    db: Session,
    *,
    isin: str,
    name: str | None = None,
) -> Security:
    isin_norm = isin.strip().upper()
    sec: Security | None = (
        db.query(Security).filter(Security.isin == isin_norm).one_or_none()
    )
    if sec is None:
        sec = Security(isin=isin_norm, name=name, active=True)
        db.add(sec)
        db.flush()
        return sec
    updated = False
    if name and not sec.name:
        sec.name = name
        updated = True
    if not sec.active:
        sec.active = True
        updated = True
    if updated:
        db.add(sec)
    return sec


def _get_or_create_listing(
    db: Session,
    *,
    exchange: str,
    symbol: str,
    isin: str | None = None,
    name: str | None = None,
) -> Listing:
    exch = exchange.strip().upper()
    sym = symbol.strip().upper()

    listing: Listing | None = (
        db.query(Listing)
        .filter(Listing.exchange == exch, Listing.symbol == sym)
        .one_or_none()
    )
    if listing is None:
        listing = Listing(exchange=exch, symbol=sym, name=name, active=True)
        db.add(listing)
        db.flush()
    updated = False
    if name and not listing.name:
        listing.name = name
        updated = True

    if isin:
        sec = _get_or_create_security(db, isin=isin, name=name)
        if listing.security_id != sec.id:
            listing.security_id = sec.id
            updated = True

    if not listing.active:
        listing.active = True
        updated = True
    if updated:
        db.add(listing)
    return listing


def _upsert_broker_instrument(
    db: Session,
    *,
    broker_name: str,
    listing_id: int,
    exchange: str,
    broker_symbol: str,
    instrument_token: str,
    isin: str | None,
    active: bool,
) -> BrokerInstrument:
    broker = broker_name.strip().lower()
    token = instrument_token.strip()
    exch = exchange.strip().upper()
    bsym = broker_symbol.strip().upper()
    bi: BrokerInstrument | None = (
        db.query(BrokerInstrument)
        .filter(
            BrokerInstrument.broker_name == broker,
            BrokerInstrument.instrument_token == token,
        )
        .one_or_none()
    )
    if bi is None:
        bi = BrokerInstrument(
            listing_id=listing_id,
            broker_name=broker,
            exchange=exch,
            broker_symbol=bsym,
            instrument_token=token,
            isin=isin,
            active=active,
        )
        db.add(bi)
        return bi

    updated = False
    if bi.listing_id != listing_id:
        bi.listing_id = listing_id
        updated = True
    if bi.exchange != exch:
        bi.exchange = exch
        updated = True
    if bi.broker_symbol != bsym:
        bi.broker_symbol = bsym
        updated = True
    if isin and not bi.isin:
        bi.isin = isin
        updated = True
    if bi.active != active:
        bi.active = active
        updated = True
    if updated:
        db.add(bi)
    return bi


def _get_kite_client(db: Session, settings: Settings):
    """Return a configured KiteConnect client for market data."""

    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.broker_name == "zerodha")
        .order_by(BrokerConnection.updated_at.desc())
        .first()
    )
    if conn is None:
        raise MarketDataError("Zerodha is not connected; cannot fetch market data.")

    api_key = get_broker_secret(
        db,
        settings,
        broker_name="zerodha",
        key="api_key",
        user_id=conn.user_id,
    )
    if not api_key:
        raise MarketDataError(
            "Zerodha API key is not configured; cannot fetch market data.",
        )

    try:
        from kiteconnect import KiteConnect  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - defensive
        raise MarketDataError(
            "kiteconnect library is not installed in the backend environment.",
        ) from exc

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


def _get_instrument_token(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
) -> str:
    canonical_broker = (
        (getattr(settings, "canonical_market_data_broker", None) or "zerodha")
        .strip()
        .lower()
    )
    exch = exchange.upper()
    sym = symbol.upper()

    listing: Listing | None = (
        db.query(Listing)
        .filter(
            Listing.exchange == exch,
            Listing.symbol == sym,
            Listing.active.is_(True),
        )
        .one_or_none()
    )
    if listing is not None:
        bi: BrokerInstrument | None = (
            db.query(BrokerInstrument)
            .filter(
                BrokerInstrument.broker_name == canonical_broker,
                BrokerInstrument.listing_id == listing.id,
                BrokerInstrument.active.is_(True),
            )
            .order_by(BrokerInstrument.updated_at.desc())
            .first()
        )
        if bi is not None:
            return bi.instrument_token

    # Legacy fallback: cached market_instruments.
    inst: MarketInstrument | None = (
        db.query(MarketInstrument)
        .filter(
            MarketInstrument.symbol == sym,
            MarketInstrument.exchange == exch,
            MarketInstrument.active.is_(True),
        )
        .one_or_none()
    )
    if inst is not None:
        return inst.instrument_token

    # Fallback: query Kite instruments for this exchange and try to infer the
    # instrument token for the given symbol.
    try:
        kite = _get_kite_client(db, settings)
        instruments = kite.instruments(exchange.upper())
    except Exception as exc:  # pragma: no cover - defensive / network
        raise MarketDataError(
            f"Instrument not configured for {exchange}:{symbol} "
            f"and failed to fetch instruments from Kite: {exc}",
        ) from exc

    token: str | None = None
    name: str | None = None
    matched_row: dict | None = None
    broker_symbol = _map_app_symbol_to_zerodha_symbol(exch, sym)
    for row in instruments:
        ts = row.get("tradingsymbol")
        exch = row.get("exchange")
        if (
            isinstance(ts, str)
            and ts.upper() == broker_symbol
            and str(exch).upper() == exchange.upper()
        ):
            token_val = row.get("instrument_token")
            if token_val is not None:
                token = str(token_val)
                name = str(row.get("name") or "")
                matched_row = row
                break

    if token is None:
        raise MarketDataError(
            f"Instrument not configured for {exchange}:{symbol} "
            "and could not infer instrument_token from Kite instruments.",
        )

    isin_val = None
    if matched_row is not None:
        isin_raw = matched_row.get("isin")
        if isinstance(isin_raw, str) and isin_raw.strip():
            isin_val = isin_raw.strip().upper()

    listing = _get_or_create_listing(
        db,
        exchange=exchange.upper(),
        symbol=sym,
        isin=isin_val,
        name=name if name else None,
    )
    _upsert_broker_instrument(
        db,
        broker_name=canonical_broker,
        listing_id=listing.id,
        exchange=exchange.upper(),
        broker_symbol=broker_symbol,
        instrument_token=token,
        isin=listing_isin(db, listing),
        active=True,
    )
    db.commit()
    return token


def resolve_listings_bulk(
    db: Session,
    settings: Settings,
    *,
    pairs: list[tuple[str, str]],
    allow_kite_fallback: bool = True,
) -> dict[tuple[str, str], Listing]:
    """Resolve (symbol, exchange) pairs to canonical Listing rows.

    This is used by features such as group imports to enforce that every
    symbol maps to a canonical listing (and to a canonical market-data broker
    instrument token for history loading). When missing, SigmaTrader can
    optionally fall back to fetching the canonical broker instrument master.
    """

    if not pairs:
        return {}

    normalized = [(sym.strip().upper(), exch.strip().upper()) for sym, exch in pairs]
    unique_pairs = sorted(set(normalized))

    cached = (
        db.query(Listing)
        .filter(
            tuple_(
                Listing.symbol,
                Listing.exchange,
            ).in_(unique_pairs),
            Listing.active.is_(True),
        )
        .all()
    )
    out: dict[tuple[str, str], Listing] = {
        (inst.symbol, inst.exchange): inst for inst in cached
    }

    # Compatibility: if listings are missing but legacy MarketInstrument cache
    # has entries (common in tests/older DBs), promote them into canonical
    # listings and broker_instruments without requiring Kite fetch.
    missing_pairs = [
        (sym, exch) for sym, exch in unique_pairs if (sym, exch) not in out
    ]
    if missing_pairs:
        legacy = (
            db.query(MarketInstrument)
            .filter(
                tuple_(
                    MarketInstrument.symbol,
                    MarketInstrument.exchange,
                ).in_(missing_pairs),
                MarketInstrument.active.is_(True),
            )
            .all()
        )
        inserted_any = False
        for inst in legacy:
            listing = _get_or_create_listing(
                db,
                exchange=inst.exchange,
                symbol=inst.symbol,
                isin=None,
                name=inst.name,
            )
            _upsert_broker_instrument(
                db,
                broker_name=(
                    getattr(settings, "canonical_market_data_broker", None) or "zerodha"
                ),
                listing_id=listing.id,
                exchange=inst.exchange,
                broker_symbol=inst.symbol,
                instrument_token=inst.instrument_token,
                isin=listing_isin(db, listing),
                active=True,
            )
            out[(inst.symbol, inst.exchange)] = listing
            inserted_any = True
        if inserted_any:
            try:
                db.commit()
            except IntegrityError:
                db.rollback()

    if not allow_kite_fallback:
        return out

    missing = [(sym, exch) for sym, exch in unique_pairs if (sym, exch) not in out]
    if not missing:
        return out

    # Fetch instruments once per exchange and upsert matches for missing symbols.
    missing_by_exchange: dict[str, set[str]] = {}
    for sym, exch in missing:
        missing_by_exchange.setdefault(exch, set()).add(sym)

    try:
        kite = _get_kite_client(db, settings)
    except Exception:
        # If broker is not connected, just return cached instruments.
        return out

    inverse_map = _invert_zerodha_symbol_map()

    inserted_any = False
    for exch, want in missing_by_exchange.items():
        if not want:
            continue
        try:
            instruments = kite.instruments(exch)
        except Exception:
            continue

        # Match by tradingsymbol for the desired exchange.
        found: dict[str, dict] = {}
        for row in instruments:
            ts = row.get("tradingsymbol")
            if not isinstance(ts, str):
                continue
            canonical_sym = inverse_map.get(exch.upper(), {}).get(
                ts.upper(),
                ts.upper(),
            )
            if canonical_sym not in want:
                continue
            token_val = row.get("instrument_token")
            if token_val is None:
                continue
            found[canonical_sym] = row
            if len(found) == len(want):
                break

        for sym, row in found.items():
            existing = out.get((sym, exch))
            if existing is not None:
                continue
            isin = row.get("isin")
            listing = _get_or_create_listing(
                db,
                exchange=exch,
                symbol=sym,
                isin=(
                    str(isin).strip().upper()
                    if isinstance(isin, str) and isin.strip()
                    else None
                ),
                name=str(row.get("name") or "").strip() or None,
            )
            _upsert_broker_instrument(
                db,
                broker_name=(
                    getattr(settings, "canonical_market_data_broker", None) or "zerodha"
                ),
                listing_id=listing.id,
                exchange=exch,
                broker_symbol=str(row.get("tradingsymbol") or sym).strip().upper(),
                instrument_token=str(row.get("instrument_token")),
                isin=listing_isin(db, listing),
                active=True,
            )
            out[(sym, exch)] = listing
            inserted_any = True

    if inserted_any:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # Best-effort only; ignore race/uniqueness and continue.

    return out


def resolve_market_instruments_bulk(
    db: Session,
    settings: Settings,
    *,
    pairs: list[tuple[str, str]],
    allow_kite_fallback: bool = True,
) -> dict[tuple[str, str], MarketInstrument]:
    """Legacy wrapper kept for compatibility."""

    listings = resolve_listings_bulk(
        db,
        settings,
        pairs=pairs,
        allow_kite_fallback=allow_kite_fallback,
    )
    out: dict[tuple[str, str], MarketInstrument] = {}
    for (sym, exch), listing in listings.items():
        token = _get_instrument_token(db, settings, symbol=sym, exchange=exch)
        inst = MarketInstrument(
            symbol=listing.symbol,
            exchange=listing.exchange,
            instrument_token=str(token),
            name=listing.name,
            active=True,
        )
        out[(sym, exch)] = inst
    return out


def _iter_history_chunks(
    start: datetime,
    end: datetime,
    *,
    max_days: int,
) -> Iterable[tuple[datetime, datetime]]:
    current = start
    while current < end:
        chunk_end = current + timedelta(days=max_days)
        if chunk_end > end:
            chunk_end = end
        yield current, chunk_end
        # Kite intervals are inclusive; advance by one day to avoid overlap.
        current = chunk_end + timedelta(days=1)


def _fetch_and_store_history(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
    base_timeframe: str,
    start: datetime,
    end: datetime,
) -> None:
    if start >= end:
        return

    kite_interval = KITE_INTERVAL_MAP.get(base_timeframe)
    if not kite_interval:
        raise MarketDataError(f"Unsupported base timeframe: {base_timeframe}")

    token = _get_instrument_token(db, settings, symbol=symbol, exchange=exchange)
    kite = _get_kite_client(db, settings)

    # Preload existing timestamps for this window so we can skip duplicates and
    # avoid violating the unique constraint on (symbol, exchange, timeframe, ts).
    existing_ts: set[datetime] = {
        row[0]
        for row in db.query(Candle.ts)
        .filter(
            Candle.symbol == symbol,
            Candle.exchange == exchange,
            Candle.timeframe == base_timeframe,
        )
        .all()
    }

    for chunk_start, chunk_end in _iter_history_chunks(
        start,
        end,
        max_days=MAX_DAYS_PER_CALL,
    ):
        try:
            bars = kite.historical_data(
                int(token),
                from_date=chunk_start,
                to_date=chunk_end,
                interval=kite_interval,
            )
        except Exception as exc:  # pragma: no cover - network/runtime
            raise MarketDataError(f"Failed to fetch history from Kite: {exc}") from exc

        for bar in bars:
            bar_ts = bar.get("date")
            if not isinstance(bar_ts, datetime):
                continue
            bar_ts = _to_ist_naive(bar_ts)
            if bar_ts in existing_ts:
                continue
            existing_ts.add(bar_ts)

            candle = Candle(
                symbol=symbol,
                exchange=exchange,
                timeframe=base_timeframe,
                ts=bar_ts,
                open=float(bar.get("open")),
                high=float(bar.get("high")),
                low=float(bar.get("low")),
                close=float(bar.get("close")),
                volume=float(bar.get("volume") or 0.0),
            )
            db.add(candle)

        try:
            db.commit()
        except IntegrityError:
            # In concurrent scenarios (e.g. background sync running alongside
            # on-demand API calls) another transaction may have inserted some of
            # the same candles after our initial existence check. Since the
            # candles table enforces a unique constraint on
            # (symbol, exchange, timeframe, ts), such conflicts simply mean the
            # desired data is already present. Roll back this chunk and
            # continue.
            db.rollback()


def ensure_history(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
    base_timeframe: str,
    start: datetime,
    end: datetime,
) -> None:
    """Ensure that candles exist for the given base timeframe and window.

    This function performs lazy gap filling:
    - It inspects the existing min/max timestamps for the symbol/exchange/timeframe.
    - It fetches missing history before/after the known window using Kite
      historical APIs with chunked date ranges.
    """

    # Serialise history maintenance to avoid race conditions between the
    # background scheduler and on-demand API calls. This keeps the unique
    # constraint on (symbol, exchange, timeframe, ts) from being violated by
    # concurrent inserts for the same instrument and timeframe.
    with _history_lock:
        now = _now_ist_naive()
        max_age = now - timedelta(days=365 * MAX_HISTORY_YEARS)

        # Clamp requested window to retention bounds.
        if start < max_age:
            start = max_age
        if end > now:
            end = now
        if start >= end:
            return

        existing_min, existing_max = (
            db.query(
                func.min(Candle.ts),
                func.max(Candle.ts),
            )
            .filter(
                Candle.symbol == symbol,
                Candle.exchange == exchange,
                Candle.timeframe == base_timeframe,
            )
            .one()
        )

        segments: list[tuple[datetime, datetime]] = []
        if existing_min is None or existing_max is None:
            segments.append((start, end))
        else:
            # When extending backwards, stop just before the earliest known candle
            # to avoid re-fetching the boundary bar.
            if start < existing_min:
                seg_end = existing_min - timedelta(seconds=1)
                if start < seg_end:
                    segments.append((start, seg_end))

            # When extending forwards, start just after the latest known candle so
            # we do not insert duplicates and violate the unique constraint on
            # (symbol, exchange, timeframe, ts).
            if end > existing_max:
                seg_start = existing_max + timedelta(seconds=1)
                if seg_start < end:
                    segments.append((seg_start, end))

        for seg_start, seg_end in segments:
            _fetch_and_store_history(
                db,
                settings,
                symbol=symbol,
                exchange=exchange,
                base_timeframe=base_timeframe,
                start=seg_start,
                end=seg_end,
            )


def ensure_history_window(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
    base_timeframe: str,
    start: datetime,
    end: datetime,
) -> None:
    """Ensure candles exist for the full requested window (fills internal gaps).

    Unlike `ensure_history`, which only extends history before/after the
    currently known min/max, this function always attempts to fetch the full
    `[start, end]` window and relies on deduplication + the unique constraint
    to avoid double inserts.

    This is ideal for explicit "Hydrate now" actions where correctness is
    preferred over minimizing fetch calls, and it also fills internal gaps.
    """

    with _history_lock:
        now = _now_ist_naive()
        max_age = now - timedelta(days=365 * MAX_HISTORY_YEARS)

        if start < max_age:
            start = max_age
        if end > now:
            end = now
        if start >= end:
            return

        _fetch_and_store_history(
            db,
            settings,
            symbol=symbol,
            exchange=exchange,
            base_timeframe=base_timeframe,
            start=start,
            end=end,
        )


def _aggregate_intraday(candles: List[Candle], *, minutes: int) -> List[Dict]:
    buckets: dict[datetime, Dict[str, float]] = {}
    for c in candles:
        ts = c.ts
        # Truncate to bucket start.
        minute_bucket = (ts.minute // minutes) * minutes
        bucket_ts = ts.replace(minute=0, second=0, microsecond=0) + timedelta(
            minutes=minute_bucket,
        )
        b = buckets.get(bucket_ts)
        if b is None:
            buckets[bucket_ts] = {
                "ts": bucket_ts,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
        else:
            b["high"] = max(b["high"], c.high)
            b["low"] = min(b["low"], c.low)
            b["close"] = c.close
            b["volume"] += c.volume

    return [buckets[k] for k in sorted(buckets.keys())]


def _aggregate_daily_to_period(
    candles: List[Candle],
    *,
    mode: Literal["1mo", "1y"],
) -> List[Dict]:
    grouped: dict[tuple[int, int | None], Dict[str, float]] = {}

    for c in candles:
        if mode == "1mo":
            key = (c.ts.year, c.ts.month)
        else:
            key = (c.ts.year, None)

        bucket = grouped.get(key)
        if bucket is None:
            grouped[key] = {
                "ts": c.ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
        else:
            bucket["high"] = max(bucket["high"], c.high)
            bucket["low"] = min(bucket["low"], c.low)
            bucket["close"] = c.close
            bucket["volume"] += c.volume

    # Sort by synthetic timestamp.
    return [grouped[k] for k in sorted(grouped.keys())]


def load_series(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    allow_fetch: bool = True,
) -> List[Dict]:
    """Return OHLCV series for the given symbol/timeframe and window.

    This function:
    - Ensures base timeframe history is present using `ensure_history`.
    - Loads base candles from the DB.
    - Aggregates them into the requested timeframe when necessary.
    """

    base_timeframe = BASE_TIMEFRAME_MAP[timeframe]
    if allow_fetch:
        ensure_history(
            db,
            settings,
            symbol=symbol,
            exchange=exchange,
            base_timeframe=base_timeframe,
            start=start,
            end=end,
        )

    candles: List[Candle] = (
        db.query(Candle)
        .filter(
            Candle.symbol == symbol,
            Candle.exchange == exchange,
            Candle.timeframe == base_timeframe,
            and_(Candle.ts >= start, Candle.ts <= end),
        )
        .order_by(Candle.ts)
        .all()
    )

    if not candles:
        return []

    if timeframe == base_timeframe:
        return [
            {
                "ts": c.ts,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]

    if timeframe in {"5m", "15m", "1h"}:
        minutes = {"5m": 5, "15m": 15, "1h": 60}[timeframe]
        return _aggregate_intraday(candles, minutes=minutes)

    if timeframe in {"1mo", "1y"}:
        return _aggregate_daily_to_period(candles, mode=timeframe)

    raise MarketDataError(f"Unsupported timeframe: {timeframe}")


def _sync_all_instruments_once() -> None:
    """Background sync to keep OHLCV data reasonably fresh.

    This performs a forward-only sync from the latest known candle up to now
    for all active instruments in the `market_instruments` table, for the base
    timeframes 1m and 1d.
    """

    settings = get_settings()

    with SessionLocal() as db:
        now = _now_ist_naive()
        max_age = now - timedelta(days=365 * MAX_HISTORY_YEARS)

        canonical_broker = (
            (getattr(settings, "canonical_market_data_broker", None) or "zerodha")
            .strip()
            .lower()
        )
        listings: list[Listing] = (
            db.query(Listing)
            .join(BrokerInstrument, BrokerInstrument.listing_id == Listing.id)
            .filter(
                Listing.active.is_(True),
                BrokerInstrument.active.is_(True),
                BrokerInstrument.broker_name == canonical_broker,
            )
            .distinct()
            .all()
        )

        for inst in listings:
            for base_tf in ("1m", "1d"):
                latest_ts: datetime | None = (
                    db.query(func.max(Candle.ts))
                    .filter(
                        Candle.symbol == inst.symbol,
                        Candle.exchange == inst.exchange,
                        Candle.timeframe == base_tf,
                    )
                    .scalar()
                )

                if latest_ts is None:
                    start = max_age
                else:
                    start = max(latest_ts, max_age)

                end = now
                if start >= end:
                    continue

                try:
                    ensure_history(
                        db,
                        settings,
                        symbol=inst.symbol,
                        exchange=inst.exchange,
                        base_timeframe=base_tf,
                        start=start,
                        end=end,
                    )
                except MarketDataError:
                    # Failures are logged in the caller; continue with next instrument.
                    continue


def _market_sync_loop() -> None:  # pragma: no cover - background loop
    """Simple background loop to periodically sync market data."""

    # Run an initial sync shortly after startup, then every 6 hours.
    interval = timedelta(hours=6)
    next_run = _now_ist_naive() + timedelta(minutes=5)

    while not _scheduler_stop_event.is_set():
        now = _now_ist_naive()
        sleep_seconds = (next_run - now).total_seconds()
        if sleep_seconds > 0:
            _scheduler_stop_event.wait(timeout=sleep_seconds)
            if _scheduler_stop_event.is_set():
                return

        try:
            _sync_all_instruments_once()
        except Exception:
            # Swallow all exceptions to avoid killing the loop; errors should be
            # visible in logs via the logging configuration.
            pass

        next_run = _now_ist_naive() + interval


def schedule_market_data_sync() -> None:
    """Start a background thread that periodically syncs market data.

    This uses a very lightweight loop and is intended to keep data reasonably
    fresh for the active instruments universe. Lazy gap-filling on reads is
    still performed by `load_series`.
    """

    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    thread = Thread(target=_market_sync_loop, name="market-data-sync", daemon=True)
    thread.start()


__all__ = [
    "Timeframe",
    "MarketDataError",
    "load_series",
    "schedule_market_data_sync",
]
