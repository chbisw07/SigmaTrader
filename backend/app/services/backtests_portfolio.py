from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Group, GroupMember
from app.schemas.backtests_portfolio import PortfolioBacktestConfigIn, RebalanceCadence
from app.services.alert_expression_dsl import parse_expression
from app.services.backtests_data import (
    UniverseSymbolRef,
    _norm_symbol_ref,
    load_eod_close_matrix,
)
from app.services.backtests_signal import (
    _eval_expr_at,
    _iter_field_operands,
    _iter_indicator_operands,
    _resolve_indicator_series,
    _series_key,
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
    if config.method != "TARGET_WEIGHTS":
        raise ValueError("This helper only supports method TARGET_WEIGHTS.")
    return run_portfolio_backtest(
        db,
        settings,
        group_id=group_id,
        config=config,
        allow_fetch=allow_fetch,
    )


def run_portfolio_backtest(
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

    refs = [_norm_symbol_ref(m.exchange, m.symbol) for m in members]
    keys = [r.key for r in refs]

    weights_by_key = (
        _normalize_weights(members) if config.method == "TARGET_WEIGHTS" else {}
    )

    lookback_days = 0
    if config.method == "ROTATION":
        lookback_days = max(60, int(config.ranking_window) * 3)
    # market_data stores candle timestamps as timezone-naive datetimes; keep
    # backtests consistent by using naive windows as well.
    start_dt = datetime.combine(config.start_date, datetime.min.time()) - timedelta(
        days=lookback_days
    )
    end_dt = datetime.combine(config.end_date, datetime.min.time()) + timedelta(days=1)
    dates, matrix, missing = load_eod_close_matrix(
        db,
        settings,
        symbols=refs,
        start=start_dt,
        end=end_dt,
        allow_fetch=allow_fetch,
    )
    if not dates:
        raise ValueError("No candles available.")

    sim_start = None
    sim_end = None
    for i, d in enumerate(dates):
        if sim_start is None and d >= config.start_date:
            sim_start = i
        if d <= config.end_date:
            sim_end = i

    if sim_start is None or sim_end is None or sim_start > sim_end:
        raise ValueError("No candles in the selected window.")

    prices_ff: dict[str, list[float | None]] = {
        key: _forward_fill(series) for key, series in matrix.items()
    }

    sim_dates = dates[sim_start : sim_end + 1]
    rebalance_ix = {
        sim_start + i for i in _rebalance_indices(sim_dates, config.cadence)
    }

    rotation_cache: dict[str, dict[tuple[str, str, int], list[float | None]]] = {}
    rotation_first_idx: dict[str, int] = {}
    rotation_closes: dict[str, list[float]] = {}
    eligible_expr = None
    eligible_needed: list[tuple[str, str, int]] = []
    if config.method == "ROTATION" and (config.eligible_dsl or "").strip():
        eligible_expr = parse_expression(config.eligible_dsl)
        if list(_iter_field_operands(eligible_expr)):
            raise ValueError("eligible_dsl does not support FIELD operands.")
        eligible_needed = sorted(
            {_series_key(o) for o in _iter_indicator_operands(eligible_expr)}
        )

    if config.method == "ROTATION":
        for key in keys:
            series = prices_ff.get(key, [])
            first = None
            for i, v in enumerate(series):
                if v is not None and v > 0:
                    first = i
                    break
            if first is None:
                continue
            closes_slice = series[first:]
            if any(v is None for v in closes_slice):
                continue
            rotation_first_idx[key] = first
            rotation_closes[key] = [float(v) for v in closes_slice if v is not None]
            if eligible_expr and eligible_needed:
                series_map: dict[tuple[str, str, int], list[float | None]] = {}
                for kind, tf, period in eligible_needed:
                    series_map[(kind, tf, period)] = _resolve_indicator_series(
                        kind, tf, period, rotation_closes[key]
                    )
                rotation_cache[key] = series_map

    positions: dict[str, int] = {k: 0 for k in keys}
    cash = float(config.initial_cash)

    equity: list[float] = []
    cash_series: list[float] = []
    drawdown_pct: list[float] = []
    actions: list[dict[str, Any]] = []
    total_turnover = 0.0

    slip = float(config.slippage_bps) / 10000.0
    charges_rate = float(config.charges_bps) / 10000.0

    peak = -math.inf
    for i in range(sim_start, sim_end + 1):
        d = dates[i]
        px_by_key: dict[str, float] = {}
        for key in keys:
            s = prices_ff.get(key, [])
            px = s[i] if i < len(s) else None
            if px is not None and px > 0:
                px_by_key[key] = float(px)

        if i in rebalance_ix:
            value_before = _portfolio_value(
                cash=cash, positions=positions, px_by_key=px_by_key
            )
            if value_before > 0:
                budget_cap = value_before * (float(config.budget_pct) / 100.0)

                target_weights: dict[str, float] = {}
                if config.method == "TARGET_WEIGHTS":
                    for key in keys:
                        target_weights[key] = float(weights_by_key.get(key, 0.0) or 0.0)
                elif config.method == "ROTATION":
                    window = max(1, int(config.ranking_window))
                    scores: list[tuple[str, float]] = []
                    for key in keys:
                        first = rotation_first_idx.get(key)
                        closes = rotation_closes.get(key)
                        if first is None or not closes:
                            continue
                        local_i = i - first
                        if local_i < window or local_i >= len(closes):
                            continue
                        if eligible_expr is not None:
                            series_map = rotation_cache.get(key, {})
                            if not _eval_expr_at(eligible_expr, series_map, local_i):
                                continue
                        p0 = closes[local_i - window]
                        p1 = closes[local_i]
                        if p0 <= 0:
                            continue
                        score = (p1 / p0 - 1.0) * 100.0
                        scores.append((key, float(score)))
                    scores.sort(key=lambda x: x[1], reverse=True)
                    picks = [k for k, _ in scores[: max(1, int(config.top_n))]]
                    if picks:
                        w = 1.0 / len(picks)
                        target_weights = {k: w for k in picks}

                desired_qty: dict[str, int] = {}
                for key in keys:
                    w = float(target_weights.get(key, 0.0) or 0.0)
                    px = px_by_key.get(key)
                    if px is None or px <= 0:
                        continue
                    desired_value = value_before * w
                    desired_qty[key] = int(math.floor(desired_value / px))

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
                        "targets": (
                            sorted(
                                target_weights.items(),
                                key=lambda x: x[1],
                                reverse=True,
                            )
                            if config.method == "ROTATION"
                            else None
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

    days = max(1, (sim_dates[-1] - sim_dates[0]).days)
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
            "top_n": int(config.top_n),
            "ranking_window": int(config.ranking_window),
            "eligible_dsl": (config.eligible_dsl or "").strip() or None,
            "symbols": keys,
            "missing_symbols": missing,
        },
        "series": {
            "dates": [d.isoformat() for d in sim_dates],
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


__all__ = ["run_portfolio_backtest", "run_target_weights_portfolio_backtest"]
