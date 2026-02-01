from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable, Optional

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
from app.services.charges_india import estimate_india_equity_charges
from app.services.market_data import Timeframe, load_series

IST_TZ = timezone(timedelta(hours=5, minutes=30))


def _iso_ist(dt: datetime) -> str:
    # Market data timestamps are stored as naive IST in SQLite. Serialise them
    # with an explicit offset so the frontend doesn't misinterpret them as UTC.
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST_TZ).isoformat()
    return dt.astimezone(IST_TZ).isoformat()


@dataclass(frozen=True)
class _IndicatorKey:
    kind: str
    period: int


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


def _series_key(operand: IndicatorOperand) -> _IndicatorKey:
    spec = operand.spec
    kind = str(spec.kind).strip().upper()
    period = int(spec.params.get("period", 0) or 0)
    return _IndicatorKey(kind=kind, period=period)


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


def _compute_volatility_pct_series(
    closes: list[float],
    window: int,
) -> list[Optional[float]]:
    from math import log, sqrt

    n = len(closes)
    if window <= 1:
        return [None] * n
    out: list[Optional[float]] = [None] * n
    for i in range(window, n):
        rets: list[float] = []
        for j in range(i - window + 1, i + 1):
            prev = closes[j - 1]
            curr = closes[j]
            if prev <= 0 or curr <= 0:
                continue
            rets.append(log(curr / prev))
        if len(rets) <= 1:
            continue
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
        out[i] = sqrt(var) * 100.0
    return out


def _compute_atr_pct_series(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int,
) -> list[Optional[float]]:
    n = len(closes)
    if period <= 0 or n < period + 1:
        return [None] * n
    out: list[Optional[float]] = [None] * n
    trs: list[float] = [0.0] * n
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs[i] = tr
    # Simple moving average of TRs.
    window_sum = 0.0
    for i in range(1, n):
        window_sum += trs[i]
        if i >= period:
            window_sum -= trs[i - period]
        if i >= period and closes[i] > 0:
            atr = window_sum / period
            out[i] = (atr / closes[i]) * 100.0
    return out


def _compute_volume_ratio_series(
    volumes: list[float],
    window: int,
) -> list[Optional[float]]:
    n = len(volumes)
    if window <= 0:
        return [None] * n
    out: list[Optional[float]] = [None] * n
    window_sum = 0.0
    for i, _v in enumerate(volumes):
        if i == 0:
            continue
        # average of previous `window` bars excluding current.
        prev_i = i - 1
        window_sum += volumes[prev_i]
        if prev_i - window >= 0:
            window_sum -= volumes[prev_i - window]
        if prev_i + 1 >= window:
            avg = window_sum / window
            if avg > 0:
                out[i] = volumes[i] / avg
    return out


def _compute_vwap_series(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
    window: int,
) -> list[Optional[float]]:
    n = len(closes)
    if window <= 0:
        return [None] * n
    out: list[Optional[float]] = [None] * n
    for i in range(window - 1, n):
        num = 0.0
        den = 0.0
        for j in range(i - window + 1, i + 1):
            typical = (highs[j] + lows[j] + closes[j]) / 3.0
            vol = volumes[j]
            num += typical * vol
            den += vol
        if den > 0:
            out[i] = num / den
    return out


def _resolve_indicator_series(
    indicator_kind: str,
    period: int,
    *,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    volumes: list[float],
) -> list[Optional[float]]:
    kind = indicator_kind.upper()
    if kind == "PRICE":
        return [float(c) for c in closes]
    if kind in {"MA", "SMA"}:
        return _compute_sma_series(closes, period or 50)
    if kind == "RSI":
        return _compute_rsi_series(closes, period or 14)
    if kind in {"PERF_PCT", "MOMENTUM"}:
        return _compute_perf_pct_series(closes, period or 20)
    if kind == "VOLATILITY":
        return _compute_volatility_pct_series(closes, period or 20)
    if kind == "ATR":
        return _compute_atr_pct_series(highs, lows, closes, period or 14)
    if kind == "VOLUME_RATIO":
        return _compute_volume_ratio_series(volumes, period or 20)
    if kind == "VWAP":
        return _compute_vwap_series(highs, lows, closes, volumes, period or 20)
    raise ValueError(f"Unsupported indicator for strategy backtest: {indicator_kind}")


