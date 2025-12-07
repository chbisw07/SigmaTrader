from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.market_hours import IST_OFFSET
from app.db.session import get_db
from app.schemas.market_data import CandlePoint
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


__all__ = ["router"]
