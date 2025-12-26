from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Group, GroupMember
from app.schemas.backtests_portfolio import PortfolioBacktestConfigIn, RebalanceCadence
from app.services.backtests_data import (
    UniverseSymbolRef,
    _norm_symbol_ref,
    load_eod_close_matrix,
)


@dataclass(frozen=True)
class _Target:
    ref: UniverseSymbolRef
    weight: float


def _normalize_weights(members: list[GroupMember]) -> dict[str, float]:
    if not members:
        return {}
    raw: list[float | None] = []
    for m in members:
        raw.append(None if m.target_weight is None else float(m.target_weight))

    if all(w is None for w in raw):
        eq = 1.0 / len(members)
        return {
            f"{(m.exchange or 'NSE').upper()}:{m.symbol.upper()}": eq for m in members
        }

    specified_sum = sum(max(0.0, float(w or 0.0)) for w in raw if w is not None)
    unspecified_idx = [i for i, w in enumerate(raw) if w is None]
    weights: list[float] = []

    if specified_sum <= 0:
        eq = 1.0 / len(members)
        weights = [eq for _ in members]
    elif specified_sum >= 1.0:
        # Normalize down to 1.0, ignore unspecified.
        for w in raw:
            weights.append(
                max(0.0, float(w or 0.0)) / specified_sum if specified_sum else 0.0
            )
    else:
        leftover = 1.0 - specified_sum
        per_unspecified = leftover / len(unspecified_idx) if unspecified_idx else 0.0
        for w in raw:
            if w is None:
                weights.append(per_unspecified)
            else:
                weights.append(max(0.0, float(w)))
        total = sum(weights)
        if total > 0:
            weights = [w / total for w in weights]

    out: dict[str, float] = {}
    for m, w in zip(members, weights, strict=False):
        key = f"{(m.exchange or 'NSE').upper()}:{m.symbol.upper()}"
        out[key] = float(w)
    return out


def _rebalance_indices(dates: list[date], cadence: RebalanceCadence) -> list[int]:
    if not dates:
        return []
    out: list[int] = [0]

    if cadence == "WEEKLY":
        last_week = dates[0].isocalendar().week
        for i, d in enumerate(dates[1:], start=1):
            week = d.isocalendar().week
            if week != last_week:
                out.append(i - 1)
                last_week = week
        out.append(len(dates) - 1)
        return sorted(set(out))

    # MONTHLY: last trading day each month.
    last_month = dates[0].month
    for i, d in enumerate(dates[1:], start=1):
        if d.month != last_month:
            out.append(i - 1)
            last_month = d.month
    out.append(len(dates) - 1)
    return sorted(set(out))


def _forward_fill(series: list[float | None]) -> list[float | None]:
    out: list[float | None] = []
    last: float | None = None
    for v in series:
        if v is not None and v > 0:
            last = float(v)
            out.append(last)
        else:
            out.append(last)
    return out


def _portfolio_value(
    *,
    cash: float,
    positions: dict[str, int],
    px_by_key: dict[str, float],
) -> float:
    v = cash
    for key, qty in positions.items():
        px = px_by_key.get(key)
        if px is None:
            continue
        v += float(qty) * px
    return float(v)


