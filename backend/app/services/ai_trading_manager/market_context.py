from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Dict, List, Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Candle
from app.schemas.ai_trading_manager import (
    MarketContextOverlay,
    SymbolMarketContext,
    TrendRegime,
    VolatilityRegime,
)


def _std(values: Sequence[float]) -> float | None:
    n = len(values)
    if n <= 1:
        return None
    mu = sum(values) / float(n)
    var = sum((x - mu) ** 2 for x in values) / float(n - 1)
    return math.sqrt(max(0.0, var))


def _sma(values: Sequence[float], window: int) -> float | None:
    if window <= 0:
        return None
    if len(values) < window:
        return None
    tail = values[-window:]
    return sum(tail) / float(window)


def _atr14(high: Sequence[float], low: Sequence[float], close: Sequence[float]) -> float | None:
    if len(high) < 15 or len(low) < 15 or len(close) < 15:
        return None
    trs: List[float] = []
    for i in range(1, len(close)):
        tr = max(
            float(high[i] - low[i]),
            abs(float(high[i] - close[i - 1])),
            abs(float(low[i] - close[i - 1])),
        )
        trs.append(tr)
    if len(trs) < 14:
        return None
    tail = trs[-14:]
    return sum(tail) / float(len(tail))


def _trend_regime(*, sma20: float | None, sma50: float | None) -> TrendRegime:
    if sma20 is None or sma50 is None or sma50 <= 0:
        return TrendRegime.unknown
    tol = 0.002  # 0.2% hysteresis to reduce noisy flips
    if sma20 > sma50 * (1.0 + tol):
        return TrendRegime.up
    if sma20 < sma50 * (1.0 - tol):
        return TrendRegime.down
    return TrendRegime.range


def _vol_regime(*, vol20_ann_pct: float | None) -> VolatilityRegime:
    if vol20_ann_pct is None or not math.isfinite(vol20_ann_pct):
        return VolatilityRegime.unknown
    if vol20_ann_pct < 15.0:
        return VolatilityRegime.low
    if vol20_ann_pct > 35.0:
        return VolatilityRegime.high
    return VolatilityRegime.normal


def _load_candles(
    db: Session,
    *,
    symbol: str,
    exchange: str,
    timeframe: str,
    limit: int,
) -> list[Candle]:
    return (
        db.execute(
            select(Candle)
            .where(
                Candle.symbol == symbol,
                Candle.exchange == exchange,
                Candle.timeframe == timeframe,
            )
            .order_by(desc(Candle.ts))
            .limit(limit)
        )
        .scalars()
        .all()
    )[::-1]


def build_market_context_overlay(
    db: Session,
    *,
    symbols: List[str],
    exchange: str = "NSE",
    timeframe: str = "1d",
    lookback: int = 80,
) -> MarketContextOverlay:
    symbols2 = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    exch = (exchange or "NSE").strip().upper()
    tf = str(timeframe or "1d")

    items: List[SymbolMarketContext] = []
    vols: List[float] = []
    atr_pcts: List[float] = []
    as_of_ts = datetime.now(UTC)

    for sym in symbols2:
        candles = _load_candles(db, symbol=sym, exchange=exch, timeframe=tf, limit=int(lookback))
        notes: List[str] = []
        if not candles:
            items.append(
                SymbolMarketContext(
                    symbol=sym,
                    exchange=exch,
                    timeframe=tf,
                    as_of_ts=as_of_ts,
                    notes=["NO_CANDLES"],
                )
            )
            continue

        last_ts = candles[-1].ts
        last_ts_utc = last_ts.replace(tzinfo=UTC) if last_ts.tzinfo is None else last_ts
        as_of_ts = max(as_of_ts, last_ts_utc)
        close = [float(c.close) for c in candles]
        high = [float(c.high) for c in candles]
        low = [float(c.low) for c in candles]

        sma20 = _sma(close, 20)
        sma50 = _sma(close, 50)
        atr14 = _atr14(high, low, close)

        returns: List[float] = []
        for i in range(1, len(close)):
            prev = close[i - 1]
            cur = close[i]
            if prev > 0 and cur > 0:
                returns.append((cur / prev) - 1.0)
            else:
                returns.append(0.0)

        vol20 = _std(returns[-20:]) if len(returns) >= 20 else None
        vol20_ann_pct = (vol20 * math.sqrt(252.0) * 100.0) if vol20 is not None else None

        last_close = close[-1] if close else None
        if atr14 is not None and last_close and last_close > 0:
            atr14_pct = (float(atr14) / float(last_close)) * 100.0
        else:
            atr14_pct = None

        trend = _trend_regime(sma20=sma20, sma50=sma50)
        vol_reg = _vol_regime(vol20_ann_pct=vol20_ann_pct)

        if len(candles) < 55:
            notes.append("INSUFFICIENT_CANDLES")

        if vol20_ann_pct is not None:
            vols.append(float(vol20_ann_pct))
        if atr14_pct is not None:
            atr_pcts.append(float(atr14_pct))

        items.append(
            SymbolMarketContext(
                symbol=sym,
                exchange=exch,
                timeframe=tf,
                as_of_ts=as_of_ts,
                close=last_close,
                sma20=sma20,
                sma50=sma50,
                atr14=atr14,
                atr14_pct=atr14_pct,
                vol20_ann_pct=vol20_ann_pct,
                trend_regime=trend,
                volatility_regime=vol_reg,
                notes=notes,
            )
        )

    summary: Dict[str, object] = {
        "symbols": symbols2,
        "avg_vol20_ann_pct": (sum(vols) / float(len(vols))) if vols else None,
        "avg_atr14_pct": (sum(atr_pcts) / float(len(atr_pcts))) if atr_pcts else None,
    }

    return MarketContextOverlay(
        as_of_ts=as_of_ts,
        exchange=exch,
        timeframe=tf,
        items=items,
        summary=summary,
    )
