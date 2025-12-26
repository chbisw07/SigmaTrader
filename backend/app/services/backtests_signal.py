from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Literal, Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.alert_expression import (
    ComparisonNode,
    ExpressionNode,
    FieldOperand,
    IndicatorOperand,
    LogicalNode,
    NotNode,
    NumberOperand,
)
from app.services.alert_expression_dsl import parse_expression
from app.services.backtests_data import UniverseSymbolRef
from app.services.market_data import load_series

SignalMode = Literal["DSL", "RANKING"]
RankingCadence = Literal["WEEKLY", "MONTHLY"]
RankingMetric = Literal["PERF_PCT"]


@dataclass(frozen=True)
class SignalBacktestConfig:
    mode: SignalMode
    start_date: date
    end_date: date
    forward_windows: list[int]

    # DSL mode
    dsl: str = ""

    # Ranking mode
    ranking_metric: RankingMetric = "PERF_PCT"
    ranking_window: int = 20
    top_n: int = 10
    cadence: RankingCadence = "MONTHLY"


def _iter_indicator_operands(expr: ExpressionNode) -> Iterable[IndicatorOperand]:
    if isinstance(expr, ComparisonNode):
        for op in (expr.left, expr.right):
            if isinstance(op, IndicatorOperand):
                yield op
        return
    if isinstance(expr, NotNode):
        yield from _iter_indicator_operands(expr.child)
        return
    if isinstance(expr, LogicalNode):
        for child in expr.children:
            yield from _iter_indicator_operands(child)


def _iter_field_operands(expr: ExpressionNode) -> Iterable[FieldOperand]:
    if isinstance(expr, ComparisonNode):
        for op in (expr.left, expr.right):
            if isinstance(op, FieldOperand):
                yield op
        return
    if isinstance(expr, NotNode):
        yield from _iter_field_operands(expr.child)
        return
    if isinstance(expr, LogicalNode):
        for child in expr.children:
            yield from _iter_field_operands(child)


def _series_key(operand: IndicatorOperand) -> tuple[str, str, int]:
    spec = operand.spec
    tf = (spec.timeframe or "1d").strip().lower()
    period = int(spec.params.get("period", 0) or 0)
    return spec.kind.strip().upper(), tf, period


def _compute_sma_series(closes: list[float], period: int) -> list[Optional[float]]:
    n = len(closes)
    if period <= 0:
        return [None] * n
    out: list[Optional[float]] = [None] * n
    window_sum = 0.0
    for i, c in enumerate(closes):
        window_sum += c
        if i >= period:
            window_sum -= closes[i - period]
        if i >= period - 1:
            out[i] = window_sum / period
    return out


def _compute_perf_pct_series(closes: list[float], window: int) -> list[Optional[float]]:
    n = len(closes)
    if window <= 0:
        return [None] * n
    out: list[Optional[float]] = [None] * n
    for i in range(window, n):
        base = closes[i - window]
        curr = closes[i]
        if base > 0:
            out[i] = (curr / base - 1.0) * 100.0
    return out


def _compute_rsi_series(closes: list[float], period: int) -> list[Optional[float]]:
    n = len(closes)
    if period <= 0 or n < period + 1:
        return [None] * n
    out: list[Optional[float]] = [None] * n

    gains: list[float] = [0.0] * n
    losses: list[float] = [0.0] * n
    for i in range(1, n):
        d = closes[i] - closes[i - 1]
        gains[i] = d if d > 0 else 0.0
        losses[i] = -d if d < 0 else 0.0

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period

    def _rsi(gain: float, loss: float) -> float:
        if loss <= 0:
            return 100.0
        rs = gain / loss
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def _resolve_indicator_series(
    indicator_kind: str,
    tf: str,
    period: int,
    closes: list[float],
) -> list[Optional[float]]:
    if tf != "1d":
        raise ValueError("Signal backtest currently supports EOD (1d) only.")
    kind = indicator_kind.upper()
    if kind == "PRICE":
        return [float(c) for c in closes]
    if kind in {"MA", "SMA"}:
        return _compute_sma_series(closes, period or 50)
    if kind == "RSI":
        return _compute_rsi_series(closes, period or 14)
    if kind in {"PERF_PCT", "MOMENTUM"}:
        return _compute_perf_pct_series(closes, period or 20)
    raise ValueError(f"Unsupported indicator for signal backtest: {indicator_kind}")


def _eval_operand_at(
    operand: Any,
    series: dict[tuple[str, str, int], list[Optional[float]]],
    i: int,
) -> tuple[Optional[float], Optional[float]]:
    if isinstance(operand, NumberOperand):
        return float(operand.value), float(operand.value)
    if isinstance(operand, IndicatorOperand):
        key = _series_key(operand)
        s = series.get(key)
        if not s:
            return None, None
        curr = s[i] if 0 <= i < len(s) else None
        prev = s[i - 1] if i - 1 >= 0 and i - 1 < len(s) else None
        return curr, prev
    if isinstance(operand, FieldOperand):
        raise ValueError("Field operands are not supported in signal backtests.")
    return None, None