def run_target_weights_portfolio_backtest(
    db: Session,
    settings: Settings,
    *,
    group_id: int,
    config: PortfolioBacktestConfigIn,
    allow_fetch: bool = True,
) -> dict[str, Any]:
    group = db.get(Group, group_id)
    if group is None:
        raise ValueError("Group not found.")

    members: list[GroupMember] = (
        db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
    )
    if not members:
        raise ValueError("Group has no members.")

    weights_by_key = _normalize_weights(members)
    targets: list[_Target] = []
    for m in members:
        ref = _norm_symbol_ref(m.exchange, m.symbol)
        w = float(weights_by_key.get(ref.key, 0.0) or 0.0)
        if w <= 0:
            continue
        targets.append(_Target(ref=ref, weight=w))

    if not targets:
        raise ValueError("No symbols with non-zero target weights.")

    # market_data stores candle timestamps as timezone-naive datetimes; keep
    # backtests consistent by using naive windows as well.
    start_dt = datetime.combine(config.start_date, datetime.min.time())
    end_dt = datetime.combine(config.end_date, datetime.min.time()) + timedelta(days=1)
    dates, matrix, missing = load_eod_close_matrix(
        db,
        settings,
        symbols=[t.ref for t in targets],
        start=start_dt,
        end=end_dt,
        allow_fetch=allow_fetch,
    )
    dates = [d for d in dates if config.start_date <= d <= config.end_date]
    if not dates:
        raise ValueError("No candles in the selected window.")

    prices_ff: dict[str, list[float | None]] = {
        key: _forward_fill(series) for key, series in matrix.items()
    }

    rebalance_ix = set(_rebalance_indices(dates, config.cadence))
    positions: dict[str, int] = {t.ref.key: 0 for t in targets}
    cash = float(config.initial_cash)

    equity: list[float] = []
    cash_series: list[float] = []
    drawdown_pct: list[float] = []
    actions: list[dict[str, Any]] = []
    total_turnover = 0.0

    slip = float(config.slippage_bps) / 10000.0
    charges_rate = float(config.charges_bps) / 10000.0

    peak = -math.inf
    for i, d in enumerate(dates):
        px_by_key: dict[str, float] = {}
        for t in targets:
            s = prices_ff.get(t.ref.key, [])
            px = s[i] if i < len(s) else None
            if px is not None and px > 0:
                px_by_key[t.ref.key] = float(px)

        if i in rebalance_ix:
            value_before = _portfolio_value(
                cash=cash, positions=positions, px_by_key=px_by_key
            )
            if value_before <= 0:
                continue
            budget_cap = value_before * (float(config.budget_pct) / 100.0)

            desired_qty: dict[str, int] = {}
            for t in targets:
                px = px_by_key.get(t.ref.key)
                if px is None or px <= 0:
                    continue
                desired_value = value_before * float(t.weight)
                desired_qty[t.ref.key] = int(math.floor(desired_value / px))

            trade_candidates: list[tuple[str, int, float]] = []
            for key, dq in desired_qty.items():
                cq = int(positions.get(key, 0) or 0)
                delta = int(dq - cq)
                if delta == 0:
                    continue
                px = px_by_key.get(key)
                if px is None or px <= 0:
                    continue
                notional = abs(delta) * px
                if notional < float(config.min_trade_value):
                    continue
                trade_candidates.append((key, delta, float(notional)))

            trade_candidates.sort(key=lambda x: x[2], reverse=True)
            trade_candidates = trade_candidates[: int(config.max_trades)]

            used = 0.0
            trades: list[dict[str, Any]] = []

            for key, delta, notional in trade_candidates:
                if used + notional > budget_cap + 1e-9:
                    continue
                px = px_by_key.get(key)
                if px is None or px <= 0:
                    continue
                charge = float(notional) * charges_rate

                if delta > 0:
                    eff_px = px * (1.0 + slip)
                    if cash > charge:
                        max_afford = int(math.floor((cash - charge) / eff_px))
                    else:
                        max_afford = 0
                    qty = min(delta, max_afford)
                    if qty <= 0:
                        continue
                    exec_notional = qty * px
                    exec_charge = exec_notional * charges_rate
                    cash -= qty * eff_px + exec_charge
                    positions[key] = int(positions.get(key, 0) or 0) + qty
                    used += exec_notional
                    total_turnover += exec_notional
                    trades.append(
                        {
                            "symbol": key,
                            "side": "BUY",
                            "qty": qty,
                            "price": px,
                            "fill_price": eff_px,
                            "notional": exec_notional,
                            "charges": exec_charge,
                        }
                    )
                else:
                    qty_avail = int(positions.get(key, 0) or 0)
                    qty = min(-delta, qty_avail)
                    if qty <= 0:
                        continue
                    eff_px = px * (1.0 - slip)
                    exec_notional = qty * px
                    exec_charge = exec_notional * charges_rate
                    cash += qty * eff_px - exec_charge
                    positions[key] = qty_avail - qty
                    used += exec_notional
                    total_turnover += exec_notional
                    trades.append(
                        {
                            "symbol": key,
                            "side": "SELL",
                            "qty": qty,
                            "price": px,
                            "fill_price": eff_px,
                            "notional": exec_notional,
                            "charges": exec_charge,
                        }
                    )

            value_after = _portfolio_value(
                cash=cash, positions=positions, px_by_key=px_by_key
            )
            actions.append(
                {
                    "date": d.isoformat(),
                    "value_before": value_before,
                    "value_after": value_after,
                    "budget_cap": budget_cap,
                    "budget_used": used,
                    "turnover_pct": (
                        (used / value_before * 100.0) if value_before else 0.0
                    ),
                    "trades": trades,
                }
            )

        v = _portfolio_value(cash=cash, positions=positions, px_by_key=px_by_key)
        equity.append(v)
        cash_series.append(float(cash))
        peak = max(peak, v)
        dd = (v / peak - 1.0) * 100.0 if peak > 0 else 0.0
        drawdown_pct.append(float(dd))

    if not equity:
        raise ValueError("No equity series produced.")

    start_val = float(equity[0])
    end_val = float(equity[-1])
    total_return_pct = (end_val / start_val - 1.0) * 100.0 if start_val > 0 else 0.0

    days = max(1, (dates[-1] - dates[0]).days)
    years = days / 365.25
    cagr_pct = (
        ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0 if years > 0 else 0.0
    )

    max_drawdown_pct = abs(min(drawdown_pct)) if drawdown_pct else 0.0

    avg_equity = sum(equity) / len(equity) if equity else 0.0
    turnover_pct_total = (
        (total_turnover / avg_equity * 100.0) if avg_equity > 0 else 0.0
    )

    return {
        "meta": {
            "group_id": group_id,
            "group_name": group.name,
            "method": config.method,
            "cadence": config.cadence,
            "timeframe": config.timeframe,
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
            "initial_cash": float(config.initial_cash),
            "budget_pct": float(config.budget_pct),
            "max_trades": int(config.max_trades),
            "min_trade_value": float(config.min_trade_value),
            "slippage_bps": float(config.slippage_bps),
            "charges_bps": float(config.charges_bps),
            "symbols": [t.ref.key for t in targets],
            "missing_symbols": missing,
        },
        "series": {
            "dates": [d.isoformat() for d in dates],
            "equity": equity,
            "cash": cash_series,
            "drawdown_pct": drawdown_pct,
        },
        "metrics": {
            "total_return_pct": total_return_pct,
            "cagr_pct": cagr_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "turnover_pct_total": turnover_pct_total,
            "rebalance_count": len(actions),
        },
        "actions": actions,
    }


__all__ = ["run_target_weights_portfolio_backtest"]
