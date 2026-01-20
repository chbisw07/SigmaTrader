from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, tuple_
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.market_hours import IST_OFFSET
from app.db.session import get_db
from app.models import Listing
from app.schemas.market_data import CandlePoint, MarketSymbol
from app.services.market_quotes import get_bulk_quotes
from app.services.market_data import (
    MarketDataError,
    Timeframe,
    _get_kite_client,
    load_series,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.get("/status", response_model=dict)
def market_data_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return status of the canonical market-data provider (v1: Zerodha)."""

    canonical = (
        (getattr(settings, "canonical_market_data_broker", None) or "zerodha")
        .strip()
        .lower()
    )
    if canonical != "zerodha":
        return {
            "canonical_broker": canonical,
            "available": False,
            "error": "Unsupported canonical broker.",
        }

    try:
        kite = _get_kite_client(db, settings)
        # Ensure token is valid; profile is the simplest validation.
        _ = kite.profile()
        return {"canonical_broker": canonical, "available": True}
    except Exception as exc:
        return {"canonical_broker": canonical, "available": False, "error": str(exc)}


@router.get("/history", response_model=List[CandlePoint])
def get_market_history(
    symbol: str = Query(..., min_length=1),
    exchange: str = Query("NSE", min_length=1),
    timeframe: Timeframe = Query("1d"),
    period_days: int | None = Query(90, ge=1, le=730),
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> List[CandlePoint]:
    """Return OHLCV history for a symbol/timeframe over a given window.

    Clients can either provide an explicit [start, end] window or rely on
    `period_days` to specify a lookback from the current time.
    """

    if start is None or end is None:
        if period_days is None:
            period_days = 90
        now_ist = datetime.now(UTC) + IST_OFFSET
        now = now_ist.replace(tzinfo=None)
        end = now
        start = now - timedelta(days=period_days)
    else:
        # Normalise to IST-naive datetimes so that comparisons against stored
        # candle timestamps (also IST-naive) do not raise naive/aware errors.
        if start.tzinfo is not None:
            start = (start.astimezone(UTC) + IST_OFFSET).replace(tzinfo=None)
        if end.tzinfo is not None:
            end = (end.astimezone(UTC) + IST_OFFSET).replace(tzinfo=None)

    if start >= end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start must be before end",
        )

    try:
        rows = load_series(
            db,
            settings,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            start=start,
            end=end,
        )
    except MarketDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return [
        CandlePoint(
            ts=row["ts"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for row in rows
    ]


@router.get("/symbols", response_model=List[MarketSymbol])
def search_market_symbols(
    q: str = Query("", max_length=64),
    exchange: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> List[MarketSymbol]:
    query = (q or "").strip().upper()
    exch = (exchange or "").strip().upper() if exchange else None
    if exch and exch not in {"NSE", "BSE"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exchange must be NSE or BSE",
        )

    stmt = db.query(Listing).filter(Listing.active.is_(True))
    if exch:
        stmt = stmt.filter(Listing.exchange == exch)

    if query:
        like = f"%{query}%"
        stmt = stmt.filter(
            or_(
                Listing.symbol.ilike(like),
                Listing.name.ilike(like),
            ),
        )

    rows = stmt.order_by(Listing.symbol.asc()).limit(limit).all()

    return [
        MarketSymbol(symbol=r.symbol, exchange=r.exchange, name=r.name) for r in rows
    ]


class MarketSymbolNormalizeRequest(BaseModel):
    items: List[str] = Field(default_factory=list)
    default_exchange: str = "NSE"


class MarketSymbolNormalizeItem(BaseModel):
    raw: str
    normalized_symbol: Optional[str] = None
    normalized_exchange: Optional[str] = None
    valid: bool
    reason: Optional[str] = None


class MarketSymbolNormalizeResponse(BaseModel):
    items: List[MarketSymbolNormalizeItem] = Field(default_factory=list)


def _parse_symbol_raw(
    raw: str,
    *,
    default_exchange: str,
) -> tuple[str | None, str | None, str | None]:
    text = (raw or "").strip().upper()
    if not text:
        return None, None, "empty"
    exch = (default_exchange or "NSE").strip().upper() or "NSE"
    sym = text
    if ":" in text:
        prefix, rest = text.split(":", 1)
        if prefix in {"NSE", "BSE"} and rest.strip():
            exch = prefix
            sym = rest.strip()
        else:
            return None, None, "invalid_prefix"
    if exch not in {"NSE", "BSE"}:
        return None, None, "invalid_exchange"
    if not sym:
        return None, None, "empty_symbol"
    return exch, sym, None


@router.post("/symbols/normalize", response_model=MarketSymbolNormalizeResponse)
def normalize_symbols(
    payload: MarketSymbolNormalizeRequest,
    db: Session = Depends(get_db),
) -> MarketSymbolNormalizeResponse:
    default_exchange = (payload.default_exchange or "NSE").strip().upper() or "NSE"
    out_items: list[MarketSymbolNormalizeItem] = []
    normalized_pairs: list[tuple[str, str]] = []

    for raw in payload.items or []:
        exch, sym, reason = _parse_symbol_raw(
            str(raw or ""),
            default_exchange=default_exchange,
        )
        if reason is not None or exch is None or sym is None:
            out_items.append(
                MarketSymbolNormalizeItem(
                    raw=str(raw or ""),
                    normalized_symbol=None,
                    normalized_exchange=None,
                    valid=False,
                    reason=reason or "invalid",
                )
            )
            continue
        normalized_pairs.append((exch, sym))
        out_items.append(
            MarketSymbolNormalizeItem(
                raw=str(raw or ""),
                normalized_symbol=sym,
                normalized_exchange=exch,
                valid=False,
                reason="not_validated",
            )
        )

    if not normalized_pairs:
        return MarketSymbolNormalizeResponse(items=out_items)

    uniq = sorted(set(normalized_pairs))
    rows = (
        db.query(Listing)
        .filter(
            Listing.active.is_(True),
            tuple_(Listing.exchange, Listing.symbol).in_(uniq),
        )
        .all()
    )
    existing = {(r.exchange.upper(), r.symbol.upper()) for r in rows}

    for item in out_items:
        if item.reason != "not_validated":
            continue
        exch = (item.normalized_exchange or "").upper()
        sym = (item.normalized_symbol or "").upper()
        if (exch, sym) in existing:
            item.valid = True
            item.reason = None
        else:
            item.valid = False
            item.reason = "not_found"

    return MarketSymbolNormalizeResponse(items=out_items)


class MarketQuotesRequestItem(BaseModel):
    symbol: str = Field(..., min_length=1)
    exchange: Optional[str] = None


class MarketQuotesRequest(BaseModel):
    items: List[MarketQuotesRequestItem] = Field(default_factory=list)


class MarketQuoteRead(BaseModel):
    symbol: str
    exchange: str
    ltp: Optional[float] = None
    prev_close: Optional[float] = None
    day_pct: Optional[float] = None


class MarketQuotesResponse(BaseModel):
    items: List[MarketQuoteRead] = Field(default_factory=list)


@router.post("/quotes", response_model=MarketQuotesResponse)
def get_market_quotes(
    payload: MarketQuotesRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MarketQuotesResponse:
    items = payload.items or []
    if len(items) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many symbols (max 200).",
        )

    parsed: list[tuple[str, str]] = []
    keys: list[tuple[str, str]] = []
    for it in items:
        combined = f"{it.exchange}:{it.symbol}" if it.exchange else it.symbol
        exch, sym, reason = _parse_symbol_raw(combined, default_exchange="NSE")
        if reason is not None or exch is None or sym is None:
            parsed.append(
                (
                    (it.exchange or "NSE").strip().upper() or "NSE",
                    (it.symbol or "").strip().upper(),
                )
            )
            continue
        parsed.append((exch, sym))
        keys.append((exch, sym))

    quotes: dict[tuple[str, str], dict[str, float | None]] = {}
    if keys:
        try:
            quotes = get_bulk_quotes(db, settings, keys)
        except MarketDataError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    out: list[MarketQuoteRead] = []
    for exch, sym in parsed:
        q = quotes.get((exch, sym))
        ltp_raw = float(q.get("last_price") or 0.0) if q else 0.0
        prev = q.get("prev_close") if q else None
        prev_f = float(prev) if prev is not None else None
        ltp = ltp_raw if ltp_raw > 0 else None
        day_pct = None
        if ltp is not None and prev_f is not None and prev_f > 0:
            day_pct = ((ltp - prev_f) / prev_f) * 100.0

        out.append(
            MarketQuoteRead(
                symbol=sym,
                exchange=exch,
                ltp=ltp,
                prev_close=prev_f,
                day_pct=day_pct,
            )
        )

    return MarketQuotesResponse(items=out)


__all__ = ["router"]