def _eval_expr_at(
    expr: ExpressionNode,
    series: dict[tuple[str, str, int], list[Optional[float]]],
    i: int,
) -> bool:
    if isinstance(expr, NotNode):
        return not _eval_expr_at(expr.child, series, i)
    if isinstance(expr, LogicalNode):
        if expr.op.upper() == "AND":
            return all(_eval_expr_at(c, series, i) for c in expr.children)
        return any(_eval_expr_at(c, series, i) for c in expr.children)
    if not isinstance(expr, ComparisonNode):
        # Operand-only expressions are not allowed in this backtest mode.
        return False

    op = expr.operator.upper()
    left_curr, left_prev = _eval_operand_at(expr.left, series, i)
    right_curr, right_prev = _eval_operand_at(expr.right, series, i)

    if left_curr is None:
        return False

    if op == "GT":
        return right_curr is not None and left_curr > right_curr
    if op == "GTE":
        return right_curr is not None and left_curr >= right_curr
    if op == "LT":
        return right_curr is not None and left_curr < right_curr
    if op == "LTE":
        return right_curr is not None and left_curr <= right_curr
    if op == "EQ":
        return right_curr is not None and left_curr == right_curr
    if op == "NEQ":
        return right_curr is not None and left_curr != right_curr

    if op in {"CROSS_ABOVE", "CROSS_BELOW"}:
        if left_prev is None:
            return False
        # constant level
        if isinstance(expr.right, NumberOperand):
            level = float(expr.right.value)
            if op == "CROSS_ABOVE":
                return left_prev <= level < left_curr
            return left_prev >= level > left_curr
        # indicator vs indicator
        if right_curr is None or right_prev is None:
            return False
        if op == "CROSS_ABOVE":
            return left_prev <= right_prev and left_curr > right_curr
        return left_prev >= right_prev and left_curr < right_curr

    return False


def _percentiles(values: list[float], pcts: list[float]) -> dict[str, float]:
    if not values:
        return {}
    xs = sorted(values)
    n = len(xs)

    def pick(p: float) -> float:
        if n == 1:
            return xs[0]
        pos = p * (n - 1)
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        w = pos - lo
        return xs[lo] * (1 - w) + xs[hi] * w

    return {f"p{int(p*100)}": float(pick(p)) for p in pcts}


def _rebalance_indices(dates: list[date], cadence: RankingCadence) -> list[int]:
    if not dates:
        return []
    if cadence == "WEEKLY":
        out = []
        last_week = None
        for i, d in enumerate(dates):
            week = d.isocalendar().week
            if last_week is None:
                last_week = week
                continue
            if week != last_week:
                out.append(i - 1)
                last_week = week
        out.append(len(dates) - 1)
        return sorted(set(out))

    # MONTHLY: use last trading day of each month.
    out = []
    last_month = dates[0].month
    for i, d in enumerate(dates):
        if d.month != last_month:
            out.append(i - 1)
            last_month = d.month
    out.append(len(dates) - 1)
    return sorted(set(out))


