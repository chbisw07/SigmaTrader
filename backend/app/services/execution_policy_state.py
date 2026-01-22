from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import floor
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import ExecutionPolicyState, Order
from app.schemas.risk_policy import RiskPolicy
from app.services.risk_policy_enforcement import is_group_enforced

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MINUTES = 5
DEFAULT_INFLIGHT_TTL_SECONDS = 120


@dataclass(frozen=True)
class ExecutionScopeKey:
    user_id: int
    strategy_ref: str
    symbol: str
    product: str


def _as_of_date_ist(now_utc: datetime) -> date:
    try:
        from zoneinfo import ZoneInfo

        return now_utc.astimezone(ZoneInfo("Asia/Kolkata")).date()
    except Exception:
        return now_utc.date()


def _day_bounds_ist(now_utc: datetime) -> tuple[datetime, datetime]:
    try:
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        d = now_utc.astimezone(ist).date()
        start_ist = datetime(d.year, d.month, d.day, tzinfo=ist)
        end_ist = start_ist + timedelta(days=1)
        return start_ist.astimezone(UTC), end_ist.astimezone(UTC)
    except Exception:
        start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)


def _split_symbol_exchange(symbol: str, exchange: str | None) -> tuple[str, str]:
    sym = (symbol or "").strip()
    exch = (exchange or "NSE").strip().upper() or "NSE"
    if ":" in sym:
        ex, ts = sym.split(":", 1)
        ex = (ex or "").strip().upper()
        ts = (ts or "").strip().upper()
        if ex:
            exch = ex
        sym = ts
    return sym.strip().upper(), exch


def _strategy_ref_for_order(order: Order) -> str:
    if getattr(order, "deployment_id", None):
        return f"deployment:{int(order.deployment_id)}"
    if getattr(order, "strategy_id", None):
        return f"strategy:{int(order.strategy_id)}"
    try:
        if order.alert is not None:
            raw = getattr(order.alert, "raw_payload", None)
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    name = str(parsed.get("strategy_name") or "").strip()
                    if name:
                        # Keep it short for DB indexes / uniqueness.
                        return f"tv:{name[:120]}"
    except Exception:
        pass
    if getattr(order, "alert_id", None):
        return f"alert:{int(order.alert_id)}"
    return "manual"


def scope_key_for_order(order: Order) -> ExecutionScopeKey:
    symbol, exchange = _split_symbol_exchange(order.symbol, order.exchange)
    symbol_key = f"{exchange}:{symbol}"
    product = (order.product or "MIS").strip().upper() or "MIS"
    return ExecutionScopeKey(
        user_id=int(order.user_id or 0),
        strategy_ref=_strategy_ref_for_order(order),
        symbol=symbol_key,
        product=product,
    )


