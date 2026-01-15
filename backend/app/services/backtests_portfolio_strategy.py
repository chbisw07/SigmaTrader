from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.backtests_portfolio_strategy import PortfolioStrategyBacktestConfigIn
from app.services.alert_expression_dsl import parse_expression
from app.services.backtests_data import UniverseSymbolRef
from app.services.backtests_strategy import (
    _eval_expr_at,
    _IndicatorKey,
    _iter_indicator_operands,
    _resolve_indicator_series,
    _series_key,
)
from app.services.charges_india import estimate_india_equity_charges
from app.services.market_data import Timeframe, load_series

IST_TZ = timezone(timedelta(hours=5, minutes=30))

MAX_SYMBOLS_LOADED = 500
MAX_GLOBAL_BARS = 200_000
MAX_CELL_UPDATES = 10_000_000  # symbols * global_bars
MAX_RETURN_POINTS = 25_000


def _iso_ist(dt: datetime) -> str:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST_TZ).isoformat()
    return dt.astimezone(IST_TZ).isoformat()


@dataclass
class _SymbolBars:
    ref: UniverseSymbolRef
    ts: list[datetime]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]
    sim_start: int
    sim_end: int
    series: dict[_IndicatorKey, list[Optional[float]]]
    rank_series: list[Optional[float]] | None
    idx_by_ts: dict[datetime, int]


@dataclass
class _PositionState:
    qty: int = 0
    entry_fill: float | None = None
    entry_ts: datetime | None = None
    entry_gi: int | None = None
    peak_since_entry: float | None = None
    trough_since_entry: float | None = None
    initial_sl_price: float | None = None
    tp_price: float | None = None
    trail_price: float | None = None
    trailing_active: bool = False
    peak_equity_since_entry: float | None = None
    last_exit_gi: int | None = None


def _is_intraday_timeframe(tf: str) -> bool:
    return tf in {"1m", "5m", "15m", "30m", "1h"}


def _intraday_in_market_hours(ts: datetime) -> bool:
    # Market data timestamps are naive IST.
    t = ts.time()
    return time(9, 15) <= t <= time(15, 30)


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


