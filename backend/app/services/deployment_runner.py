from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.market_hours import IST_OFFSET
from app.models import (
    GroupMember,
    Order,
    StrategyDeployment,
    StrategyDeploymentAction,
    StrategyDeploymentState,
)
from app.services.alert_expression_dsl import parse_expression
from app.services.backtests_strategy import (
    _eval_expr_at,
    _IndicatorKey,
    _iter_indicator_operands,
    _resolve_indicator_series,
    _series_key,
)
from app.services.market_data import load_series


def _json_load(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except Exception:
        return {}
    return val if isinstance(val, dict) else {}


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_to_ist_naive(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=UTC)
    return (dt_utc.astimezone(UTC) + IST_OFFSET).replace(tzinfo=None)


def _ist_naive_to_utc(dt_ist: datetime) -> datetime:
    return (dt_ist - IST_OFFSET).replace(tzinfo=UTC)


def _tf_minutes(tf: str) -> int | None:
    return {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}.get(tf)


def _sym_key(exchange: str, symbol: str) -> str:
    return f"{exchange.upper()}:{symbol.upper()}"


def _compute_perf_pct(closes: list[float], window: int) -> list[Optional[float]]:
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


def _indicator_lookback_max(exprs: list) -> int:
    needed: set[_IndicatorKey] = set()
    for expr in exprs:
        for op in _iter_indicator_operands(expr):
            needed.add(_series_key(op))
    periods = [int(k.period or 0) for k in needed if int(k.period or 0) > 0]
    return max(periods) if periods else 0


def _load_intraday_series(
    db: Session,
    settings: Settings,
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    bar_end_ist: datetime,
    lookback_bars: int,
    allow_fetch: bool,
) -> tuple[
    list[datetime], list[float], list[float], list[float], list[float], list[float]
]:
    minutes = _tf_minutes(timeframe)
    if minutes is None:
        raise ValueError(f"Unsupported intraday timeframe: {timeframe}")
    delta = timedelta(minutes=minutes)
    bar_start = bar_end_ist - delta
    start = bar_start - delta * max(lookback_bars, 10)
    end = bar_start

    rows = load_series(
        db,
        settings,
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,  # type: ignore[arg-type]
        start=start,
        end=end,
        allow_fetch=allow_fetch,
    )
    ts: list[datetime] = []
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    vols: list[float] = []
    for r in rows:
        t = r.get("ts")
        if not isinstance(t, datetime) or t > bar_start:
            continue
        o = float(r.get("open") or 0.0)
        h = float(r.get("high") or 0.0)
        lo = float(r.get("low") or 0.0)
        c = float(r.get("close") or 0.0)
        v = float(r.get("volume") or 0.0)
        if min(o, h, lo, c) <= 0:
            continue
        ts.append(t)
        opens.append(o)
        highs.append(h)
        lows.append(lo)
        closes.append(c)
        vols.append(v)
    return ts, opens, highs, lows, closes, vols


def _load_daily_proxy_series(
    db: Session,
    settings: Settings,
    *,
    exchange: str,
    symbol: str,
    base_timeframe: str,
    proxy_close_hhmm: str,
    bar_end_ist: datetime,
    lookback_days: int,
    allow_fetch: bool,
) -> tuple[
    list[datetime], list[float], list[float], list[float], list[float], list[float]
]:
    """Build synthetic daily candles up to current day proxy close (IST)."""

    minutes = _tf_minutes(base_timeframe)
    if minutes is None:
        raise ValueError(f"Unsupported base_timeframe: {base_timeframe}")
    delta = timedelta(minutes=minutes)
    hh, mm = proxy_close_hhmm.split(":")
    proxy_t = time(hour=int(hh), minute=int(mm))

    end_day = bar_end_ist.date()
    start_day = (bar_end_ist - timedelta(days=int(lookback_days))).date()
    start = datetime.combine(start_day, time(9, 15))
    end = datetime.combine(end_day, time(15, 30))

    rows = load_series(
        db,
        settings,
        symbol=symbol,
        exchange=exchange,
        timeframe=base_timeframe,  # type: ignore[arg-type]
        start=start,
        end=end,
        allow_fetch=allow_fetch,
    )
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        t = r.get("ts")
        if not isinstance(t, datetime):
            continue
        by_day.setdefault(t.date().isoformat(), []).append(r)

    dts: list[datetime] = []
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    vols: list[float] = []

    for day in sorted(by_day.keys()):
        bars = by_day[day]
        bars_sorted = sorted(bars, key=lambda x: x.get("ts"))
        # Proxy close bar ends at HH:MM; bar start is HH:MM - delta.
        day_dt = datetime.fromisoformat(day)
        proxy_end = datetime.combine(day_dt.date(), proxy_t)
        proxy_start = proxy_end - delta
        # Only include days up to the current evaluation day.
        if proxy_end > bar_end_ist:
            continue

        day_open = None
        day_high = None
        day_low = None
        day_close = None
        day_vol = 0.0

        for b in bars_sorted:
            t = b.get("ts")
            if not isinstance(t, datetime):
                continue
            if t.time() < time(9, 15) or t > proxy_start:
                continue
            o = float(b.get("open") or 0.0)
            h = float(b.get("high") or 0.0)
            lo = float(b.get("low") or 0.0)
            c = float(b.get("close") or 0.0)
            v = float(b.get("volume") or 0.0)
            if min(o, h, lo, c) <= 0:
                continue
            if day_open is None:
                day_open = o
            day_high = max(day_high or h, h)
            day_low = min(day_low or lo, lo)
            day_vol += v
            # close will be overwritten until proxy_start
            day_close = c

        # Use the proxy bar close as close for the day.
        proxy_bar = next(
            (b for b in bars_sorted if b.get("ts") == proxy_start),
            None,
        )
        if proxy_bar is not None:
            day_close = float(proxy_bar.get("close") or day_close or 0.0)
            day_high = max(day_high or 0.0, float(proxy_bar.get("high") or 0.0))
            day_low = (
                min(day_low or float("inf"), float(proxy_bar.get("low") or 0.0))
                if day_low is not None
                else float(proxy_bar.get("low") or 0.0)
            )
            day_vol += float(proxy_bar.get("volume") or 0.0)

        if (
            day_open is None
            or day_close is None
            or (day_high or 0) <= 0
            or (day_low or 0) <= 0
        ):
            continue

        dts.append(datetime.combine(day_dt.date(), time.min))
        opens.append(float(day_open))
        highs.append(float(day_high or day_open))
        lows.append(float(day_low or day_open))
        closes.append(float(day_close))
        vols.append(float(day_vol))

    return dts, opens, highs, lows, closes, vols


def _open_at(
    db: Session,
    settings: Settings,
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    bar_start_ist: datetime,
    allow_fetch: bool,
) -> float | None:
    minutes = _tf_minutes(timeframe)
    if minutes is None:
        return None
    end = bar_start_ist + timedelta(minutes=minutes * 2)
    rows = load_series(
        db,
        settings,
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,  # type: ignore[arg-type]
        start=bar_start_ist,
        end=end,
        allow_fetch=allow_fetch,
    )
    for r in rows:
        if r.get("ts") == bar_start_ist:
            try:
                return float(r.get("open") or 0.0) or None
            except (TypeError, ValueError):
                return None
    return None


@dataclass(frozen=True)
class RunnerResult:
    orders_created: list[int]
    state: dict[str, Any]
    summary: dict[str, Any]


def _get_or_create_state(dep: StrategyDeployment) -> StrategyDeploymentState:
    if dep.state is None:
        raise RuntimeError("Deployment is missing state row.")
    return dep.state


def _create_order(
    db: Session,
    *,
    dep: StrategyDeployment,
    action: StrategyDeploymentAction,
    client_order_id: str,
    exchange: str,
    symbol: str,
    side: str,
    qty: int,
    price: float,
    order_type: str,
    product: str,
    execution_target: str,
    simulated: bool,
) -> Order:
    order = Order(
        user_id=dep.owner_id,
        strategy_id=None,
        alert_id=None,
        portfolio_group_id=(dep.group_id if dep.target_kind == "GROUP" else None),
        deployment_id=dep.id,
        deployment_action_id=action.id,
        client_order_id=client_order_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        qty=float(qty),
        price=float(price),
        order_type=order_type,
        product=product,
        status="EXECUTED" if execution_target == "PAPER" else "WAITING",
        mode="AUTO",
        execution_target=execution_target,
        broker_name=str(dep.broker_name or "zerodha"),
        simulated=bool(simulated),
    )
    try:
        with db.begin_nested():
            db.add(order)
            db.flush()
    except IntegrityError:
        existing = (
            db.query(Order)
            .filter(Order.client_order_id == client_order_id)
            .one_or_none()
        )
        if existing is None:
            raise
        return existing
    return order


def _position_equity(qty: int, side: str, price: float) -> float:
    if qty <= 0:
        return 0.0
    if side == "SHORT":
        # Paper model: treat short as negative exposure.
        return -float(qty) * float(price)
    return float(qty) * float(price)


def process_deployment_job(
    db: Session,
    settings: Settings,
    *,
    dep: StrategyDeployment,
    job_kind: str,
    scheduled_for_utc: datetime | None,
    payload: dict[str, Any],
    action: StrategyDeploymentAction,
) -> RunnerResult:
    """Evaluate deployment state on one job and create paper orders (MVP)."""

    cfg_obj = _json_load(dep.config_json).get("config") or {}

    state_row = _get_or_create_state(dep)
    state = _json_load(state_row.state_json)
    state.setdefault("version", 1)
    state.setdefault(
        "cash",
        float(cfg_obj.get("initial_cash") or state.get("cash") or 0.0),
    )
    state.setdefault("positions", {})
    state.setdefault("cooldown_bars", {})
    state.setdefault("trading_disabled", False)
    state.setdefault(
        "peak_equity",
        float(state.get("peak_equity") or state.get("cash") or 0.0),
    )
    kind = str(dep.kind or cfg_obj.get("kind") or "STRATEGY").upper()

    entry_expr = parse_expression(str(cfg_obj.get("entry_dsl") or ""))
    exit_expr = parse_expression(str(cfg_obj.get("exit_dsl") or ""))
    max_period = _indicator_lookback_max([entry_expr, exit_expr])

    timeframe = str(cfg_obj.get("timeframe") or dep.timeframe or "1d")
    exec_target = str(
        cfg_obj.get("execution_target") or dep.execution_target or "PAPER"
    ).upper()
    product = str(cfg_obj.get("product") or dep.product or "CNC").upper()
    direction = str(cfg_obj.get("direction") or "LONG").upper()

    # Trailing mode (bar-close only MVP): use base_timeframe when daily-via-intraday.
    daily = cfg_obj.get("daily_via_intraday") or {}
    daily_enabled = bool(daily.get("enabled")) if timeframe == "1d" else False
    base_timeframe = str(daily.get("base_timeframe") or "5m")
    proxy_close_hhmm = str(daily.get("proxy_close_hhmm") or "15:25")

    allow_fetch = exec_target != "PAPER"
    scheduled_for_utc = scheduled_for_utc or _utc_now()
    bar_end_ist = _utc_to_ist_naive(scheduled_for_utc)

    orders: list[Order] = []
    events: list[dict[str, Any]] = []

    def _cancel_order(order_id: int) -> None:
        o = db.get(Order, int(order_id))
        if o is None:
            return
        if o.status in {"WAITING", "SENT", "OPEN"}:
            o.status = "CANCELLED"
            db.add(o)

    def position_map() -> dict[str, Any]:
        raw = state.get("positions")
        if isinstance(raw, dict):
            return raw
        raw = {}
        state["positions"] = raw
        return raw

    def open_positions() -> list[tuple[str, dict[str, Any]]]:
        out = []
        for k, v in position_map().items():
            if not isinstance(v, dict):
                continue
            if int(v.get("qty") or 0) > 0:
                out.append((k, v))
        return out

    def equity_at_prices(prices: dict[str, float]) -> float:
        cash = float(state.get("cash") or 0.0)
        eq = float(cash)
        for k, pos in open_positions():
            px = prices.get(k)
            if px is None:
                continue
            eq += _position_equity(
                int(pos.get("qty") or 0), str(pos.get("side") or "LONG"), px
            )
        return eq

    # Which time series to use for signal evaluation on this job:
    # - DAILY_PROXY_CLOSED: evaluate 1d signals on proxy-built candles.
    # - BAR_CLOSED for daily deployments: risk-only trailing updates on base timeframe.
    signal_timeframe = timeframe
    if timeframe == "1d" and daily_enabled and job_kind == "BAR_CLOSED":
        signal_timeframe = base_timeframe

    signal_step = (timeframe != "1d" and job_kind == "BAR_CLOSED") or (
        timeframe == "1d" and job_kind == "DAILY_PROXY_CLOSED"
    )

    def load_symbol_snapshot(exchange: str, symbol: str) -> dict[str, Any] | None:
        symk = _sym_key(exchange, symbol)
        lookback_bars = max(
            50, max_period * 3, int(cfg_obj.get("ranking_window") or 0) * 3
        )

        if (
            signal_timeframe == "1d"
            and daily_enabled
            and job_kind
            in {
                "DAILY_PROXY_CLOSED",
                "WINDOW",
            }
        ):
            ts, opens, highs, lows, closes, vols = _load_daily_proxy_series(
                db,
                settings,
                exchange=exchange,
                symbol=symbol,
                base_timeframe=base_timeframe,
                proxy_close_hhmm=proxy_close_hhmm,
                bar_end_ist=bar_end_ist,
                lookback_days=max(30, max(lookback_bars // 5, 5)),
                allow_fetch=allow_fetch,
            )
        else:
            ts, opens, highs, lows, closes, vols = _load_intraday_series(
                db,
                settings,
                exchange=exchange,
                symbol=symbol,
                timeframe=signal_timeframe,
                bar_end_ist=bar_end_ist,
                lookback_bars=lookback_bars,
                allow_fetch=allow_fetch,
            )

        if not ts:
            return None
        i = len(ts) - 1

        needed: set[_IndicatorKey] = set()
        for op in list(_iter_indicator_operands(entry_expr)) + list(
            _iter_indicator_operands(exit_expr)
        ):
            needed.add(_series_key(op))

        series: dict[_IndicatorKey, list[Optional[float]]] = {}
        for k in needed:
            series[k] = _resolve_indicator_series(
                k.kind,
                int(k.period or 0),
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=vols,
            )

        warmup = max(max_period, int(cfg_obj.get("ranking_window") or 0))
        warm_ok = True if warmup <= 0 else i >= (warmup - 1)

        entry_ok = _eval_expr_at(entry_expr, series, i) if warm_ok else False
        exit_ok = _eval_expr_at(exit_expr, series, i)

        rank_series = None
        if str(cfg_obj.get("allocation_mode") or "EQUAL").upper() == "RANKING":
            rank_series = _compute_perf_pct(
                closes, int(cfg_obj.get("ranking_window") or 5)
            )
        return {
            "key": symk,
            "exchange": exchange,
            "symbol": symbol,
            "i": i,
            "warmup_bars": int(warmup),
            "warm_ok": bool(warm_ok),
            "close": float(closes[i]),
            "entry_ok": bool(entry_ok),
            "exit_ok": bool(exit_ok),
            "rank": (
                float(rank_series[i])
                if isinstance(rank_series, list) and rank_series[i] is not None
                else None
            ),
        }

    # Build a snapshot for all symbols in this deployment.
    payload_all = _json_load(dep.config_json)
    universe = payload_all.get("universe") or {}
    symbols = universe.get("symbols") or []
    if dep.target_kind == "SYMBOL" and dep.symbol and not symbols:
        symbols = [{"exchange": dep.exchange or "NSE", "symbol": dep.symbol}]
    if dep.target_kind == "GROUP" and dep.group_id and not symbols:
        members: list[GroupMember] = (
            db.query(GroupMember)
            .filter(GroupMember.group_id == int(dep.group_id))
            .all()
        )
        symbols = [
            {
                "exchange": str(m.exchange or "NSE").upper(),
                "symbol": str(m.symbol).upper(),
            }
            for m in members
        ]

    snapshots: list[dict[str, Any]] = []
    for s in symbols:
        if not isinstance(s, dict):
            continue
        exchange = str(s.get("exchange") or "NSE").upper()
        symbol = str(s.get("symbol") or "").upper()
        if not symbol:
            continue
        snap = load_symbol_snapshot(exchange, symbol)
        if snap is not None:
            snapshots.append(snap)

    prices = {sn["key"]: float(sn["close"]) for sn in snapshots}
    equity_now = equity_at_prices(prices)
    open_before = len(open_positions())
    state["peak_equity"] = max(
        float(state.get("peak_equity") or equity_now), float(equity_now)
    )

    cooldowns = state.get("cooldown_bars")
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        state["cooldown_bars"] = cooldowns

    # Advance counters once per evaluation step (bar-close / proxy-close).
    if job_kind in {"BAR_CLOSED", "DAILY_PROXY_CLOSED"}:
        for _symk, pos in open_positions():
            pos["holding_bars"] = int(pos.get("holding_bars") or 0) + 1
        for k in list(cooldowns.keys()):
            cooldowns[k] = max(0, int(cooldowns.get(k) or 0) - 1)
            if cooldowns[k] <= 0:
                cooldowns.pop(k, None)

    def _close_position(
        symk: str, pos: dict[str, Any], *, reason: str, fill_price: float
    ) -> None:
        qty = int(pos.get("qty") or 0)
        if qty <= 0:
            return
        side = str(pos.get("side") or "LONG").upper()
        exit_side = "BUY" if side == "SHORT" else "SELL"
        idx = len(orders)
        client_id = (
            f"dep:{dep.id}:{job_kind}:{scheduled_for_utc.isoformat()}:"
            f"{symk}:{exit_side}:{idx}"
        )
        order = _create_order(
            db,
            dep=dep,
            action=action,
            client_order_id=client_id,
            exchange=symk.split(":", 1)[0],
            symbol=symk.split(":", 1)[1],
            side=exit_side,
            qty=qty,
            price=fill_price,
            order_type="MARKET",
            product=product,
            execution_target=exec_target,
            simulated=(exec_target == "PAPER"),
        )
        orders.append(order)

        cash = float(state.get("cash") or 0.0)
        if exit_side == "SELL":
            cash += float(fill_price) * qty
        else:
            cash -= float(fill_price) * qty
        state["cash"] = cash
        pos["qty"] = 0
        pos["exit_price"] = float(fill_price)
        pos["exit_ts"] = scheduled_for_utc.isoformat()
        pos["exit_reason"] = reason
        events.append(
            {"type": "EXIT", "symbol": symk, "reason": reason, "order_id": order.id}
        )

        ds_id = pos.get("disaster_stop_order_id")
        if ds_id is not None:
            _cancel_order(int(ds_id))
            pos["disaster_stop_order_id"] = None

        cd = int(cfg_obj.get("cooldown_bars") or 0)
        if cd > 0:
            cooldowns[symk] = cd

    def _open_position(symk: str, *, side: str, qty: int, fill_price: float) -> None:
        if qty <= 0:
            return
        entry_side = "SELL" if side == "SHORT" else "BUY"
        idx = len(orders)
        client_id = (
            f"dep:{dep.id}:{job_kind}:{scheduled_for_utc.isoformat()}:"
            f"{symk}:{entry_side}:{idx}"
        )
        order = _create_order(
            db,
            dep=dep,
            action=action,
            client_order_id=client_id,
            exchange=symk.split(":", 1)[0],
            symbol=symk.split(":", 1)[1],
            side=entry_side,
            qty=qty,
            price=fill_price,
            order_type="MARKET",
            product=product,
            execution_target=exec_target,
            simulated=(exec_target == "PAPER"),
        )
        orders.append(order)
        cash = float(state.get("cash") or 0.0)
        if entry_side == "BUY":
            cash -= float(fill_price) * qty
        else:
            cash += float(fill_price) * qty
        state["cash"] = cash
        pos = position_map().get(symk) or {}
        pos.update(
            {
                "qty": int(qty),
                "side": side,
                "entry_price": float(fill_price),
                "entry_ts": scheduled_for_utc.isoformat(),
                "peak": float(fill_price),
                "trough": float(fill_price),
                "holding_bars": 0,
                "disaster_stop_order_id": None,
            }
        )
        position_map()[symk] = pos
        events.append({"type": "ENTRY", "symbol": symk, "order_id": order.id})

        # Broker-disaster stop scaffolding (MVP):
        # create an internal stop order row that future broker executors can
        # wire to GTT/SL primitives. In PAPER mode this is purely an audit trail.
        sl_pct = float(cfg_obj.get("stop_loss_pct") or 0.0)
        if sl_pct > 0:
            stop_px = (
                float(fill_price) * (1.0 - sl_pct / 100.0)
                if side != "SHORT"
                else float(fill_price) * (1.0 + sl_pct / 100.0)
            )
            stop_side = "BUY" if side == "SHORT" else "SELL"
            client_id = (
                f"dep:{dep.id}:DISASTER_STOP:{scheduled_for_utc.isoformat()}:"
                f"{symk}:{stop_side}"
            )
            stop_order = Order(
                user_id=dep.owner_id,
                strategy_id=None,
                alert_id=None,
                portfolio_group_id=(
                    dep.group_id if dep.target_kind == "GROUP" else None
                ),
                deployment_id=dep.id,
                deployment_action_id=action.id,
                client_order_id=client_id,
                symbol=symk.split(":", 1)[1],
                exchange=symk.split(":", 1)[0],
                side=stop_side,
                qty=float(qty),
                price=float(stop_px),
                order_type="LIMIT",
                trigger_price=float(stop_px),
                product=product,
                status="WAITING",
                mode="AUTO",
                execution_target=exec_target,
                broker_name=str(dep.broker_name or "zerodha"),
                gtt=True,
                synthetic_gtt=True,
                trigger_operator="<=" if stop_side == "SELL" else ">=",
                simulated=(exec_target == "PAPER"),
            )
            try:
                with db.begin_nested():
                    db.add(stop_order)
                    db.flush()
            except IntegrityError:
                existing = (
                    db.query(Order)
                    .filter(Order.client_order_id == client_id)
                    .one_or_none()
                )
                if existing is not None:
                    stop_order = existing
                else:
                    raise
            pos["disaster_stop_order_id"] = int(stop_order.id)
            events.append(
                {
                    "type": "DISASTER_STOP",
                    "symbol": symk,
                    "order_id": stop_order.id,
                    "stop_price": float(stop_px),
                }
            )

    # 1) Forced exits: window-triggered flatten.
    if job_kind == "WINDOW" and str(payload.get("window") or "") in {
        "MIS_FLATTEN",
        "FORCE_FLATTEN",
    }:
        reason = str(payload.get("window") or "FORCE_FLATTEN")
        for symk, pos in open_positions():
            fill_px = prices.get(symk) or float(pos.get("entry_price") or 0.0)
            _close_position(symk, pos, reason=reason, fill_price=float(fill_px))

    # 2) Risk exits (SL/TP/trailing) evaluated at close for bar-close jobs.
    def _risk_exit_reason(pos: dict[str, Any], close_px: float) -> str | None:
        qty = int(pos.get("qty") or 0)
        if qty <= 0:
            return None
        side = str(pos.get("side") or "LONG").upper()
        entry = float(pos.get("entry_price") or 0.0)
        if entry <= 0:
            return None
        sl = float(cfg_obj.get("stop_loss_pct") or 0.0)
        tp = float(cfg_obj.get("take_profit_pct") or 0.0)
        trail = float(cfg_obj.get("trailing_stop_pct") or 0.0)
        peak = float(pos.get("peak") or close_px)
        trough = float(pos.get("trough") or close_px)

        if side == "SHORT":
            stop_px = entry * (1.0 + sl / 100.0) if sl > 0 else None
            tp_px = entry * (1.0 - tp / 100.0) if tp > 0 else None
            trail_px = trough * (1.0 + trail / 100.0) if trail > 0 else None
            if stop_px is not None and close_px >= stop_px:
                return "STOP_LOSS"
            if tp_px is not None and close_px <= tp_px:
                return "TAKE_PROFIT"
            if trail_px is not None and close_px >= trail_px:
                return "TRAILING_STOP"
            return None

        stop_px = entry * (1.0 - sl / 100.0) if sl > 0 else None
        tp_px = entry * (1.0 + tp / 100.0) if tp > 0 else None
        trail_px = peak * (1.0 - trail / 100.0) if trail > 0 else None
        if stop_px is not None and close_px <= stop_px:
            return "STOP_LOSS"
        if tp_px is not None and close_px >= tp_px:
            return "TAKE_PROFIT"
        if trail_px is not None and close_px <= trail_px:
            return "TRAILING_STOP"
        return None

    if job_kind in {"BAR_CLOSED", "DAILY_PROXY_CLOSED"}:
        for symk, pos in open_positions():
            px = prices.get(symk)
            if px is None:
                continue
            # update peak/trough
            pos["peak"] = max(float(pos.get("peak") or px), float(px))
            pos["trough"] = min(float(pos.get("trough") or px), float(px))
            reason = _risk_exit_reason(pos, float(px))
            if reason:
                fill_px = float(px)
                if job_kind == "BAR_CLOSED" and _tf_minutes(signal_timeframe):
                    nxt = _open_at(
                        db,
                        settings,
                        exchange=symk.split(":", 1)[0],
                        symbol=symk.split(":", 1)[1],
                        timeframe=signal_timeframe,
                        bar_start_ist=bar_end_ist,
                        allow_fetch=allow_fetch,
                    )
                    if nxt is not None and nxt > 0:
                        fill_px = float(nxt)
                _close_position(symk, pos, reason=reason, fill_price=float(fill_px))

    # 3) Exit signal (exit-first) for symbols with positions.
    if signal_step:
        for snap in snapshots:
            symk = snap["key"]
            pos = position_map().get(symk)
            if not isinstance(pos, dict) or int(pos.get("qty") or 0) <= 0:
                continue
            min_hold = int(cfg_obj.get("min_holding_bars") or 0)
            if min_hold > 0 and int(pos.get("holding_bars") or 0) < min_hold:
                continue
            if bool(snap.get("exit_ok")):
                fill_px = float(snap["close"])
                if job_kind == "BAR_CLOSED" and _tf_minutes(signal_timeframe):
                    nxt = _open_at(
                        db,
                        settings,
                        exchange=snap["exchange"],
                        symbol=snap["symbol"],
                        timeframe=signal_timeframe,
                        bar_start_ist=bar_end_ist,
                        allow_fetch=allow_fetch,
                    )
                    if nxt is not None and nxt > 0:
                        fill_px = float(nxt)
                _close_position(symk, pos, reason="EXIT_SIGNAL", fill_price=fill_px)

    # 3.5) Equity drawdown controls (paper MVP; evaluated at close).
    equity_now = equity_at_prices(prices)
    peak_equity = float(state.get("peak_equity") or equity_now)
    if equity_now > peak_equity:
        peak_equity = equity_now
        state["peak_equity"] = float(peak_equity)
    dd_pct = (equity_now / peak_equity - 1.0) * 100.0 if peak_equity > 0 else 0.0

    max_dd_global = float(cfg_obj.get("max_equity_dd_global_pct") or 0.0)
    if max_dd_global > 0 and dd_pct <= -max_dd_global:
        state["trading_disabled"] = True
        for symk, pos in open_positions():
            px = prices.get(symk)
            if px is None:
                continue
            _close_position(symk, pos, reason="EQUITY_DD_GLOBAL", fill_price=float(px))

    max_dd_trade = float(cfg_obj.get("max_equity_dd_trade_pct") or 0.0)
    if max_dd_trade > 0:
        for symk, pos in open_positions():
            peak_trade = float(pos.get("peak_equity_since_entry") or equity_now)
            peak_trade = max(peak_trade, equity_now)
            pos["peak_equity_since_entry"] = float(peak_trade)
            dd_trade = (
                (equity_now / peak_trade - 1.0) * 100.0 if peak_trade > 0 else 0.0
            )
            if dd_trade <= -max_dd_trade:
                px = prices.get(symk)
                if px is None:
                    continue
                _close_position(
                    symk, pos, reason="EQUITY_DD_TRADE", fill_price=float(px)
                )

    # 4) Entry signal (if warm and not disabled).
    if (
        not bool(state.get("trading_disabled"))
        and signal_step
        and not bool(state.get("exit_only"))
    ):
        max_open = (
            int(cfg_obj.get("max_open_positions") or 1) if kind != "STRATEGY" else 1
        )
        open_count = len(open_positions())
        slots = max(0, max_open - open_count)
        if slots > 0:
            candidates = [s for s in snapshots if bool(s.get("entry_ok"))]
            if (
                kind != "STRATEGY"
                and str(cfg_obj.get("allocation_mode") or "EQUAL").upper() == "RANKING"
            ):
                scored = [
                    (s, float(s["rank"]))
                    for s in candidates
                    if s.get("rank") is not None
                ]
                scored = sorted(scored, key=lambda x: x[1], reverse=True)
                picks = [s for (s, _score) in scored[:slots]]
            else:
                picks = candidates[:slots]

            for s in picks:
                symk = s["key"]
                if int(cooldowns.get(symk) or 0) > 0:
                    continue
                if (
                    symk in position_map()
                    and int(position_map()[symk].get("qty") or 0) > 0
                ):
                    continue
                fill_px = float(s["close"])
                if job_kind == "BAR_CLOSED" and _tf_minutes(signal_timeframe):
                    nxt = _open_at(
                        db,
                        settings,
                        exchange=s["exchange"],
                        symbol=s["symbol"],
                        timeframe=signal_timeframe,
                        bar_start_ist=bar_end_ist,
                        allow_fetch=allow_fetch,
                    )
                    if nxt is not None and nxt > 0:
                        fill_px = float(nxt)
                equity = equity_at_prices(prices) or float(state.get("cash") or 0.0)
                if kind == "STRATEGY":
                    alloc_pct = float(cfg_obj.get("position_size_pct") or 100.0) / 100.0
                    notional = float(equity) * alloc_pct
                else:
                    sizing_mode = str(
                        cfg_obj.get("sizing_mode") or "PCT_EQUITY"
                    ).upper()
                    if sizing_mode == "FIXED_CASH":
                        notional = float(cfg_obj.get("fixed_cash_per_trade") or 0.0)
                    elif sizing_mode == "CASH_PER_SLOT":
                        notional = float(state.get("cash") or 0.0) / max(1, slots)
                    else:
                        notional = (
                            float(equity)
                            * float(cfg_obj.get("position_size_pct") or 20.0)
                            / 100.0
                        )

                qty = int(math.floor(notional / max(fill_px, 0.01)))
                if qty <= 0:
                    continue
                side = "SHORT" if direction == "SHORT" else "LONG"
                _open_position(symk, side=side, qty=qty, fill_price=fill_px)

    # Persist state updates.
    state_row.state_json = _json_dump(state)
    db.add(state_row)

    open_after = len(open_positions())
    warm_ok_all = True
    if snapshots:
        warm_ok_all = all(bool(s.get("warm_ok")) for s in snapshots)

    exit_events = [e for e in events if isinstance(e, dict) and e.get("type") == "EXIT"]
    entry_events = [
        e for e in events if isinstance(e, dict) and e.get("type") == "ENTRY"
    ]

    runtime_state = "FLAT"
    if state_row.status == "PAUSED":
        runtime_state = "PAUSED"
    elif open_after > 0:
        runtime_state = "IN_POSITION"
    elif signal_step and not warm_ok_all:
        runtime_state = "WARMING_UP"

    last_decision = "NO_BAR" if not snapshots else "ENTRY_FALSE"
    last_decision_reason = "No market data available."
    if snapshots:
        last_decision_reason = "No action."
        if state_row.status == "PAUSED":
            last_decision = "PAUSED"
            last_decision_reason = "Deployment is paused."
        elif bool(state.get("trading_disabled")):
            last_decision = "BLOCKED_TRADING_DISABLED"
            last_decision_reason = "Trading disabled by equity drawdown guard."
        elif signal_step and not warm_ok_all:
            last_decision = "WARMING_UP"
            last_decision_reason = "Not enough candles to warm indicators."
        elif open_before > 0:
            last_decision = "EXIT_TRUE" if exit_events else "EXIT_FALSE"
            last_decision_reason = (
                "Exit triggered." if exit_events else "No exit triggered."
            )
        else:
            last_decision = "ENTRY_TRUE" if entry_events else "ENTRY_FALSE"
            last_decision_reason = (
                "Entry triggered." if entry_events else "No entry triggered."
            )

    summary = {
        "job_kind": str(job_kind),
        "scheduled_for_utc": scheduled_for_utc.isoformat(),
        "bar_end_ist": bar_end_ist.isoformat(),
        "timeframe": str(timeframe),
        "signal_timeframe": str(signal_timeframe),
        "execution_target": str(exec_target),
        "product": str(product),
        "direction": str(direction),
        "dsl": {
            "entry": str(cfg_obj.get("entry_dsl") or ""),
            "exit": str(cfg_obj.get("exit_dsl") or ""),
        },
        "daily_via_intraday": (
            {
                "enabled": bool(daily_enabled),
                "base_timeframe": str(base_timeframe),
                "proxy_close_hhmm": str(proxy_close_hhmm),
            }
            if timeframe == "1d"
            else None
        ),
        "equity": float(equity_now),
        "cash": float(state.get("cash") or 0.0),
        "open_positions": len(open_positions()),
        "heartbeat": {
            "runtime_state": runtime_state,
            "last_decision": last_decision,
            "last_decision_reason": last_decision_reason,
            "open_positions_before": int(open_before),
            "open_positions_after": int(open_after),
        },
        "events": events,
        "orders": [{"id": o.id, "client_order_id": o.client_order_id} for o in orders],
    }
    return RunnerResult(
        orders_created=[o.id for o in orders],
        state=state,
        summary=summary,
    )


__all__ = ["RunnerResult", "process_deployment_job"]