def _parse_interval_minutes_from_alert_raw(alert_raw: str | None) -> int | None:
    if not alert_raw:
        return None
    try:
        parsed = json.loads(alert_raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    raw = parsed.get("interval")
    if raw is None:
        return None
    try:
        # TradingView webhooks commonly send minutes as a string.
        v = int(str(raw).strip())
    except Exception:
        return None
    return v if v > 0 else None


def _parse_timeframe_minutes(tf: str | None) -> int | None:
    if not tf:
        return None
    s = str(tf).strip().lower()
    if s.endswith("m"):
        try:
            v = int(s[:-1])
        except Exception:
            return None
        return v if v > 0 else None
    if s.endswith("h"):
        try:
            v = int(s[:-1])
        except Exception:
            return None
        return v * 60 if v > 0 else None
    if s.endswith("d"):
        try:
            v = int(s[:-1])
        except Exception:
            return None
        return v * 1440 if v > 0 else None
    return None


def resolve_interval_for_order(
    order: Order, state: ExecutionPolicyState | None
) -> tuple[int, str]:
    try:
        if order.alert is not None:
            v = _parse_interval_minutes_from_alert_raw(
                getattr(order.alert, "raw_payload", None)
            )
            if v:
                return int(v), "tv_payload"
            rule = getattr(order.alert, "rule", None)
            tf = getattr(rule, "timeframe", None) if rule is not None else None
            v2 = _parse_timeframe_minutes(tf)
            if v2:
                return int(v2), "alert_rule"
    except Exception:
        pass
    if state is not None and int(getattr(state, "interval_minutes", 0) or 0) > 0:
        src = str(getattr(state, "interval_source", "") or "").strip() or "persisted"
        return int(state.interval_minutes), src
    return DEFAULT_INTERVAL_MINUTES, "default_fallback"


def interval_minutes_for_order(order: Order, state: ExecutionPolicyState | None) -> int:
    minutes, _src = resolve_interval_for_order(order, state)
    return minutes


def _signed_position_qty(state: ExecutionPolicyState) -> float:
    qty = float(getattr(state, "open_qty", 0.0) or 0.0)
    if qty <= 0:
        return 0.0
    side = (getattr(state, "open_side", None) or "").strip().upper()
    if side == "BUY":
        return qty
    if side == "SELL":
        return -qty
    return 0.0


def classify_position_delta(
    state: ExecutionPolicyState, *, side: str, qty: float
) -> tuple[float, float, bool, bool]:
    """Return (prev_abs, new_abs, is_entry, is_exit_reduce) for the scope key.

    Entry: abs(new_position_qty) > abs(previous_position_qty)
    Exit (protective): abs(new_position_qty) < abs(previous_position_qty)
    """
    qty_f = float(qty or 0.0)
    side_u = (side or "").strip().upper()
    if qty_f <= 0 or side_u not in {"BUY", "SELL"}:
        prev = abs(_signed_position_qty(state))
        return prev, prev, False, False
    prev_signed = _signed_position_qty(state)
    delta = qty_f if side_u == "BUY" else -qty_f
    new_signed = prev_signed + delta
    prev_abs = abs(prev_signed)
    new_abs = abs(new_signed)
    return prev_abs, new_abs, bool(new_abs > prev_abs), bool(new_abs < prev_abs)


def _bar_index(
    now_utc: datetime, *, start_day_utc: datetime, interval_minutes: int
) -> int:
    interval_sec = max(int(interval_minutes) * 60, 60)
    dt = (now_utc - start_day_utc).total_seconds()
    if dt < 0:
        dt = 0
    return int(floor(dt / interval_sec))


def get_or_create_execution_state(
    db: Session,
    *,
    key: ExecutionScopeKey,
    now_utc: datetime,
    interval_minutes: int,
    interval_source: str | None = None,
    lock: bool = False,
) -> ExecutionPolicyState:
    query = db.query(ExecutionPolicyState).filter(
        ExecutionPolicyState.user_id == int(key.user_id),
        ExecutionPolicyState.strategy_ref == str(key.strategy_ref),
        ExecutionPolicyState.symbol == str(key.symbol),
        ExecutionPolicyState.product == str(key.product),
    )
    if lock:
        query = query.with_for_update()
    row = query.one_or_none()
    if row is not None:
        if int(row.interval_minutes or 0) <= 0:
            row.interval_minutes = int(interval_minutes)
            db.add(row)
        return row

    row = ExecutionPolicyState(
        user_id=int(key.user_id),
        strategy_ref=str(key.strategy_ref),
        symbol=str(key.symbol),
        product=str(key.product),
        interval_minutes=int(interval_minutes),
        interval_source=str(interval_source or "persisted"),
        default_interval_logged=False,
        trade_date=_as_of_date_ist(now_utc),
        trades_today=0,
        last_trade_time=None,
        last_trade_bar_index=None,
        consecutive_losses=0,
        last_loss_time=None,
        last_loss_bar_index=None,
        paused_until=None,
        paused_reason=None,
        inflight_order_id=None,
        inflight_started_at=None,
        inflight_expires_at=None,
        open_side=None,
        open_qty=0.0,
        open_avg_price=None,
        open_realized_pnl=0.0,
    )
    try:
        db.add(row)
        db.flush()
        return row
    except IntegrityError:
        # Another concurrent executor created the row first.
        db.rollback()
        query2 = db.query(ExecutionPolicyState).filter(
            ExecutionPolicyState.user_id == int(key.user_id),
            ExecutionPolicyState.strategy_ref == str(key.strategy_ref),
            ExecutionPolicyState.symbol == str(key.symbol),
            ExecutionPolicyState.product == str(key.product),
        )
        if lock:
            query2 = query2.with_for_update()
        row2 = query2.one()
        return row2


def reset_daily_counters_if_new_day(
    state: ExecutionPolicyState, *, now_utc: datetime
) -> None:
    today = _as_of_date_ist(now_utc)
    if state.trade_date != today:
        state.trade_date = today
        state.trades_today = 0
        state.last_trade_bar_index = None
        state.last_trade_time = None
        # EOD pause expires at the next trading day start.
        state.paused_until = None
        state.paused_reason = None
        # Reset streak on EOD to avoid immediate re-pause the next day.
        state.consecutive_losses = 0
        state.last_loss_time = None
        state.last_loss_bar_index = None
        state.inflight_order_id = None
        state.inflight_started_at = None
        state.inflight_expires_at = None


def is_paused(state: ExecutionPolicyState, *, now_utc: datetime) -> bool:
    if state.paused_until is None:
        return False
    try:
        return now_utc < state.paused_until
    except Exception:
        return False


def apply_pre_trade_checks(
    policy: RiskPolicy,
    state: ExecutionPolicyState,
    *,
    now_utc: datetime,
) -> tuple[bool, str | None, str | None]:
    tf_on = is_group_enforced(policy, "trade_frequency")
    lc_on = is_group_enforced(policy, "loss_controls")
    if not (tf_on or lc_on):
        return True, None, None

    reset_daily_counters_if_new_day(state, now_utc=now_utc)

    if lc_on and is_paused(state, now_utc=now_utc):
        reason = state.paused_reason or "Paused by loss controls."
        return False, "RISK_POLICY_PAUSED", f"loss_controls: {reason}"

    tf = policy.trade_frequency
    lc = policy.loss_controls
    interval_min = int(state.interval_minutes or DEFAULT_INTERVAL_MINUTES)
    start_day, _end_day = _day_bounds_ist(now_utc)
    now_bar = _bar_index(
        now_utc, start_day_utc=start_day, interval_minutes=interval_min
    )

    if tf_on:
        max_trades = int(tf.max_trades_per_symbol_per_day)
        if max_trades > 0 and int(state.trades_today or 0) >= max_trades:
            return (
                False,
                "RISK_POLICY_TRADE_FREQ_MAX_TRADES",
                f"trade_frequency: max_trades_per_symbol_per_day={max_trades} reached.",
            )

        min_bars = int(tf.min_bars_between_trades)
        if min_bars > 0 and state.last_trade_bar_index is not None:
            if now_bar - int(state.last_trade_bar_index) < min_bars:
                return (
                    False,
                    "RISK_POLICY_TRADE_FREQ_MIN_BARS",
                    (
                        "trade_frequency: min_bars_between_trades="
                        f"{min_bars} not satisfied."
                    ),
                )

        cooldown = int(tf.cooldown_after_loss_bars)
        if (
            cooldown > 0
            and state.last_loss_bar_index is not None
            and state.last_loss_time is not None
        ):
            if now_bar - int(state.last_loss_bar_index) < cooldown:
                return (
                    False,
                    "RISK_POLICY_TRADE_FREQ_COOLDOWN_LOSS",
                    f"trade_frequency: cooldown_after_loss_bars={cooldown} active.",
                )

    # Loss-streak pause is applied on trade close updates.
    if (
        lc_on
        and bool(lc.pause_after_loss_streak)
        and int(state.consecutive_losses or 0) >= int(lc.max_consecutive_losses)
    ):
        # Defensive: if state wasn't paused but streak says it should be, pause
        # until EOD.
        start_day, end_day = _day_bounds_ist(now_utc)
        state.paused_until = end_day
        state.paused_reason = "Paused after loss streak."
        return (
            False,
            "RISK_POLICY_LOSS_STREAK_PAUSE",
            f"loss_controls: {state.paused_reason}",
        )

    return True, None, None


def apply_post_trade_updates_on_execution(
    policy: RiskPolicy,
    state: ExecutionPolicyState,
    *,
    now_utc: datetime,
    side: str,
    qty: float,
    exec_price: float | None,
) -> None:
    tf_on = is_group_enforced(policy, "trade_frequency")
    lc_on = is_group_enforced(policy, "loss_controls")
    if not (tf_on or lc_on):
        return

    reset_daily_counters_if_new_day(state, now_utc=now_utc)

    interval_min = int(state.interval_minutes or DEFAULT_INTERVAL_MINUTES)
    start_day, end_day = _day_bounds_ist(now_utc)
    now_bar = _bar_index(
        now_utc, start_day_utc=start_day, interval_minutes=interval_min
    )

    qty_f = float(qty or 0.0)
    if qty_f <= 0:
        return

    price_f = float(exec_price) if exec_price is not None else None
    side_u = (side or "").strip().upper()
    if side_u not in {"BUY", "SELL"}:
        return

    prev_abs, new_abs, is_entry, _is_exit_reduce = classify_position_delta(
        state, side=side_u, qty=qty_f
    )
    if tf_on and is_entry:
        state.trades_today = int(state.trades_today or 0) + 1
        state.last_trade_time = now_utc
        state.last_trade_bar_index = now_bar

    prev_signed = _signed_position_qty(state)
    delta_signed = qty_f if side_u == "BUY" else -qty_f
    new_signed = prev_signed + delta_signed

    prev_side = (state.open_side or "").strip().upper() if state.open_side else None
    prev_qty = abs(prev_signed)
    prev_avg = float(state.open_avg_price) if state.open_avg_price else None
    prev_realized = float(state.open_realized_pnl or 0.0)

    # Always update the lightweight position qty/side so future executions can
    # classify entry/exit structurally, even when price is unavailable.
    def _set_position(
        *, signed_qty: float, avg_price: float | None, realized_pnl: float
    ) -> None:
        if abs(signed_qty) <= 0:
            state.open_side = None
            state.open_qty = 0.0
            state.open_avg_price = None
            state.open_realized_pnl = 0.0
            return
        state.open_side = "BUY" if signed_qty > 0 else "SELL"
        state.open_qty = float(abs(signed_qty))
        state.open_avg_price = avg_price
        state.open_realized_pnl = float(realized_pnl)

    if price_f is None or price_f <= 0:
        # No PnL math; only track net exposure and clear metadata on close.
        if abs(new_signed) <= 0:
            _set_position(signed_qty=0.0, avg_price=None, realized_pnl=0.0)
        else:
            # Keep avg/realized only when staying on the same side; otherwise
            # drop it to avoid misleading PnL computations.
            if prev_side and (
                (prev_side == "BUY" and new_signed > 0)
                or (prev_side == "SELL" and new_signed < 0)
            ):
                _set_position(
                    signed_qty=new_signed,
                    avg_price=state.open_avg_price,
                    realized_pnl=state.open_realized_pnl or 0.0,
                )
            else:
                _set_position(signed_qty=new_signed, avg_price=None, realized_pnl=0.0)
        return

    # With price available, keep avg/realized only when we have a consistent
    # reference for the open position.
    if prev_qty <= 0:
        _set_position(signed_qty=new_signed, avg_price=float(price_f), realized_pnl=0.0)
        return

    if prev_side not in {"BUY", "SELL"}:
        _set_position(signed_qty=new_signed, avg_price=None, realized_pnl=0.0)
        return

    if prev_avg is None or prev_avg <= 0:
        _set_position(signed_qty=new_signed, avg_price=None, realized_pnl=0.0)
        return

    if prev_side == side_u:
        # Scale in: weighted average.
        new_qty = float(abs(new_signed))
        if new_qty > 0:
            new_avg = (prev_avg * prev_qty + price_f * qty_f) / new_qty
        else:
            new_avg = prev_avg
        _set_position(
            signed_qty=new_signed,
            avg_price=float(new_avg),
            realized_pnl=prev_realized,
        )
        return

    # Opposite side: reduce/close/reverse.
    close_qty = min(prev_qty, qty_f)
    pnl = (
        (price_f - prev_avg) * close_qty
        if prev_side == "BUY"
        else (prev_avg - price_f) * close_qty
    )
    realized = prev_realized + float(pnl)
    remaining_open = prev_qty - close_qty

    if remaining_open > 0:
        # Partial close.
        _set_position(
            signed_qty=(remaining_open if prev_side == "BUY" else -remaining_open),
            avg_price=float(prev_avg),
            realized_pnl=float(realized),
        )
        return

    # Trade fully closed (may reverse).
    total_pnl = float(realized)
    _set_position(signed_qty=0.0, avg_price=None, realized_pnl=0.0)

    if lc_on or tf_on:
        if total_pnl < 0:
            state.last_loss_time = now_utc
            state.last_loss_bar_index = now_bar
            if lc_on:
                state.consecutive_losses = int(state.consecutive_losses or 0) + 1
        else:
            state.last_loss_time = None
            state.last_loss_bar_index = None
            if lc_on:
                state.consecutive_losses = 0

    lc = policy.loss_controls
    if (
        lc_on
        and bool(lc.pause_after_loss_streak)
        and int(state.consecutive_losses or 0) >= int(lc.max_consecutive_losses)
    ):
        state.paused_until = (
            end_day if str(lc.pause_duration or "").upper() == "EOD" else end_day
        )
        state.paused_reason = "Paused after loss streak."

    if abs(new_signed) > 0:
        # Reverse: open a new trade using the current execution price.
        _set_position(signed_qty=new_signed, avg_price=float(price_f), realized_pnl=0.0)


def log_block(
    *,
    reason_code: str,
    message: str,
    key: ExecutionScopeKey,
    policy: RiskPolicy,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "reason_code": reason_code,
        "message": message,
        "user_id": key.user_id,
        "strategy_ref": key.strategy_ref,
        "symbol": key.symbol,
        "product": key.product,
        "policy": {
            "trade_frequency": getattr(policy, "trade_frequency", None).model_dump()  # type: ignore[attr-defined]
            if hasattr(getattr(policy, "trade_frequency", None), "model_dump")
            else getattr(policy, "trade_frequency", None).__dict__,
            "loss_controls": getattr(policy, "loss_controls", None).model_dump()  # type: ignore[attr-defined]
            if hasattr(getattr(policy, "loss_controls", None), "model_dump")
            else getattr(policy, "loss_controls", None).__dict__,
        },
    }
    if extra:
        payload.update(extra)
    logger.warning("Order blocked by execution policy", extra={"extra": payload})


__all__ = [
    "ExecutionScopeKey",
    "scope_key_for_order",
    "classify_position_delta",
    "resolve_interval_for_order",
    "interval_minutes_for_order",
    "get_or_create_execution_state",
    "reset_daily_counters_if_new_day",
    "is_paused",
    "apply_pre_trade_checks",
    "apply_post_trade_updates_on_execution",
    "log_block",
]
