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
    load_eod_open_close_matrix,
)
from app.services.backtests_signal import (
    _eval_expr_at,
    _iter_field_operands,
    _iter_indicator_operands,
    _resolve_indicator_series,
    _series_key,
)
from app.services.rebalance_risk import solve_risk_parity_erc


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


def _compute_covariance(returns: list[list[float]]) -> list[list[float]]:
    n = len(returns)
    t = len(returns[0]) if n else 0
    if n == 0 or t <= 1:
        raise ValueError("Insufficient returns to compute covariance.")

    means = [sum(r) / t for r in returns]
    cov = [[0.0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            s = 0.0
            for k in range(t):
                s += (returns[i][k] - means[i]) * (returns[j][k] - means[j])
            v = s / float(t - 1)
            cov[i][j] = float(v)
            cov[j][i] = float(v)
    return cov


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


def _execute_trade_candidates(
    *,
    trade_candidates: list[tuple[str, int, float, float]],
    px_fill_by_key: dict[str, float],
    positions: dict[str, int],
    cash: float,
    budget_cap: float,
    slip: float,
    charges_rate: float,
) -> tuple[float, float, list[dict[str, Any]], float]:
    """Execute a list of trade candidates.

    trade_candidates: (key, delta_qty, decision_price, decision_notional).
    - Budget/charges are computed on decision_notional (decision_price).
    - Cash impact uses fill prices (px_fill_by_key) with slippage.
    """

    used = 0.0
    turnover = 0.0
    trades: list[dict[str, Any]] = []

    for key, delta, decision_px, decision_notional in trade_candidates:
        if used + decision_notional > budget_cap + 1e-9:
            continue
        fill_px = px_fill_by_key.get(key)
        if fill_px is None or fill_px <= 0:
            continue
        charge = float(decision_notional) * charges_rate

        if delta > 0:
            eff_px = fill_px * (1.0 + slip)
            if cash <= charge:
                continue
            max_afford = int(math.floor((cash - charge) / eff_px))
            qty = min(delta, max_afford)
            if qty <= 0:
                continue
            exec_notional = qty * decision_px
            exec_charge = exec_notional * charges_rate
            cash -= qty * eff_px + exec_charge
            positions[key] = int(positions.get(key, 0) or 0) + qty
            used += exec_notional
            turnover += exec_notional
            trades.append(
                {
                    "symbol": key,
                    "side": "BUY",
                    "qty": qty,
                    "decision_price": decision_px,
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
            eff_px = fill_px * (1.0 - slip)
            exec_notional = qty * decision_px
            exec_charge = exec_notional * charges_rate
            cash += qty * eff_px - exec_charge
            positions[key] = qty_avail - qty
            used += exec_notional
            turnover += exec_notional
            trades.append(
                {
                    "symbol": key,
                    "side": "SELL",
                    "qty": qty,
                    "decision_price": decision_px,
                    "fill_price": eff_px,
                    "notional": exec_notional,
                    "charges": exec_charge,
                }
            )

    return cash, used, trades, turnover


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
    elif config.method == "RISK_PARITY":
        lookback_days = max(60, int(config.risk_window) * 3)
    # market_data stores candle timestamps as timezone-naive datetimes; keep
    # backtests consistent by using naive windows as well.
    start_dt = datetime.combine(config.start_date, datetime.min.time()) - timedelta(
        days=lookback_days
    )
    end_dt = datetime.combine(config.end_date, datetime.min.time()) + timedelta(days=1)
    dates, opens_raw, closes_raw, missing = load_eod_open_close_matrix(
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

    close_ff: dict[str, list[float | None]] = {
        key: _forward_fill(series) for key, series in closes_raw.items()
    }
    open_ff: dict[str, list[float | None]] = {}
    for key in set([*opens_raw.keys(), *close_ff.keys()]):
        opens = opens_raw.get(key, [None] * len(dates))
        closes = close_ff.get(key, [None] * len(dates))
        out: list[float | None] = []
        last: float | None = None
        for ov, cv in zip(opens, closes, strict=False):
            v = ov if ov is not None and ov > 0 else (cv if cv is not None else None)
            if v is not None and v > 0:
                last = float(v)
                out.append(last)
            else:
                out.append(last)
        open_ff[key] = out

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
            series = close_ff.get(key, [])
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

    pending: dict[int, list[dict[str, Any]]] = {}
    peak = -math.inf
    for i in range(sim_start, sim_end + 1):
        d = dates[i]
        px_close_by_key: dict[str, float] = {}
        px_open_by_key: dict[str, float] = {}
        for key in keys:
            s_close = close_ff.get(key, [])
            px = s_close[i] if i < len(s_close) else None
            if px is not None and px > 0:
                px_close_by_key[key] = float(px)

            s_open = open_ff.get(key, [])
            opx = s_open[i] if i < len(s_open) else None
            if opx is not None and opx > 0:
                px_open_by_key[key] = float(opx)

        if config.fill_timing == "NEXT_OPEN":
            for plan in pending.pop(i, []):
                cash, used, trades, turnover = _execute_trade_candidates(
                    trade_candidates=plan["trade_candidates"],
                    px_fill_by_key=px_open_by_key,
                    positions=positions,
                    cash=cash,
                    budget_cap=float(plan["budget_cap"]),
                    slip=slip,
                    charges_rate=charges_rate,
                )
                total_turnover += turnover
                value_after = _portfolio_value(
                    cash=cash, positions=positions, px_by_key=px_close_by_key
                )
                actions.append(
                    {
                        "date": plan["decision_date"],
                        "executed_on": d.isoformat(),
                        "fill_timing": "NEXT_OPEN",
                        "value_before": plan["value_before"],
                        "value_after": value_after,
                        "budget_cap": plan["budget_cap"],
                        "budget_used": used,
                        "turnover_pct": (
                            (used / plan["value_before"] * 100.0)
                            if plan["value_before"]
                            else 0.0
                        ),
                        "targets": plan["targets"],
                        "trades": trades,
                    }
                )

        if i in rebalance_ix:
            value_before = _portfolio_value(
                cash=cash, positions=positions, px_by_key=px_close_by_key
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
                elif config.method == "RISK_PARITY":
                    window = max(2, int(config.risk_window))
                    min_obs = max(2, min(int(config.min_observations), window))
                    obs = min(window, i)
                    start_i = i - obs

                    eligible: list[str] = []
                    returns: list[list[float]] = []
                    if obs >= min_obs and start_i >= 0:
                        for key in keys:
                            if key not in px_close_by_key:
                                continue
                            series = close_ff.get(key, [])
                            if i >= len(series):
                                continue
                            ok = True
                            rets: list[float] = []
                            for j in range(start_i + 1, i + 1):
                                p0 = series[j - 1]
                                p1 = series[j]
                                if p0 is None or p1 is None or p0 <= 0 or p1 <= 0:
                                    ok = False
                                    break
                                rets.append(float(p1 / p0 - 1.0))
                            if not ok or len(rets) < min_obs:
                                continue
                            eligible.append(key)
                            returns.append(rets[-min_obs:])

                    if len(eligible) == 1:
                        target_weights = {eligible[0]: 1.0}
                    elif len(eligible) >= 2:
                        try:
                            cov = _compute_covariance(returns)
                            rp = solve_risk_parity_erc(
                                cov,
                                min_weight=float(config.min_weight),
                                max_weight=float(config.max_weight),
                                max_iter=200,
                                tol=1e-6,
                            )
                            target_weights = {
                                k: float(w)
                                for k, w in zip(eligible, rp.weights, strict=False)
                            }
                        except Exception:
                            w = 1.0 / len(eligible)
                            target_weights = {k: w for k in eligible}

                desired_qty: dict[str, int] = {}
                for key in keys:
                    w = float(target_weights.get(key, 0.0) or 0.0)
                    px = px_close_by_key.get(key)
                    if px is None or px <= 0:
                        continue
                    desired_value = value_before * w
                    desired_qty[key] = int(math.floor(desired_value / px))

                trade_candidates: list[tuple[str, int, float, float]] = []
                for key, dq in desired_qty.items():
                    cq = int(positions.get(key, 0) or 0)
                    delta = int(dq - cq)
                    if delta == 0:
                        continue
                    px = px_close_by_key.get(key)
                    if px is None or px <= 0:
                        continue
                    notional = abs(delta) * px
                    if notional < float(config.min_trade_value):
                        continue
                    trade_candidates.append((key, delta, float(px), float(notional)))

                trade_candidates.sort(key=lambda x: x[3], reverse=True)
                trade_candidates = trade_candidates[: int(config.max_trades)]

                targets_sorted = (
                    sorted(target_weights.items(), key=lambda x: x[1], reverse=True)
                    if config.method in {"ROTATION", "RISK_PARITY"}
                    else None
                )

                if config.fill_timing == "CLOSE":
                    cash, used, trades, turnover = _execute_trade_candidates(
                        trade_candidates=trade_candidates,
                        px_fill_by_key=px_close_by_key,
                        positions=positions,
                        cash=cash,
                        budget_cap=budget_cap,
                        slip=slip,
                        charges_rate=charges_rate,
                    )
                    total_turnover += turnover
                    value_after = _portfolio_value(
                        cash=cash, positions=positions, px_by_key=px_close_by_key
                    )
                    actions.append(
                        {
                            "date": d.isoformat(),
                            "executed_on": d.isoformat(),
                            "fill_timing": "CLOSE",
                            "value_before": value_before,
                            "value_after": value_after,
                            "budget_cap": budget_cap,
                            "budget_used": used,
                            "turnover_pct": (
                                (used / value_before * 100.0) if value_before else 0.0
                            ),
                            "targets": targets_sorted,
                            "trades": trades,
                        }
                    )
                else:
                    exec_i = i + 1
                    if exec_i <= sim_end and trade_candidates:
                        pending.setdefault(exec_i, []).append(
                            {
                                "decision_date": d.isoformat(),
                                "value_before": value_before,
                                "budget_cap": budget_cap,
                                "targets": targets_sorted,
                                "trade_candidates": trade_candidates,
                            }
                        )

        v = _portfolio_value(cash=cash, positions=positions, px_by_key=px_close_by_key)
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
            "fill_timing": config.fill_timing,
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
            "risk_window": int(config.risk_window),
            "min_observations": int(config.min_observations),
            "min_weight": float(config.min_weight),
            "max_weight": float(config.max_weight),
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