def run_portfolio_strategy_backtest(
    db: Session,
    settings: Settings,
    *,
    symbols: list[UniverseSymbolRef],
    config: PortfolioStrategyBacktestConfigIn,
    allow_fetch: bool = True,
) -> dict[str, Any]:
    """Portfolio-level entry/exit backtest for many symbols sharing a cash pool.

    Assumptions:
    - Evaluate signals at candle close, execute at next candle open.
    - CNC: long-only.
    - MIS: long/short allowed, and positions are squared-off at end of day (IST).
    - One position per symbol (no pyramiding); symbols compete for shared cash and
      max positions.
    """

    tf: Timeframe = config.timeframe  # type: ignore[assignment]
    if config.product == "CNC" and config.direction != "LONG":
        raise ValueError("CNC does not allow short selling; use direction LONG.")
    if config.product == "MIS" and config.timeframe == "1d":
        raise ValueError("MIS product requires an intraday timeframe (<= 1h).")

    entry_expr = parse_expression(config.entry_dsl)
    exit_expr = parse_expression(config.exit_dsl)

    needed: set[_IndicatorKey] = set()
    for op in list(_iter_indicator_operands(entry_expr)) + list(
        _iter_indicator_operands(exit_expr)
    ):
        needed.add(_series_key(op))

    max_period = max(
        [k.period for k in needed if k.period]
        + [max(20, int(config.ranking_window or 0) or 0)]
    )
    if config.timeframe == "1d":
        lookback_days = max(30, int(max_period) * 3)
    else:
        bars_per_day = {
            "1m": 375,
            "5m": 75,
            "15m": 25,
            "30m": 13,
            "1h": 6,
        }.get(config.timeframe, 75)
        lookback_days = max(5, int(math.ceil(max_period / bars_per_day)) + 3)

    start_dt = datetime.combine(config.start_date, time.min) - timedelta(
        days=lookback_days
    )
    end_dt = datetime.combine(config.end_date, time.max)

    unique: list[UniverseSymbolRef] = []
    seen: set[str] = set()
    for s in symbols:
        if s.key in seen:
            continue
        seen.add(s.key)
        unique.append(s)
    if not unique:
        raise ValueError("No symbols provided.")

    bars_by_key: dict[str, _SymbolBars] = {}
    missing_symbols: list[str] = []

    for s in unique:
        rows = load_series(
            db,
            settings,
            symbol=s.symbol,
            exchange=s.exchange,
            timeframe=tf,
            start=start_dt,
            end=end_dt,
            allow_fetch=allow_fetch,
        )
        if not rows:
            missing_symbols.append(s.key)
            continue

        ts: list[datetime] = []
        opens: list[float] = []
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        volumes: list[float] = []
        for r in rows:
            t = r.get("ts")
            if not isinstance(t, datetime):
                continue
            if _is_intraday_timeframe(
                config.timeframe
            ) and not _intraday_in_market_hours(t):
                continue
            try:
                o = float(r.get("open") or 0.0)
                h = float(r.get("high") or 0.0)
                lo = float(r.get("low") or 0.0)
                c = float(r.get("close") or 0.0)
                v = float(r.get("volume") or 0.0)
            except (TypeError, ValueError):
                continue
            if c <= 0 or o <= 0 or h <= 0 or lo <= 0:
                continue
            ts.append(t)
            opens.append(o)
            highs.append(h)
            lows.append(lo)
            closes.append(c)
            volumes.append(v)

        if not ts:
            missing_symbols.append(s.key)
            continue

        sim_start_dt = datetime.combine(config.start_date, time.min)
        sim_end_dt = datetime.combine(config.end_date, time.max)
        sim_start = None
        sim_end = None
        for i, t in enumerate(ts):
            if sim_start is None and t >= sim_start_dt:
                sim_start = i
            if t <= sim_end_dt:
                sim_end = i
        if sim_start is None or sim_end is None or sim_start > sim_end:
            missing_symbols.append(s.key)
            continue

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

        rank_series: list[Optional[float]] | None = None
        if config.allocation_mode == "RANKING":
            if config.ranking_metric != "PERF_PCT":
                raise ValueError("Only PERF_PCT ranking is supported in v1.")
            rank_series = _compute_perf_pct_series(
                closes, int(config.ranking_window or 1)
            )

        idx_by_ts = {t: i for i, t in enumerate(ts)}

        bars_by_key[s.key] = _SymbolBars(
            ref=s,
            ts=ts,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            sim_start=sim_start,
            sim_end=sim_end,
            series=series,
            rank_series=rank_series,
            idx_by_ts=idx_by_ts,
        )

    if not bars_by_key:
        raise ValueError("No candles available for requested symbols.")

    # Global evaluation calendar from union of all timestamps within window.
    all_ts: set[datetime] = set()
    for b in bars_by_key.values():
        for t in b.ts[b.sim_start : b.sim_end + 1]:
            all_ts.add(t)
    gts = sorted(all_ts)
    if not gts:
        raise ValueError("No candles in the selected window.")
    if len(gts) > MAX_GLOBAL_BARS:
        raise ValueError(
            f"Too many bars in window ({len(gts)}). "
            "Narrow the date range or use a higher timeframe."
        )
    if len(bars_by_key) > MAX_SYMBOLS_LOADED:
        raise ValueError(
            f"Too many symbols loaded ({len(bars_by_key)}). Reduce group size or split "
            "into smaller groups."
        )
    if len(gts) * len(bars_by_key) > MAX_CELL_UPDATES:
        raise ValueError(
            f"Backtest too large (symbols={len(bars_by_key)}, bars={len(gts)}). "
            "Narrow the date range, use a higher timeframe, or reduce group size."
        )

    slip = float(config.slippage_bps) / 10000.0
    charges_rate = (
        float(config.charges_bps) / 10000.0 if config.charges_model == "BPS" else None
    )

    def est_charges(*, symbol: UniverseSymbolRef, side: str, notional: float) -> float:
        if charges_rate is not None:
            return float(notional) * float(charges_rate)
        ex = symbol.exchange.upper()
        return float(
            estimate_india_equity_charges(
                broker=str(config.charges_broker).lower() or "zerodha",
                product=str(config.product).upper(),
                side=side,
                exchange="BSE" if ex == "BSE" else "NSE",
                turnover=float(notional),
                stamp_state="WEST_BENGAL",
                include_dp=bool(config.include_dp_charges),
            ).total
        )

    cash = float(config.initial_cash)
    trading_disabled = False

    positions: dict[str, _PositionState] = {
        k: _PositionState() for k in bars_by_key.keys()
    }
    pending_entry_ts: dict[str, datetime] = {}
    pending_exit_ts: dict[str, tuple[datetime, str]] = {}  # exec_ts, reason

    last_close: dict[str, float] = {}
    last_ts_seen: dict[str, datetime] = {}
    realized_pnl: dict[str, float] = {k: 0.0 for k in bars_by_key.keys()}

    equity: list[float] = []
    drawdown_pct: list[float] = []
    peak_equity = -math.inf
    total_charges = 0.0
    total_turnover = 0.0

    trades: list[dict[str, Any]] = []
    trade_pnl_pct: list[float] = []

    per_symbol_pnl: dict[str, list[float]] = {k: [] for k in bars_by_key.keys()}
    markers: list[dict[str, Any]] = []

    def open_positions_count() -> int:
        return sum(1 for st in positions.values() if st.qty != 0)

    def equity_now_for_close() -> float:
        v = float(cash)
        for key, st in positions.items():
            if st.qty == 0:
                continue
            px = last_close.get(key)
            if px is None:
                continue
            v += float(st.qty) * float(px)
        return float(v)

    def update_symbol_pnl_series() -> None:
        for key, st in positions.items():
            pnl = float(realized_pnl.get(key, 0.0))
            if st.qty != 0 and st.entry_fill is not None:
                px = last_close.get(key)
                if px is not None:
                    # Long: qty*(px-entry). Short: qty is negative => works.
                    pnl += float(st.qty) * (float(px) - float(st.entry_fill))
            per_symbol_pnl[key].append(float(pnl))

    for gi, t in enumerate(gts):
        # 1) Execute exits at this bar open (symbol-specific).
        for key, (exec_ts, reason) in list(pending_exit_ts.items()):
            if exec_ts != t:
                continue
            st = positions[key]
            if st.qty == 0:
                del pending_exit_ts[key]
                continue
            b = bars_by_key[key]
            si = b.idx_by_ts.get(t)
            if si is None:
                continue
            side = "SELL" if st.qty > 0 else "BUY"
            fill_px = float(b.opens[si]) * (1.0 + slip if side == "BUY" else 1.0 - slip)
            qty_int = abs(int(st.qty))
            notional = qty_int * float(b.opens[si])
            ch = est_charges(symbol=b.ref, side=side, notional=notional)
            total_charges += ch
            total_turnover += notional

            if side == "SELL":
                cash += qty_int * fill_px - ch
            else:
                cash -= qty_int * fill_px + ch

            if st.entry_fill is not None and st.entry_ts is not None:
                exit_reason = reason
                if reason == "TRAILING_STOP":
                    # Trailing stop is profit-protecting: never attribute a losing
                    # exit to trailing (gaps/slippage can still produce a loss).
                    if st.qty > 0 and fill_px < float(st.entry_fill):
                        exit_reason = "STOP_LOSS"
                    if st.qty < 0 and fill_px > float(st.entry_fill):
                        exit_reason = "STOP_LOSS"
                ret_pct = (
                    (fill_px / st.entry_fill - 1.0) * 100.0
                    if st.qty > 0
                    else (st.entry_fill / fill_px - 1.0) * 100.0
                )
                trade_pnl_pct.append(float(ret_pct))
                realized = float(st.qty) * (float(fill_px) - float(st.entry_fill))
                realized_pnl[key] = float(realized_pnl.get(key, 0.0) + realized)
                trades.append(
                    {
                        "symbol": key,
                        "entry_ts": _iso_ist(st.entry_ts),
                        "exit_ts": _iso_ist(t),
                        "side": "LONG" if st.qty > 0 else "SHORT",
                        "entry_price": float(st.entry_fill),
                        "exit_price": float(fill_px),
                        "qty": int(qty_int),
                        "pnl_pct": float(ret_pct),
                        "reason": exit_reason,
                    }
                )
                markers.append(
                    {
                        "ts": _iso_ist(st.entry_ts),
                        "kind": "CROSSOVER",
                        "text": f"E {b.ref.symbol}",
                    }
                )
                markers.append(
                    {
                        "ts": _iso_ist(t),
                        "kind": "CROSSUNDER",
                        "text": f"X {b.ref.symbol}",
                    }
                )

            st.qty = 0
            st.entry_fill = None
            st.entry_ts = None
            st.entry_gi = None
            st.peak_since_entry = None
            st.trough_since_entry = None
            st.initial_sl_price = None
            st.tp_price = None
            st.trail_price = None
            st.trailing_active = False
            st.peak_equity_since_entry = None
            st.last_exit_gi = gi
            del pending_exit_ts[key]

        # 2) Execute entries at this bar open.
        if pending_entry_ts:
            decision_equity = equity[gi - 1] if gi - 1 >= 0 and equity else float(cash)
            slots_remaining = max(
                0, int(config.max_open_positions) - open_positions_count()
            )
            budget_per_slot = None
            if config.sizing_mode == "CASH_PER_SLOT":
                budget_per_slot = float(cash) / float(max(1, slots_remaining))

            # Deterministic fill order.
            for key in sorted(list(pending_entry_ts.keys())):
                if pending_entry_ts.get(key) != t:
                    continue
                if open_positions_count() >= int(config.max_open_positions):
                    del pending_entry_ts[key]
                    continue
                st = positions[key]
                if st.qty != 0:
                    del pending_entry_ts[key]
                    continue
                b = bars_by_key[key]
                si = b.idx_by_ts.get(t)
                if si is None:
                    continue
                side = "BUY" if config.direction == "LONG" else "SELL"
                fill_px = float(b.opens[si]) * (
                    1.0 + slip if side == "BUY" else 1.0 - slip
                )

                if config.sizing_mode == "PCT_EQUITY":
                    deploy = float(decision_equity) * (
                        float(config.position_size_pct) / 100.0
                    )
                elif config.sizing_mode == "FIXED_CASH":
                    deploy = float(config.fixed_cash_per_trade or 0.0)
                else:
                    deploy = float(budget_per_slot or 0.0)

                if (
                    float(config.max_symbol_alloc_pct or 0.0) > 0
                    and decision_equity > 0
                ):
                    deploy = min(
                        float(deploy),
                        float(decision_equity)
                        * (float(config.max_symbol_alloc_pct) / 100.0),
                    )

                if side == "BUY":
                    deploy = min(float(deploy), float(cash))

                qty_int = (
                    int(math.floor(float(deploy) / float(fill_px)))
                    if fill_px > 0
                    else 0
                )
                if qty_int <= 0:
                    del pending_entry_ts[key]
                    continue
                notional = qty_int * float(b.opens[si])
                ch = est_charges(symbol=b.ref, side=side, notional=notional)
                total_charges += ch
                total_turnover += notional

                if side == "BUY":
                    if cash >= qty_int * fill_px + ch:
                        cash -= qty_int * fill_px + ch
                        st.qty = qty_int
                    else:
                        del pending_entry_ts[key]
                        continue
                else:
                    cash += qty_int * fill_px - ch
                    st.qty = -qty_int

                st.entry_fill = float(fill_px)
                st.entry_ts = t
                st.entry_gi = gi
                st.peak_since_entry = float(st.entry_fill)
                st.trough_since_entry = float(st.entry_fill)
                stop_pct = float(config.stop_loss_pct or 0.0)
                tp_pct = float(config.take_profit_pct or 0.0)
                trail_pct = float(config.trailing_stop_pct or 0.0)
                if st.qty > 0:
                    st.initial_sl_price = (
                        float(st.entry_fill) * (1.0 - stop_pct / 100.0)
                        if stop_pct > 0
                        else None
                    )
                    st.tp_price = (
                        float(st.entry_fill) * (1.0 + tp_pct / 100.0)
                        if tp_pct > 0
                        else None
                    )
                else:
                    st.initial_sl_price = (
                        float(st.entry_fill) * (1.0 + stop_pct / 100.0)
                        if stop_pct > 0
                        else None
                    )
                    st.tp_price = (
                        float(st.entry_fill) * (1.0 - tp_pct / 100.0)
                        if tp_pct > 0
                        else None
                    )
                st.trailing_active = False
                st.trail_price = float(st.entry_fill) if trail_pct > 0 else None
                st.peak_equity_since_entry = float(decision_equity)
                del pending_entry_ts[key]

        # 3) Update last seen prices for mark-to-market.
        for key, b in bars_by_key.items():
            si = b.idx_by_ts.get(t)
            if si is None:
                continue
            last_close[key] = float(b.closes[si])
            last_ts_seen[key] = t

        # 4) Risk controls evaluated at close; schedule exit next open.
        for key, st in positions.items():
            if st.qty == 0 or st.entry_fill is None:
                continue
            b = bars_by_key[key]
            si = b.idx_by_ts.get(t)
            if si is None:
                continue
            # Min holding period.
            if int(config.min_holding_bars or 0) > 0 and st.entry_gi is not None:
                if gi - int(st.entry_gi) < int(config.min_holding_bars):
                    continue
            close_px = float(b.closes[si])

            next_i = si + 1
            if next_i > b.sim_end:
                continue
            next_ts = b.ts[next_i]
            if key in pending_exit_ts:
                continue

            if st.qty > 0:
                st.peak_since_entry = max(
                    float(st.peak_since_entry or float(st.entry_fill)),
                    close_px,
                )
                trail_pct = float(config.trailing_stop_pct or 0.0)
                if trail_pct > 0 and st.peak_since_entry is not None:
                    activate_when = float(st.entry_fill) * (1.0 + trail_pct / 100.0)
                    if float(st.peak_since_entry) >= activate_when:
                        st.trailing_active = True
                    if st.trailing_active:
                        candidate = float(st.peak_since_entry) * (
                            1.0 - trail_pct / 100.0
                        )
                        prev = float(
                            st.trail_price
                            if st.trail_price is not None
                            else st.entry_fill
                        )
                        st.trail_price = max(prev, candidate, float(st.entry_fill))

                effective_stop = st.initial_sl_price
                if st.trailing_active and st.trail_price is not None:
                    effective_stop = (
                        float(st.trail_price)
                        if effective_stop is None
                        else max(float(effective_stop), float(st.trail_price))
                    )

                if st.tp_price is not None and close_px >= float(st.tp_price):
                    pending_exit_ts[key] = (next_ts, "TAKE_PROFIT")
                elif effective_stop is not None and close_px <= float(effective_stop):
                    if (not st.trailing_active) or (
                        st.initial_sl_price is not None
                        and close_px <= float(st.initial_sl_price)
                    ):
                        pending_exit_ts[key] = (next_ts, "STOP_LOSS")
                    else:
                        pending_exit_ts[key] = (next_ts, "TRAILING_STOP")
            else:
                st.trough_since_entry = min(
                    float(st.trough_since_entry or float(st.entry_fill)),
                    close_px,
                )
                trail_pct = float(config.trailing_stop_pct or 0.0)
                if trail_pct > 0 and st.trough_since_entry is not None:
                    activate_when = float(st.entry_fill) * (1.0 - trail_pct / 100.0)
                    if float(st.trough_since_entry) <= activate_when:
                        st.trailing_active = True
                    if st.trailing_active:
                        candidate = float(st.trough_since_entry) * (
                            1.0 + trail_pct / 100.0
                        )
                        prev = float(
                            st.trail_price
                            if st.trail_price is not None
                            else st.entry_fill
                        )
                        st.trail_price = min(prev, candidate, float(st.entry_fill))

                effective_stop = st.initial_sl_price
                if st.trailing_active and st.trail_price is not None:
                    effective_stop = (
                        float(st.trail_price)
                        if effective_stop is None
                        else min(float(effective_stop), float(st.trail_price))
                    )

                if st.tp_price is not None and close_px <= float(st.tp_price):
                    pending_exit_ts[key] = (next_ts, "TAKE_PROFIT")
                elif effective_stop is not None and close_px >= float(effective_stop):
                    if (not st.trailing_active) or (
                        st.initial_sl_price is not None
                        and close_px >= float(st.initial_sl_price)
                    ):
                        pending_exit_ts[key] = (next_ts, "STOP_LOSS")
                    else:
                        pending_exit_ts[key] = (next_ts, "TRAILING_STOP")

        # 5) Signal evaluation at close; schedule entries/exits for next open.
        if not trading_disabled:
            candidates: list[str] = []
            scored: list[tuple[str, float]] = []

            for key, b in bars_by_key.items():
                si = b.idx_by_ts.get(t)
                if si is None:
                    continue
                st = positions[key]
                if st.qty == 0:
                    # cooldown
                    if (
                        int(config.cooldown_bars or 0) > 0
                        and st.last_exit_gi is not None
                    ):
                        if gi - int(st.last_exit_gi) <= int(config.cooldown_bars):
                            continue
                    if key not in pending_entry_ts and open_positions_count() + len(
                        pending_entry_ts
                    ) < int(config.max_open_positions):
                        if si < b.sim_end and _eval_expr_at(entry_expr, b.series, si):
                            if (
                                config.allocation_mode == "RANKING"
                                and b.rank_series is not None
                            ):
                                score = b.rank_series[si]
                                if score is not None:
                                    scored.append((key, float(score)))
                                else:
                                    candidates.append(key)
                            else:
                                candidates.append(key)
                else:
                    if (
                        key not in pending_exit_ts
                        and si < b.sim_end
                        and _eval_expr_at(exit_expr, b.series, si)
                    ):
                        if (
                            int(config.min_holding_bars or 0) > 0
                            and st.entry_gi is not None
                        ):
                            if gi - int(st.entry_gi) < int(config.min_holding_bars):
                                continue
                        next_ts = b.ts[si + 1]
                        pending_exit_ts[key] = (next_ts, "EXIT_SIGNAL")

            # Select entries up to remaining slots.
            slots = max(
                0,
                int(config.max_open_positions)
                - open_positions_count()
                - len(pending_entry_ts),
            )
            picks: list[str] = []
            if slots > 0:
                if config.allocation_mode == "RANKING" and scored:
                    scored_sorted = sorted(scored, key=lambda x: x[1], reverse=True)
                    picks = [k for k, _ in scored_sorted[:slots]]
                    if len(picks) < slots:
                        # fallback deterministic
                        for k in sorted(candidates):
                            if k not in picks:
                                picks.append(k)
                            if len(picks) >= slots:
                                break
                else:
                    picks = sorted(candidates)[:slots]

            for key in picks:
                b = bars_by_key[key]
                si = b.idx_by_ts.get(t)
                if si is None or si + 1 > b.sim_end:
                    continue
                pending_entry_ts[key] = b.ts[si + 1]

        # 6) MIS square-off at last bar of day (close at close price).
        if config.product == "MIS":
            # detect end of day by date change in global timeline
            next_date = gts[gi + 1].date() if gi + 1 < len(gts) else None
            if next_date is None or next_date != t.date():
                for key, st in positions.items():
                    if st.qty == 0 or st.entry_fill is None:
                        continue
                    b = bars_by_key[key]
                    si = b.idx_by_ts.get(t)
                    if si is None:
                        continue
                    fill_px = float(b.closes[si])
                    side = "SELL" if st.qty > 0 else "BUY"
                    qty_int = abs(int(st.qty))
                    notional = qty_int * float(b.closes[si])
                    ch = est_charges(symbol=b.ref, side=side, notional=notional)
                    total_charges += ch
                    total_turnover += notional
                    if side == "SELL":
                        cash += qty_int * fill_px - ch
                    else:
                        cash -= qty_int * fill_px + ch

                    ret_pct = (
                        (fill_px / st.entry_fill - 1.0) * 100.0
                        if st.qty > 0
                        else (st.entry_fill / fill_px - 1.0) * 100.0
                    )
                    trade_pnl_pct.append(float(ret_pct))
                    realized = float(st.qty) * (float(fill_px) - float(st.entry_fill))
                    realized_pnl[key] = float(realized_pnl.get(key, 0.0) + realized)
                    trades.append(
                        {
                            "symbol": key,
                            "entry_ts": _iso_ist(st.entry_ts or t),
                            "exit_ts": _iso_ist(t),
                            "side": "LONG" if st.qty > 0 else "SHORT",
                            "entry_price": float(st.entry_fill),
                            "exit_price": float(fill_px),
                            "qty": int(qty_int),
                            "pnl_pct": float(ret_pct),
                            "reason": "EOD_SQUARE_OFF",
                        }
                    )
                    markers.append(
                        {
                            "ts": _iso_ist(st.entry_ts or t),
                            "kind": "CROSSOVER",
                            "text": f"E {b.ref.symbol}",
                        }
                    )
                    markers.append(
                        {
                            "ts": _iso_ist(t),
                            "kind": "CROSSUNDER",
                            "text": f"X {b.ref.symbol}",
                        }
                    )
                    st.qty = 0
                    st.entry_fill = None
                    st.entry_ts = None
                    st.entry_gi = None
                    st.last_exit_gi = gi
                    st.peak_since_entry = None
                    st.trough_since_entry = None
                    st.peak_equity_since_entry = None
                    pending_entry_ts.pop(key, None)
                    pending_exit_ts.pop(key, None)

        # 7) Combined equity + drawdown at this bar close.
        v = equity_now_for_close()
        equity.append(float(v))
        peak_equity = max(float(peak_equity), float(v))
        dd = (float(v) / float(peak_equity) - 1.0) * 100.0 if peak_equity > 0 else 0.0
        drawdown_pct.append(float(dd))

        # Per-symbol P&L series (contribution).
        update_symbol_pnl_series()

        # 8) Equity drawdown controls at close (global and per-trade).
        if float(config.max_equity_dd_global_pct or 0.0) > 0 and dd <= -float(
            config.max_equity_dd_global_pct
        ):
            trading_disabled = True
            pending_entry_ts.clear()
            for key, st in positions.items():
                if st.qty == 0:
                    continue
                b = bars_by_key[key]
                si = b.idx_by_ts.get(t)
                if si is None or si + 1 > b.sim_end:
                    continue
                pending_exit_ts[key] = (b.ts[si + 1], "EQUITY_DD_GLOBAL")

        max_dd_trade = float(config.max_equity_dd_trade_pct or 0.0)
        if max_dd_trade > 0:
            for key, st in positions.items():
                if st.qty == 0 or st.peak_equity_since_entry is None:
                    continue
                st.peak_equity_since_entry = max(
                    float(st.peak_equity_since_entry), float(v)
                )
                dd_trade_pct = (
                    (float(v) / float(st.peak_equity_since_entry) - 1.0) * 100.0
                    if st.peak_equity_since_entry > 0
                    else 0.0
                )
                if dd_trade_pct <= -max_dd_trade:
                    b = bars_by_key[key]
                    si = b.idx_by_ts.get(t)
                    if si is None or si + 1 > b.sim_end:
                        continue
                    pending_exit_ts[key] = (b.ts[si + 1], "EQUITY_DD_TRADE")

    if not equity:
        raise ValueError("No equity series produced.")

    start_val = float(equity[0])
    end_val = float(equity[-1])
    total_return_pct = (end_val / start_val - 1.0) * 100.0 if start_val > 0 else 0.0

    duration_days = max(1, (gts[-1] - gts[0]).days + 1)
    years = duration_days / 365.25
    cagr_pct = (
        ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0
        if years > 0 and start_val > 0
        else 0.0
    )
    max_drawdown_pct = abs(min(drawdown_pct)) if drawdown_pct else 0.0
    avg_equity = sum(equity) / len(equity) if equity else 0.0
    turnover_pct_total = (
        (total_turnover / avg_equity * 100.0) if avg_equity > 0 else 0.0
    )

    win_rate_pct = (
        (sum(1 for x in trade_pnl_pct if x > 0) / len(trade_pnl_pct) * 100.0)
        if trade_pnl_pct
        else 0.0
    )

    per_symbol_stats: list[dict[str, Any]] = []
    by_symbol_trades: dict[str, list[dict[str, Any]]] = {}
    for tr in trades:
        by_symbol_trades.setdefault(str(tr.get("symbol") or ""), []).append(tr)
    for key in sorted(bars_by_key.keys()):
        trs = by_symbol_trades.get(key, [])
        pnls = [
            float(t.get("pnl_pct") or 0.0) for t in trs if t.get("pnl_pct") is not None
        ]
        per_symbol_stats.append(
            {
                "symbol": key,
                "trades": len(trs),
                "win_rate_pct": (
                    float(sum(1 for p in pnls if p > 0) / len(pnls) * 100.0)
                    if pnls
                    else 0.0
                ),
                "avg_pnl_pct": float(sum(pnls) / len(pnls)) if pnls else 0.0,
                "realized_pnl": float(realized_pnl.get(key, 0.0)),
            }
        )

    ts_iso = [_iso_ist(x) for x in gts]
    if len(ts_iso) > MAX_RETURN_POINTS:
        step = int(math.ceil(len(ts_iso) / MAX_RETURN_POINTS))
        keep: set[int] = set(range(0, len(ts_iso), step))
        keep.add(len(ts_iso) - 1)
        marker_ts = {
            str(m.get("ts"))
            for m in markers
            if isinstance(m, dict) and m.get("ts") is not None
        }
        keep.update(i for i, t in enumerate(ts_iso) if t in marker_ts)
        idxs = sorted(keep)

        ts_iso = [ts_iso[i] for i in idxs]
        equity = [equity[i] for i in idxs]
        drawdown_pct = [drawdown_pct[i] for i in idxs]
        per_symbol_pnl = {
            k: [vals[i] for i in idxs] for k, vals in per_symbol_pnl.items()
        }

    return {
        "meta": {
            "timeframe": config.timeframe,
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
            "entry_dsl": config.entry_dsl,
            "exit_dsl": config.exit_dsl,
            "product": config.product,
            "direction": config.direction,
            "initial_cash": float(config.initial_cash),
            "max_open_positions": int(config.max_open_positions),
            "allocation_mode": config.allocation_mode,
            "ranking_metric": config.ranking_metric,
            "ranking_window": int(config.ranking_window),
            "sizing_mode": config.sizing_mode,
            "position_size_pct": float(config.position_size_pct),
            "fixed_cash_per_trade": float(config.fixed_cash_per_trade),
            "min_holding_bars": int(config.min_holding_bars),
            "cooldown_bars": int(config.cooldown_bars),
            "max_symbol_alloc_pct": float(config.max_symbol_alloc_pct),
            "stop_loss_pct": float(config.stop_loss_pct),
            "take_profit_pct": float(config.take_profit_pct),
            "trailing_stop_pct": float(config.trailing_stop_pct),
            "max_equity_dd_global_pct": float(config.max_equity_dd_global_pct),
            "max_equity_dd_trade_pct": float(config.max_equity_dd_trade_pct),
            "slippage_bps": float(config.slippage_bps),
            "charges_model": config.charges_model,
            "charges_bps": float(config.charges_bps),
            "charges_broker": config.charges_broker,
            "include_dp_charges": bool(config.include_dp_charges),
            "symbols_requested": len(unique),
            "symbols_loaded": len(bars_by_key),
            "symbols_missing": missing_symbols,
            "bars_total": len(gts),
            "bars_returned": len(ts_iso),
        },
        "series": {
            "ts": ts_iso,
            "equity": equity,
            "drawdown_pct": drawdown_pct,
        },
        "metrics": {
            "total_return_pct": float(total_return_pct),
            "cagr_pct": float(cagr_pct),
            "max_drawdown_pct": float(max_drawdown_pct),
            "turnover_pct_total": float(turnover_pct_total),
            "total_turnover": float(total_turnover),
            "total_charges": float(total_charges),
            "trades": len(trade_pnl_pct),
            "win_rate_pct": float(win_rate_pct),
        },
        "trades": trades,
        "markers": markers,
        "per_symbol_stats": per_symbol_stats,
        "per_symbol_pnl": per_symbol_pnl,
    }


__all__ = ["run_portfolio_strategy_backtest"]