def _eval_operand_at(
    operand: Any,
    series: dict[_IndicatorKey, list[Optional[float]]],
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
        raise ValueError("Field operands are not supported in strategy backtests.")
    return None, None


def _eval_expr_at(
    expr: ExpressionNode,
    series: dict[_IndicatorKey, list[Optional[float]]],
    i: int,
) -> bool:
    if isinstance(expr, NotNode):
        return not _eval_expr_at(expr.child, series, i)
    if isinstance(expr, LogicalNode):
        if expr.op.upper() == "AND":
            return all(_eval_expr_at(c, series, i) for c in expr.children)
        return any(_eval_expr_at(c, series, i) for c in expr.children)
    if not isinstance(expr, ComparisonNode):
        return False

    op = str(expr.operator).upper()
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
        if isinstance(expr.right, NumberOperand):
            level = float(expr.right.value)
            if op == "CROSS_ABOVE":
                return left_prev <= level < left_curr
            return left_prev >= level > left_curr
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


def run_strategy_backtest(
    db: Session,
    settings: Settings,
    *,
    symbol: UniverseSymbolRef,
    config: dict[str, Any],
    allow_fetch: bool = True,
) -> dict[str, Any]:
    """Entry/exit rule backtest for a single symbol.

    Assumptions:
    - Evaluate signals at candle close, execute at next candle open.
    - CNC: long-only.
    - MIS: long/short allowed, and position is squared-off at end of day (IST).
    """

    from app.schemas.backtests_strategy import StrategyBacktestConfigIn

    from app.pydantic_compat import PYDANTIC_V2

    cfg = (
        StrategyBacktestConfigIn.model_validate(config)
        if PYDANTIC_V2
        else StrategyBacktestConfigIn.parse_obj(config)
    )

    tf: Timeframe = cfg.timeframe  # type: ignore[assignment]
    if cfg.product == "CNC" and cfg.direction != "LONG":
        raise ValueError("CNC does not allow short selling; use direction LONG.")
    if cfg.product == "MIS" and cfg.timeframe == "1d":
        raise ValueError("MIS product requires an intraday timeframe (<= 1h).")

    entry_expr = parse_expression(cfg.entry_dsl)
    exit_expr = parse_expression(cfg.exit_dsl)

    needed: set[_IndicatorKey] = set()
    for op in list(_iter_indicator_operands(entry_expr)) + list(
        _iter_indicator_operands(exit_expr)
    ):
        needed.add(_series_key(op))

    reentry_enabled = (
        bool(cfg.allow_reentry_after_trailing_stop) and cfg.direction == "LONG"
    )
    if reentry_enabled:
        needed.add(_IndicatorKey(kind="MA", period=9))
        needed.add(_IndicatorKey(kind="MA", period=45))

    max_period = max([k.period for k in needed if k.period] + [20])
    if cfg.timeframe == "1d":
        lookback_days = max(30, int(max_period) * 3)
    else:
        bars_per_day = {
            "1m": 375,
            "5m": 75,
            "15m": 25,
            "30m": 13,
            "1h": 6,
        }.get(cfg.timeframe, 75)
        lookback_days = max(5, int(math.ceil(max_period / bars_per_day)) + 3)

    start_dt = datetime.combine(cfg.start_date, time.min) - timedelta(
        days=lookback_days,
    )
    end_dt = datetime.combine(cfg.end_date, time.max)

    candles = load_series(
        db,
        settings,
        symbol=symbol.symbol,
        exchange=symbol.exchange,
        timeframe=tf,
        start=start_dt,
        end=end_dt,
        allow_fetch=allow_fetch,
    )
    if not candles:
        raise ValueError("No candles available.")

    ts: list[datetime] = []
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    volumes: list[float] = []
    for c in candles:
        t = c.get("ts")
        if not isinstance(t, datetime):
            continue
        o = float(c.get("open") or 0.0)
        h = float(c.get("high") or 0.0)
        lo = float(c.get("low") or 0.0)
        close = float(c.get("close") or 0.0)
        v = float(c.get("volume") or 0.0)
        if close <= 0 or o <= 0 or h <= 0 or lo <= 0:
            continue
        ts.append(t)
        opens.append(o)
        highs.append(h)
        lows.append(lo)
        closes.append(close)
        volumes.append(v)

    if not ts:
        raise ValueError("No valid candles available.")

    sim_start_dt = datetime.combine(cfg.start_date, time.min)
    sim_end_dt = datetime.combine(cfg.end_date, time.max)
    sim_start = None
    sim_end = None
    for i, t in enumerate(ts):
        if sim_start is None and t >= sim_start_dt:
            sim_start = i
        if t <= sim_end_dt:
            sim_end = i
    if sim_start is None or sim_end is None or sim_start > sim_end:
        raise ValueError("No candles in the selected window.")

    series: dict[_IndicatorKey, list[Optional[float]]] = {}
    for k in needed:
        series[k] = _resolve_indicator_series(
            k.kind,
            k.period,
            closes=closes,
            highs=highs,
            lows=lows,
            volumes=volumes,
        )

    slip = float(cfg.slippage_bps) / 10000.0
    charges_rate = (
        float(cfg.charges_bps) / 10000.0 if cfg.charges_model == "BPS" else None
    )

    def est_charges(*, side: str, notional: float) -> float:
        if charges_rate is not None:
            return float(notional) * float(charges_rate)
        ex = symbol.exchange.upper()
        return float(
            estimate_india_equity_charges(
                broker=str(cfg.charges_broker).lower() or "zerodha",
                product=str(cfg.product).upper(),
                side=side,
                exchange="BSE" if ex == "BSE" else "NSE",
                turnover=float(notional),
                stamp_state="WEST_BENGAL",
                include_dp=bool(cfg.include_dp_charges),
            ).total
        )

    cash = float(cfg.initial_cash)
    qty = 0  # positive long, negative short
    entry_fill: float | None = None
    entry_ts: datetime | None = None
    first_long_entry_idx: int | None = None
    peak_since_entry: float | None = None
    trough_since_entry: float | None = None
    initial_sl_price: float | None = None
    take_profit_price: float | None = None
    trail_price: float | None = None
    trailing_active = False
    entry_reason: str | None = None
    peak_equity_since_entry: float | None = None
    trading_disabled = False

    last_exit_reason: str | None = None
    cooldown_remaining = 0
    trend_id = 0
    trend_prev_active = False
    trend_had_break = False
    reentries_in_trend = 0

    pending_entry: tuple[int, str, str] | None = (
        None  # (exec_index, side, entry_reason)
    )
    pending_exit: tuple[int, str, str] | None = None  # (exec_index, side, reason)

    equity: list[float] = []
    dd: list[float] = []
    peak = -math.inf

    trades: list[dict[str, Any]] = []
    trade_pnl_pct: list[float] = []
    total_turnover = 0.0
    total_charges = 0.0

    def equity_now(i: int) -> float:
        return float(cash) + float(qty) * float(closes[i])

    def force_close_position(i: int, *, reason: str) -> None:
        nonlocal cash, qty, entry_fill, entry_ts, peak_since_entry, trough_since_entry
        nonlocal initial_sl_price, take_profit_price, trail_price, trailing_active
        nonlocal entry_reason, last_exit_reason, cooldown_remaining
        nonlocal total_turnover, total_charges

        if qty == 0:
            return
        side = "SELL" if qty > 0 else "BUY"
        if qty > 0:
            fill_px = float(closes[i]) * (1.0 - slip)
        else:
            fill_px = float(closes[i]) * (1.0 + slip)
        notional = abs(int(qty)) * float(closes[i])
        ch = est_charges(side=side, notional=notional)
        total_charges += ch
        total_turnover += notional
        if qty > 0:
            cash += abs(int(qty)) * fill_px - ch
        else:
            cash -= abs(int(qty)) * fill_px + ch

        if entry_fill is not None and entry_ts is not None:
            ret_pct = (
                (fill_px / entry_fill - 1.0) * 100.0
                if qty > 0
                else (entry_fill / fill_px - 1.0) * 100.0
            )
            trade_pnl_pct.append(float(ret_pct))
            trades.append(
                {
                    "entry_ts": _iso_ist(entry_ts),
                    "exit_ts": _iso_ist(ts[i]),
                    "side": "LONG" if qty > 0 else "SHORT",
                    "entry_price": float(entry_fill),
                    "exit_price": float(fill_px),
                    "qty": int(abs(int(qty))),
                    "pnl_pct": float(ret_pct),
                    "reason": reason,
                    "entry_reason": entry_reason,
                }
            )

        qty = 0
        entry_fill = None
        entry_ts = None
        peak_since_entry = None
        trough_since_entry = None
        initial_sl_price = None
        take_profit_price = None
        trail_price = None
        trailing_active = False
        entry_reason = None
        last_exit_reason = reason
        cooldown_remaining = 0

    for i in range(sim_start, sim_end + 1):
        # Execute pending orders at this candle open.
        if pending_entry and pending_entry[0] == i and qty == 0:
            _, side, ent_reason = pending_entry
            if side == "BUY":
                fill_px = float(opens[i]) * (1.0 + slip)
            else:
                fill_px = float(opens[i]) * (1.0 - slip)
            # size by cash/equity at decision time (previous close)
            decision_eq = equity_now(i - 1) if i - 1 >= 0 else cash
            deploy = decision_eq * (float(cfg.position_size_pct) / 100.0)
            deploy = min(deploy, cash if side == "BUY" else deploy)
            qty_int = int(math.floor(deploy / fill_px)) if fill_px > 0 else 0
            if qty_int > 0:
                notional = qty_int * float(opens[i])
                ch = est_charges(side=side, notional=notional)
                total_charges += ch
                total_turnover += notional
                if side == "BUY":
                    if cash >= qty_int * fill_px + ch:
                        cash -= qty_int * fill_px + ch
                        qty = qty_int
                        entry_fill = float(fill_px)
                        entry_ts = ts[i]
                        peak_since_entry = float(entry_fill)
                        trough_since_entry = float(entry_fill)
                        stop_pct = float(cfg.stop_loss_pct or 0.0)
                        tp_pct = float(cfg.take_profit_pct or 0.0)
                        trail_pct = float(cfg.trailing_stop_pct or 0.0)
                        initial_sl_price = (
                            float(entry_fill) * (1.0 - stop_pct / 100.0)
                            if stop_pct > 0
                            else None
                        )
                        take_profit_price = (
                            float(entry_fill) * (1.0 + tp_pct / 100.0)
                            if tp_pct > 0
                            else None
                        )
                        trailing_active = False
                        trail_price = float(entry_fill) if trail_pct > 0 else None
                        entry_reason = (
                            ent_reason if ent_reason == "REENTRY_TREND" else None
                        )
                        if ent_reason == "REENTRY_TREND":
                            reentries_in_trend += 1
                        last_exit_reason = None
                        if first_long_entry_idx is None:
                            first_long_entry_idx = i
                        peak_equity_since_entry = float(cash) + float(qty) * float(
                            fill_px
                        )
                else:
                    # short sell: proceeds increase cash but we do not allow
                    # pyramiding (single-position backtest).
                    cash += qty_int * fill_px - ch
                    qty = -qty_int
                    entry_fill = float(fill_px)
                    entry_ts = ts[i]
                    peak_since_entry = float(entry_fill)
                    trough_since_entry = float(entry_fill)
                    stop_pct = float(cfg.stop_loss_pct or 0.0)
                    tp_pct = float(cfg.take_profit_pct or 0.0)
                    trail_pct = float(cfg.trailing_stop_pct or 0.0)
                    initial_sl_price = (
                        float(entry_fill) * (1.0 + stop_pct / 100.0)
                        if stop_pct > 0
                        else None
                    )
                    take_profit_price = (
                        float(entry_fill) * (1.0 - tp_pct / 100.0)
                        if tp_pct > 0
                        else None
                    )
                    trailing_active = False
                    trail_price = float(entry_fill) if trail_pct > 0 else None
                    entry_reason = None
                    last_exit_reason = None
                    peak_equity_since_entry = float(cash) + float(qty) * float(fill_px)
            pending_entry = None

        if pending_exit and pending_exit[0] == i and qty != 0:
            _, side, reason = pending_exit
            exit_reason = reason
            if side == "BUY":
                fill_px = float(opens[i]) * (1.0 + slip)
            else:
                fill_px = float(opens[i]) * (1.0 - slip)
            qty_int = abs(int(qty))
            notional = qty_int * float(opens[i])
            ch = est_charges(side=side, notional=notional)
            total_charges += ch
            total_turnover += notional
            if side == "SELL":
                cash += qty_int * fill_px - ch
            else:
                cash -= qty_int * fill_px + ch

            if entry_fill is not None and entry_ts is not None:
                if reason == "TRAILING_STOP":
                    # Trailing stop is profit-protecting: never attribute a losing
                    # exit to trailing (gaps/slippage can still produce a loss).
                    if qty > 0 and fill_px < entry_fill:
                        exit_reason = "STOP_LOSS"
                    if qty < 0 and fill_px > entry_fill:
                        exit_reason = "STOP_LOSS"
                ret_pct = (
                    (fill_px / entry_fill - 1.0) * 100.0
                    if qty > 0
                    else (entry_fill / fill_px - 1.0) * 100.0
                )
                trade_pnl_pct.append(float(ret_pct))
                trades.append(
                    {
                        "entry_ts": _iso_ist(entry_ts),
                        "exit_ts": _iso_ist(ts[i]),
                        "side": "LONG" if qty > 0 else "SHORT",
                        "entry_price": float(entry_fill),
                        "exit_price": float(fill_px),
                        "qty": int(qty_int),
                        "pnl_pct": float(ret_pct),
                        "reason": exit_reason,
                        "entry_reason": entry_reason,
                    }
                )
            qty = 0
            entry_fill = None
            entry_ts = None
            peak_since_entry = None
            trough_since_entry = None
            initial_sl_price = None
            take_profit_price = None
            trail_price = None
            trailing_active = False
            peak_equity_since_entry = None
            entry_reason = None
            if exit_reason == "TRAILING_STOP" and reentry_enabled:
                last_exit_reason = "TRAILING_STOP"
                cooldown_remaining = int(cfg.reentry_cooldown_bars) + 1
            else:
                last_exit_reason = exit_reason
                cooldown_remaining = 0
            pending_exit = None

        # Risk controls evaluated at close; schedule exit next open.
        if qty != 0 and entry_fill is not None:
            close_px = float(closes[i])
            next_i = i + 1
            if qty > 0:
                peak_since_entry = max(
                    float(peak_since_entry or entry_fill),
                    close_px,
                )
                trail_pct = float(cfg.trailing_stop_pct or 0.0)
                if trail_pct > 0 and peak_since_entry is not None:
                    activate_when = float(entry_fill) * (1.0 + trail_pct / 100.0)
                    if float(peak_since_entry) >= activate_when:
                        trailing_active = True
                    if trailing_active:
                        candidate = float(peak_since_entry) * (1.0 - trail_pct / 100.0)
                        prev = float(
                            trail_price if trail_price is not None else entry_fill
                        )
                        trail_price = max(prev, candidate, float(entry_fill))

                effective_stop = initial_sl_price
                if trailing_active and trail_price is not None:
                    effective_stop = (
                        float(trail_price)
                        if effective_stop is None
                        else max(float(effective_stop), float(trail_price))
                    )

                if next_i <= sim_end:
                    if take_profit_price is not None and close_px >= float(
                        take_profit_price
                    ):
                        pending_exit = (next_i, "SELL", "TAKE_PROFIT")
                    elif effective_stop is not None and close_px <= float(
                        effective_stop
                    ):
                        if (not trailing_active) or (
                            initial_sl_price is not None
                            and close_px <= float(initial_sl_price)
                        ):
                            pending_exit = (next_i, "SELL", "STOP_LOSS")
                        else:
                            pending_exit = (next_i, "SELL", "TRAILING_STOP")
            else:
                trough_since_entry = min(
                    float(trough_since_entry or entry_fill),
                    close_px,
                )
                trail_pct = float(cfg.trailing_stop_pct or 0.0)
                if trail_pct > 0 and trough_since_entry is not None:
                    activate_when = float(entry_fill) * (1.0 - trail_pct / 100.0)
                    if float(trough_since_entry) <= activate_when:
                        trailing_active = True
                    if trailing_active:
                        candidate = float(trough_since_entry) * (
                            1.0 + trail_pct / 100.0
                        )
                        prev = float(
                            trail_price if trail_price is not None else entry_fill
                        )
                        trail_price = min(prev, candidate, float(entry_fill))

                effective_stop = initial_sl_price
                if trailing_active and trail_price is not None:
                    effective_stop = (
                        float(trail_price)
                        if effective_stop is None
                        else min(float(effective_stop), float(trail_price))
                    )

                if next_i <= sim_end:
                    if take_profit_price is not None and close_px <= float(
                        take_profit_price
                    ):
                        pending_exit = (next_i, "BUY", "TAKE_PROFIT")
                    elif effective_stop is not None and close_px >= float(
                        effective_stop
                    ):
                        if (not trailing_active) or (
                            initial_sl_price is not None
                            and close_px >= float(initial_sl_price)
                        ):
                            pending_exit = (next_i, "BUY", "STOP_LOSS")
                        else:
                            pending_exit = (next_i, "BUY", "TRAILING_STOP")

        # Trend / re-entry bookkeeping (evaluate at close).
        trend_active = False
        fast_ma = None
        slow_ma = None
        if reentry_enabled:
            ma9 = series.get(_IndicatorKey(kind="MA", period=9))
            ma45 = series.get(_IndicatorKey(kind="MA", period=45))
            if ma9 is not None and ma45 is not None and 0 <= i < len(closes):
                fast_ma = ma9[i]
                slow_ma = ma45[i]
                if fast_ma is not None and slow_ma is not None:
                    close_px = float(closes[i])
                    trend_active = close_px > float(slow_ma) and float(
                        fast_ma
                    ) >= float(slow_ma)

            if trend_prev_active and not trend_active:
                trend_had_break = True
            if (not trend_prev_active) and trend_active and trend_had_break:
                trend_id += 1
                trend_had_break = False
                reentries_in_trend = 0
                last_exit_reason = None
                cooldown_remaining = 0
            trend_prev_active = trend_active

            if cooldown_remaining > 0:
                cooldown_remaining -= 1

        # Signal evaluation at close; schedule orders for next open.
        if i < sim_end:
            if qty == 0 and pending_entry is None and not trading_disabled:
                if _eval_expr_at(entry_expr, series, i):
                    if cfg.direction == "LONG":
                        pending_entry = (i + 1, "BUY", "ENTRY_SIGNAL")
                    elif cfg.product == "MIS":
                        pending_entry = (i + 1, "SELL", "ENTRY_SIGNAL")
                elif reentry_enabled and last_exit_reason == "TRAILING_STOP":
                    max_re = int(cfg.max_reentries_per_trend or 0)
                    if max_re <= 0 or reentries_in_trend < max_re:
                        if cooldown_remaining == 0 and trend_active:
                            if (
                                cfg.reentry_trigger == "CLOSE_CROSSES_ABOVE_FAST_MA"
                                and fast_ma is not None
                                and i - 1 >= 0
                            ):
                                ma9 = series.get(_IndicatorKey(kind="MA", period=9))
                                prev_fast = (
                                    ma9[i - 1]
                                    if ma9 is not None and i - 1 < len(ma9)
                                    else None
                                )
                                prev_close = float(closes[i - 1])
                                close_px = float(closes[i])
                                if (
                                    prev_fast is not None
                                    and prev_close <= float(prev_fast)
                                    and close_px > float(fast_ma)
                                ):
                                    pending_entry = (i + 1, "BUY", "REENTRY_TREND")
            if qty != 0 and pending_exit is None:
                if _eval_expr_at(exit_expr, series, i):
                    pending_exit = (i + 1, "SELL" if qty > 0 else "BUY", "EXIT_SIGNAL")

        # MIS square-off: force exit at last candle of the day.
        if cfg.product == "MIS" and qty != 0:
            is_last_bar = i == sim_end or ts[i + 1].date() != ts[i].date()
            if is_last_bar:
                force_close_position(i, reason="EOD_SQUARE_OFF")
                pending_exit = None
                pending_entry = None

        v = equity_now(i)
        if qty != 0:
            peak_equity_since_entry = max(float(peak_equity_since_entry or v), float(v))
        else:
            peak_equity_since_entry = None

        equity.append(v)
        peak = max(peak, v)
        dd_global_pct = (v / peak - 1.0) * 100.0 if peak > 0 else 0.0
        dd.append(float(dd_global_pct))

        # Equity drawdown controls (evaluate at close, execute at next open).
        if i < sim_end and pending_exit is None:
            next_i = i + 1
            max_dd_global = float(cfg.max_equity_dd_global_pct or 0.0)
            max_dd_trade = float(cfg.max_equity_dd_trade_pct or 0.0)

            if max_dd_global > 0 and dd_global_pct <= -max_dd_global:
                trading_disabled = True
                pending_entry = None
                if qty != 0:
                    pending_exit = (
                        next_i,
                        "SELL" if qty > 0 else "BUY",
                        "EQUITY_DD_GLOBAL",
                    )

            if (
                pending_exit is None
                and qty != 0
                and max_dd_trade > 0
                and peak_equity_since_entry is not None
                and peak_equity_since_entry > 0
            ):
                dd_trade_pct = (v / peak_equity_since_entry - 1.0) * 100.0
                if dd_trade_pct <= -max_dd_trade:
                    pending_exit = (
                        next_i,
                        "SELL" if qty > 0 else "BUY",
                        "EQUITY_DD_TRADE",
                    )

    # Close any open position at end of backtest (strategy ends).
    if qty != 0:
        force_close_position(sim_end, reason="END_OF_TEST")
        equity[-1] = float(cash)
        peak = -math.inf
        dd = []
        for v in equity:
            peak = max(peak, v)
            dd.append((v / peak - 1.0) * 100.0 if peak > 0 else 0.0)

    if not equity:
        raise ValueError("No equity series produced.")

    start_val = float(equity[0])
    end_val = float(equity[-1])
    total_return_pct = (end_val / start_val - 1.0) * 100.0 if start_val > 0 else 0.0

    duration_days = max(1, (ts[sim_end] - ts[sim_start]).days + 1)
    years = duration_days / 365.25
    if years > 0 and start_val > 0:
        cagr_pct = ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0
    else:
        cagr_pct = 0.0

    max_drawdown_pct = abs(min(dd)) if dd else 0.0
    avg_equity = sum(equity) / len(equity) if equity else 0.0
    turnover_pct_total = (
        (total_turnover / avg_equity * 100.0) if avg_equity > 0 else 0.0
    )

    win_rate_pct = (
        (sum(1 for x in trade_pnl_pct if x > 0) / len(trade_pnl_pct) * 100.0)
        if trade_pnl_pct
        else 0.0
    )

    trade_stats = {
        "count": len(trade_pnl_pct),
        "win_rate_pct": float(win_rate_pct),
        "avg_pnl_pct": (
            float(sum(trade_pnl_pct) / len(trade_pnl_pct)) if trade_pnl_pct else 0.0
        ),
        "pnl_percentiles": (
            _percentiles(trade_pnl_pct, [0.1, 0.5, 0.9]) if trade_pnl_pct else {}
        ),
    }

    # Baselines: buy-and-hold (long only).
    buy_hold: dict[str, Any] = {}

    def _hold_curve(buy_i: int) -> dict[str, Any]:
        if buy_i is None:
            return {}
        buy_px = float(opens[buy_i])
        qty_hold = (
            int(math.floor(float(cfg.initial_cash) / buy_px)) if buy_px > 0 else 0
        )
        if qty_hold <= 0:
            return {}
        cash_hold = float(cfg.initial_cash) - qty_hold * buy_px
        curve = [
            cash_hold + qty_hold * float(closes[j])
            for j in range(sim_start, sim_end + 1)
        ]
        start_h = float(curve[0])
        end_h = float(curve[-1])
        ret = (end_h / start_h - 1.0) * 100.0 if start_h > 0 else 0.0
        return {
            "buy_ts": _iso_ist(ts[buy_i]),
            "total_return_pct": float(ret),
            "equity": curve,
        }

    buy_hold["start_to_end"] = _hold_curve(sim_start)
    if first_long_entry_idx is not None:
        buy_hold["first_entry_to_end"] = _hold_curve(first_long_entry_idx)

    return {
        "meta": {
            "symbol": symbol.key,
            "timeframe": cfg.timeframe,
            "start_date": cfg.start_date.isoformat(),
            "end_date": cfg.end_date.isoformat(),
            "entry_dsl": cfg.entry_dsl,
            "exit_dsl": cfg.exit_dsl,
            "product": cfg.product,
            "direction": cfg.direction,
            "initial_cash": float(cfg.initial_cash),
            "position_size_pct": float(cfg.position_size_pct),
            "stop_loss_pct": float(cfg.stop_loss_pct),
            "take_profit_pct": float(cfg.take_profit_pct),
            "trailing_stop_pct": float(cfg.trailing_stop_pct),
            "max_equity_dd_global_pct": float(cfg.max_equity_dd_global_pct),
            "max_equity_dd_trade_pct": float(cfg.max_equity_dd_trade_pct),
            "slippage_bps": float(cfg.slippage_bps),
            "charges_model": cfg.charges_model,
            "charges_bps": float(cfg.charges_bps),
            "charges_broker": cfg.charges_broker,
            "include_dp_charges": bool(cfg.include_dp_charges),
        },
        "series": {
            "ts": [_iso_ist(t) for t in ts[sim_start : sim_end + 1]],
            "equity": equity,
            "drawdown_pct": dd,
        },
        "metrics": {
            "total_return_pct": float(total_return_pct),
            "cagr_pct": float(cagr_pct),
            "max_drawdown_pct": float(max_drawdown_pct),
            "turnover_pct_total": float(turnover_pct_total),
            "total_turnover": float(total_turnover),
            "total_charges": float(total_charges),
        },
        "trades": trades,
        "trade_stats": trade_stats,
        "baselines": buy_hold,
    }


__all__ = ["run_strategy_backtest"]
