from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Dict, List

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Candle
from app.schemas.ai_trading_manager import (
    BrokerSnapshot,
    LedgerSnapshot,
    PortfolioDiagnostics,
    PortfolioDriftItem,
)
from app.services.ai_trading_manager.riskgate.policy_config import default_policy


def _quote_map(snapshot: BrokerSnapshot) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for q in snapshot.quotes_cache:
        sym = str(q.symbol).upper()
        out[sym] = float(q.last_price)
    return out


def _build_drift(
    *,
    broker: BrokerSnapshot,
    ledger: LedgerSnapshot,
) -> List[PortfolioDriftItem]:
    quotes = _quote_map(broker)

    exp: Dict[tuple[str, str], float] = {}
    for p in ledger.expected_positions:
        key = (str(p.symbol).upper(), str(p.product).upper())
        exp[key] = float(p.expected_qty)

    act: Dict[tuple[str, str], float] = {}
    for p in broker.positions:
        key = (str(p.symbol).upper(), str(p.product).upper())
        act[key] = float(p.qty)

    keys = sorted(set(exp) | set(act))
    drift: List[PortfolioDriftItem] = []
    for sym, product in keys:
        expected_qty = float(exp.get((sym, product), 0.0))
        broker_qty = float(act.get((sym, product), 0.0))
        delta = broker_qty - expected_qty
        drift.append(
            PortfolioDriftItem(
                symbol=sym,
                product=product,
                expected_qty=expected_qty,
                broker_qty=broker_qty,
                delta_qty=delta,
                last_price=quotes.get(sym),
            )
        )
    return drift


def _load_closes(
    db: Session,
    *,
    symbol: str,
    exchange: str,
    timeframe: str,
    limit: int,
) -> List[tuple[datetime, float]]:
    rows = (
        db.execute(
            select(Candle.ts, Candle.close)
            .where(
                Candle.symbol == symbol,
                Candle.exchange == exchange,
                Candle.timeframe == timeframe,
            )
            .order_by(desc(Candle.ts))
            .limit(limit)
        )
        .all()
    )
    # Ascending by ts for return computation.
    rows2 = [(ts, float(close)) for ts, close in rows]
    return sorted(rows2, key=lambda x: x[0])


def _align_returns(
    series_by_symbol: Dict[str, List[tuple[datetime, float]]],
    *,
    min_observations: int,
) -> tuple[list[str], list[list[float]], datetime | None]:
    if not series_by_symbol:
        return [], [], None

    ts_sets = [set(ts for ts, _ in series) for series in series_by_symbol.values() if series]
    if not ts_sets:
        return [], [], None
    common_ts = sorted(set.intersection(*ts_sets))
    if len(common_ts) < (min_observations + 1):
        return [], [], None

    # Keep the last (min_observations + 1) to compute min_observations returns.
    common_ts = common_ts[-(min_observations + 1) :]
    as_of_ts = common_ts[-1]

    aligned_symbols: list[str] = []
    returns: list[list[float]] = []
    for sym, series in series_by_symbol.items():
        m = {ts: close for ts, close in series}
        rets: list[float] = []
        for i in range(1, len(common_ts)):
            prev = m.get(common_ts[i - 1])
            cur = m.get(common_ts[i])
            if prev is None or cur is None or prev <= 0 or cur <= 0:
                rets.append(0.0)
            else:
                rets.append((cur / prev) - 1.0)
        aligned_symbols.append(sym)
        returns.append(rets)

    return aligned_symbols, returns, as_of_ts


def _compute_corr(returns: list[list[float]]) -> list[list[float]]:
    n = len(returns)
    t = len(returns[0]) if n else 0
    if n == 0 or t <= 1:
        return []

    means = [sum(r) / float(t) for r in returns]
    cov = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            s = 0.0
            for k in range(t):
                s += (returns[i][k] - means[i]) * (returns[j][k] - means[j])
            v = s / float(t - 1)
            cov[i][j] = v
            cov[j][i] = v

    vol = [math.sqrt(max(0.0, cov[i][i])) for i in range(n)]
    corr = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            denom = (vol[i] * vol[j]) if vol[i] > 0 and vol[j] > 0 else 0.0
            corr[i][j] = cov[i][j] / denom if denom else (1.0 if i == j else 0.0)
    return corr


def _correlation_from_candles(
    db: Session,
    *,
    symbols: List[str],
    exchange: str = "NSE",
    timeframe: str = "1d",
    window_days: int = 60,
    min_observations: int = 40,
) -> Dict[str, Any]:
    symbols2 = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    if len(symbols2) < 2:
        return {"status": "skipped", "reason": "need_at_least_2_symbols"}

    limit = max(int(window_days), 2) + 1
    series_by_symbol: Dict[str, List[tuple[datetime, float]]] = {}
    for sym in symbols2:
        series_by_symbol[sym] = _load_closes(
            db,
            symbol=sym,
            exchange=str(exchange).upper(),
            timeframe=str(timeframe),
            limit=limit,
        )

    aligned, returns, as_of_ts = _align_returns(series_by_symbol, min_observations=int(min_observations))
    if not aligned or not returns or as_of_ts is None:
        return {
            "status": "insufficient_data",
            "symbols": symbols2,
            "window_days": int(window_days),
            "min_observations": int(min_observations),
        }

    corr = _compute_corr(returns)
    return {
        "status": "ok",
        "symbols": aligned,
        "timeframe": timeframe,
        "window_days": int(window_days),
        "observations": len(returns[0]) if returns else 0,
        "as_of_ts": as_of_ts,
        "matrix": corr,
    }


def build_portfolio_diagnostics(
    db: Session,
    *,
    account_id: str,
    broker_snapshot: BrokerSnapshot,
    ledger_snapshot: LedgerSnapshot,
) -> PortfolioDiagnostics:
    drift = _build_drift(broker=broker_snapshot, ledger=ledger_snapshot)
    policy = default_policy().normalized()
    risk_budgets = {
        "policy_version": policy.version,
        "policy_hash": policy.content_hash(),
        "max_per_trade_risk_pct": policy.max_per_trade_risk_pct,
        "max_open_positions": policy.max_open_positions,
    }

    symbols = [d.symbol for d in drift if abs(float(d.broker_qty)) > 0 or abs(float(d.expected_qty)) > 0]
    corr = _correlation_from_candles(db, symbols=symbols)

    return PortfolioDiagnostics(
        as_of_ts=broker_snapshot.as_of_ts or datetime.now(UTC),
        account_id=account_id,
        drift=drift,
        risk_budgets=risk_budgets,
        correlation=corr,
    )