def run_signal_backtest(
    db: Session,
    settings: Settings,
    *,
    symbols: list[UniverseSymbolRef],
    config: SignalBacktestConfig,
    allow_fetch: bool = True,
) -> dict[str, Any]:
    # Use a conservative lookback so indicators have enough history.
    lookback_days = 400
    start_dt = datetime.combine(config.start_date, datetime.min.time()) - timedelta(
        days=lookback_days
    )
    end_dt = datetime.combine(config.end_date, datetime.min.time()) + timedelta(days=1)

    forward_windows = [int(w) for w in config.forward_windows if int(w) > 0]
    forward_windows = sorted(set(forward_windows)) or [1, 5, 20]

    event_returns: dict[int, list[float]] = {w: [] for w in forward_windows}
    event_count = 0
    missing_symbols: list[str] = []
    loaded_symbols = 0

    per_symbol_dates: dict[str, list[date]] = {}
    per_symbol_closes: dict[str, list[float]] = {}

    for s in symbols:
        key = s.key
        rows = load_series(
            db,
            settings,
            symbol=s.symbol,
            exchange=s.exchange,
            timeframe="1d",
            start=start_dt,
            end=end_dt,
            allow_fetch=allow_fetch,
        )
        if not rows:
            missing_symbols.append(key)
            continue
        dates_s: list[date] = []
        closes_s: list[float] = []
        for r in rows:
            ts = r.get("ts")
            close = r.get("close")
            if ts is None or close is None:
                continue
            try:
                c = float(close)
            except (TypeError, ValueError):
                continue
            if c <= 0:
                continue
            dates_s.append(ts.date())
            closes_s.append(c)
        if not closes_s:
            missing_symbols.append(key)
            continue
        per_symbol_dates[key] = dates_s
        per_symbol_closes[key] = closes_s
        loaded_symbols += 1

    # Determine an evaluation calendar from the union of all available trading dates.
    all_dates = sorted({d for ds in per_symbol_dates.values() for d in ds})
    dates_in_window = [
        d for d in all_dates if config.start_date <= d <= config.end_date
    ]
    if not dates_in_window:
        return {
            "meta": {
                "mode": config.mode,
                "start_date": config.start_date.isoformat(),
                "end_date": config.end_date.isoformat(),
                "forward_windows": forward_windows,
                "symbols_requested": len(symbols),
                "symbols_loaded": loaded_symbols,
                "symbols_missing": missing_symbols,
            },
            "error": "No candles in the selected window.",
        }

    if config.mode == "DSL":
        expr = parse_expression(config.dsl or "")
        if list(_iter_field_operands(expr)):
            raise ValueError("Signal backtest DSL does not support FIELD operands.")

        # Precompute indicator series per symbol.
        operands = list(_iter_indicator_operands(expr))
        needed = sorted({_series_key(o) for o in operands})

        for key, closes_full in per_symbol_closes.items():
            dates_s = per_symbol_dates[key]
            idx_by_date = {d: i for i, d in enumerate(dates_s)}
            window_indices = [
                idx_by_date[d] for d in dates_in_window if d in idx_by_date
            ]
            if not window_indices:
                continue
            series_map: dict[tuple[str, str, int], list[Optional[float]]] = {}
            for kind, tf, period in needed:
                series_map[(kind, tf, period)] = _resolve_indicator_series(
                    kind, tf, period, closes_full
                )

            for i in window_indices:
                if not _eval_expr_at(expr, series_map, i):
                    continue
                price_i = closes_full[i]
                if price_i <= 0:
                    continue
                event_count += 1
                for w in forward_windows:
                    j = i + w
                    if j >= len(closes_full):
                        continue
                    price_j = closes_full[j]
                    if price_j <= 0:
                        continue
                    r = (price_j / price_i - 1.0) * 100.0
                    if r == r:  # not NaN
                        event_returns[w].append(float(r))

    else:
        # Ranking mode: pick Top-N symbols at each rebalance date by PERF_PCT(window).
        if config.ranking_metric != "PERF_PCT":
            raise ValueError("Only PERF_PCT ranking is supported in v1.")
        rebalance_dates = [
            dates_in_window[i]
            for i in _rebalance_indices(dates_in_window, config.cadence)
        ]
        window = max(1, int(config.ranking_window))

        for d in rebalance_dates:
            scores: list[tuple[str, float]] = []
            for key, dates_s in per_symbol_dates.items():
                idx_by_date = {dd: ii for ii, dd in enumerate(dates_s)}
                i = idx_by_date.get(d)
                if i is None or i - window < 0:
                    continue
                closes_s = per_symbol_closes[key]
                p0 = closes_s[i - window]
                p1 = closes_s[i]
                score = (p1 / p0 - 1.0) * 100.0
                scores.append((key, float(score)))
            scores.sort(key=lambda x: x[1], reverse=True)
            picks = scores[: max(1, int(config.top_n))]
            for key, _score in picks:
                dates_s = per_symbol_dates[key]
                idx_by_date = {dd: ii for ii, dd in enumerate(dates_s)}
                i = idx_by_date.get(d)
                if i is None:
                    continue
                closes_s = per_symbol_closes[key]
                price_i = closes_s[i]
                event_count += 1
                for w in forward_windows:
                    j = i + w
                    if j >= len(closes_s):
                        continue
                    price_j = closes_s[j]
                    r = (price_j / price_i - 1.0) * 100.0
                    event_returns[w].append(float(r))

    summary_by_window: dict[str, dict[str, Any]] = {}
    for w, vals in event_returns.items():
        count = len(vals)
        wins = sum(1 for v in vals if v > 0)
        avg = sum(vals) / count if count else None
        pct = _percentiles(vals, [0.1, 0.5, 0.9]) if vals else {}
        summary_by_window[str(w)] = {
            "count": count,
            "win_rate_pct": (wins / count * 100.0) if count else None,
            "avg_return_pct": avg,
            **pct,
        }

    return {
        "meta": {
            "mode": config.mode,
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
            "forward_windows": forward_windows,
            "symbols_requested": len(symbols),
            "symbols_loaded": loaded_symbols,
            "symbols_missing": missing_symbols,
        },
        "events": {
            "total_events": event_count,
        },
        "by_window": summary_by_window,
    }


__all__ = ["SignalBacktestConfig", "run_signal_backtest"]
