from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.market_hours import IST_OFFSET
from app.db.session import get_db
from app.models.market_data import MarketInstrument
from app.schemas.market_data import CandlePoint, MarketSymbol
from app.services.market_data import MarketDataError, Timeframe, load_series

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


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

    stmt = db.query(MarketInstrument).filter(MarketInstrument.active.is_(True))
    if exch:
        stmt = stmt.filter(MarketInstrument.exchange == exch)

    if query:
        like = f"%{query}%"
        stmt = stmt.filter(
            or_(
                MarketInstrument.symbol.ilike(like),
                MarketInstrument.name.ilike(like),
            ),
        )

    rows = stmt.order_by(MarketInstrument.symbol.asc()).limit(limit).all()

    return [
        MarketSymbol(symbol=r.symbol, exchange=r.exchange, name=r.name) for r in rows
    ]


__all__ = ["router"]
