from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import log, sqrt
from threading import Event, Thread
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.market_hours import IST_OFFSET
from app.db.session import SessionLocal
from app.models import Alert, IndicatorRule, Order, Position, User
from app.schemas.indicator_rules import (
    IndicatorCondition,
    LogicType,
    OperatorType,
    TriggerMode,
)
from app.services.market_data import Timeframe, load_series


class IndicatorAlertError(RuntimeError):
    """Raised when indicator alert evaluation cannot be completed."""


_scheduler_started = False
_scheduler_stop_event = Event()


def _now_ist_naive() -> datetime:
    """Return current time in IST as a naive datetime."""

    return (datetime.now(UTC) + IST_OFFSET).replace(tzinfo=None)


def _deserialize_conditions(
    rule: IndicatorRule,
) -> Tuple[LogicType, List[IndicatorCondition]]:
    try:
        raw = json.loads(rule.conditions_json)
    except json.JSONDecodeError as exc:
        msg = f"Invalid conditions JSON for rule {rule.id}: {exc}"
        raise IndicatorAlertError(msg) from exc

    if isinstance(raw, dict):
        # Allow a simple object with a single condition.
        raw = [raw]
    if not isinstance(raw, list):
        raise IndicatorAlertError(f"Conditions for rule {rule.id} must be a list")

    conditions: List[IndicatorCondition] = []
    for item in raw:
        conditions.append(IndicatorCondition.parse_obj(item))

    logic: LogicType = rule.logic if rule.logic in {"AND", "OR"} else "AND"
    return logic, conditions


@dataclass
class IndicatorSample:
    value: Optional[float]
    prev_value: Optional[float]
    bar_time: Optional[datetime]


def _compute_sma(
    values: Sequence[float],
    period: int,
) -> Tuple[Optional[float], Optional[float]]:
    if period <= 0 or len(values) < period:
        return None, None
    curr = sum(values[-period:]) / period
    prev = None
    if len(values) >= period + 1:
        prev = sum(values[-period - 1 : -1]) / period
    return curr, prev


def _compute_rsi(
    values: Sequence[float],
    period: int,
) -> Tuple[Optional[float], Optional[float]]:
    if period <= 0 or len(values) < period + 1:
        return None, None

    def rsi_slice(slice_vals: Sequence[float]) -> Optional[float]:
        if len(slice_vals) < period + 1:
            return None
        gains: List[float] = []
        losses: List[float] = []
        for prev, curr in zip(
            slice_vals[:-1],
            slice_vals[1:],
            strict=False,
        ):
            delta = curr - prev
            if delta >= 0:
                gains.append(delta)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(-delta)
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    curr = rsi_slice(values)
    prev = rsi_slice(values[:-1]) if len(values) >= period + 2 else None
    return curr, prev


def _compute_volatility_pct(values: Sequence[float], window: int) -> Optional[float]:
    if window <= 1 or len(values) < window:
        return None
    rets: List[float] = []
    for prev, curr in zip(
        values[-window - 1 : -1],
        values[-window:],
        strict=False,
    ):
        if prev <= 0 or curr <= 0:
            continue
        rets.append(log(curr / prev))
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
    return sqrt(var) * 100.0


def _compute_atr_pct(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
) -> Optional[float]:
    if period <= 0 or len(highs) < period + 1 or len(closes) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(highs)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[-period:]) / period
    last_close = closes[-1]
    if last_close == 0:
        return None
    return (atr / last_close) * 100.0


def _compute_perf_pct(values: Sequence[float], window: int) -> Optional[float]:
    if window <= 0 or len(values) <= window:
        return None
    past = values[-window - 1]
    curr = values[-1]
    if past == 0:
        return None
    return (curr - past) / past * 100.0


def _compute_volume_ratio(volumes: Sequence[float], window: int) -> Optional[float]:
    if window <= 0 or len(volumes) < window + 1:
        return None
    today = volumes[-1]
    avg = sum(volumes[-window - 1 : -1]) / window
    if avg == 0:
        return None
    return today / avg


def _load_candles_for_rule(
    db: Session,
    settings: Settings,
    symbol: str,
    exchange: str,
    timeframe: Timeframe,
) -> List[Dict]:
    now_ist = datetime.now(UTC) + IST_OFFSET
    end = now_ist.replace(tzinfo=None)
    # Use conservative lookback; indicator-specific helpers ensure they
    # have enough bars for their calculations.
    if timeframe in {"1d", "1mo", "1y"}:
        lookback_days = 400
    else:
        lookback_days = 90
    start = end - timedelta(days=lookback_days)
    return load_series(
        db,
        settings,
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        start=start,
        end=end,
    )


def _compute_indicator_sample(
    candles: List[Dict],
    condition: IndicatorCondition,
) -> IndicatorSample:
    if not candles:
        return IndicatorSample(None, None, None)

    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    volumes = [float(c["volume"]) for c in candles]
    bar_time = candles[-1]["ts"]

    indicator = condition.indicator
    params = condition.params or {}

    if indicator == "RSI":
        period = int(params.get("period", 14))
        value, prev = _compute_rsi(closes, period)
    elif indicator == "MA":
        period = int(params.get("period", 50))
        value, prev = _compute_sma(closes, period)
    elif indicator == "VOLATILITY":
        window = int(params.get("window", 20))
        value = _compute_volatility_pct(closes, window)
        prev = None
    elif indicator == "ATR":
        period = int(params.get("period", 14))
        value = _compute_atr_pct(highs, lows, closes, period)
        prev = None
    elif indicator == "PERF_PCT":
        window = int(params.get("window", 20))
        value = _compute_perf_pct(closes, window)
        prev = None
    elif indicator == "VOLUME_RATIO":
        window = int(params.get("window", 20))
        value = _compute_volume_ratio(volumes, window)
        prev = None
    else:
        raise IndicatorAlertError(f"Unsupported indicator: {indicator}")

    return IndicatorSample(value, prev, bar_time)


def _condition_matches(
    cond: IndicatorCondition,
    sample: IndicatorSample,
) -> bool:
    value = sample.value
    prev = sample.prev_value
    if value is None:
        return False

    op: OperatorType = cond.operator
    t1 = cond.threshold_1
    t2 = cond.threshold_2

    if op == "GT":
        return value > t1
    if op == "LT":
        return value < t1
    if op == "BETWEEN":
        if t2 is None:
            return False
        return t1 <= value <= t2
    if op == "OUTSIDE":
        if t2 is None:
            return False
        return value < t1 or value > t2
    if op == "CROSS_ABOVE":
        if prev is None:
            return False
        return prev <= t1 and value > t1
    if op == "CROSS_BELOW":
        if prev is None:
            return False
        return prev >= t1 and value < t1
    return False


def _iter_rule_symbols(
    db: Session,
    settings: Settings,
    rule: IndicatorRule,
) -> Iterable[Tuple[str, str]]:
    if rule.symbol:
        yield rule.symbol, (rule.exchange or "NSE")
        return

    if rule.universe == "HOLDINGS":
        # Resolve live holdings for the rule's user.
        user = db.get(User, rule.user_id)
        if user is None:
            return
        try:
            from app.api.positions import list_holdings

            holdings = list_holdings(db=db, settings=settings, user=user)
        except Exception:
            return
        for h in holdings:
            exch = getattr(h, "exchange", None) or "NSE"
            yield h.symbol, exch


def _create_alert_and_order(
    db: Session,
    rule: IndicatorRule,
    settings: Settings,
    symbol: str,
    exchange: str,
    sample: IndicatorSample,
) -> None:
    # Serialize a minimal payload so alerts are inspectable later.
    payload = {
        "symbol": symbol,
        "exchange": exchange,
        "timeframe": rule.timeframe,
        "conditions": json.loads(rule.conditions_json),
        "action_type": rule.action_type,
        "action_params": json.loads(rule.action_params_json or "{}"),
        "indicator_value": sample.value,
        "indicator_prev": sample.prev_value,
    }
    raw_payload = json.dumps(payload, default=str)

    alert = Alert(
        user_id=rule.user_id,
        strategy_id=rule.strategy_id,
        symbol=symbol,
        exchange=exchange,
        interval=rule.timeframe,
        action=rule.action_type,
        qty=None,
        price=None,
        platform="INTERNAL",
        source="INTERNAL_INDICATOR",
        raw_payload=raw_payload,
        reason=payload.get("action_type"),
        bar_time=sample.bar_time,
        rule_id=rule.id,
    )
    db.add(alert)
    db.flush()  # ensure alert.id is populated

    if rule.action_type == "SELL_PERCENT":
        params = json.loads(rule.action_params_json or "{}")
        percent = float(params.get("percent", 0))
        if percent <= 0:
            return
        # Use positions table as an approximation of current holdings quantity.
        pos = (
            db.query(Position)
            .filter(
                Position.symbol == symbol,
                Position.product == "CNC",
            )
            .one_or_none()
        )
        if pos is None or pos.qty <= 0:
            return
        qty = max(int(pos.qty * percent / 100.0), 1)
        order = Order(
            user_id=rule.user_id,
            strategy_id=rule.strategy_id,
            alert_id=alert.id,
            symbol=symbol,
            exchange=exchange,
            side="SELL",
            qty=float(qty),
            price=None,
            order_type="MARKET",
            product="CNC",
            gtt=False,
            status="WAITING",
            mode="MANUAL",
            simulated=False,
        )
        db.add(order)
    elif rule.action_type == "BUY_QUANTITY":
        params = json.loads(rule.action_params_json or "{}")
        qty = float(params.get("quantity", 0))
        if qty <= 0:
            return
        order = Order(
            user_id=rule.user_id,
            strategy_id=rule.strategy_id,
            alert_id=alert.id,
            symbol=symbol,
            exchange=exchange,
            side="BUY",
            qty=qty,
            price=None,
            order_type="MARKET",
            product="CNC",
            gtt=False,
            status="WAITING",
            mode="MANUAL",
            simulated=False,
        )
        db.add(order)


def _evaluate_rule_for_symbol(
    db: Session,
    settings: Settings,
    rule: IndicatorRule,
    symbol: str,
    exchange: str,
    logic: LogicType,
    conditions: List[IndicatorCondition],
) -> None:
    timeframe: Timeframe = rule.timeframe  # type: ignore[assignment]
    candles = _load_candles_for_rule(db, settings, symbol, exchange, timeframe)
    if not candles:
        return

    samples: List[IndicatorSample] = []
    for cond in conditions:
        samples.append(_compute_indicator_sample(candles, cond))

    results = [
        _condition_matches(cond, sample)
        for cond, sample in zip(conditions, samples, strict=False)
    ]
    if not results:
        return

    matched = all(results) if logic == "AND" else any(results)
    if not matched:
        return

    # Triggered: respect trigger_mode
    trigger_mode: TriggerMode = rule.trigger_mode or "ONCE"  # type: ignore[assignment]
    bar_time_candidates = [s.bar_time for s in samples if s.bar_time is not None]
    bar_time = max(bar_time_candidates) if bar_time_candidates else None

    if trigger_mode == "ONCE" and rule.last_triggered_at is not None:
        return
    if trigger_mode == "ONCE_PER_BAR":
        if bar_time is None:
            return
        if rule.last_triggered_at is not None and rule.last_triggered_at >= bar_time:
            return

    sample = samples[0]
    _create_alert_and_order(db, rule, settings, symbol, exchange, sample)
    rule.last_triggered_at = bar_time or _now_ist_naive()


def evaluate_indicator_rules_once() -> None:
    """Evaluate all enabled indicator rules once.

    This is written so it can be called from either a background thread
    or an external scheduler via a small wrapper endpoint.
    """

    settings = get_settings()
    now = _now_ist_naive()

    with SessionLocal() as db:
        rules: List[IndicatorRule] = (
            db.query(IndicatorRule)
            .filter(
                IndicatorRule.enabled.is_(True),
                or_(
                    IndicatorRule.expires_at.is_(None),
                    IndicatorRule.expires_at >= now,
                ),
            )
            .all()
        )
        if not rules:
            return

        for rule in rules:
            try:
                logic, conditions = _deserialize_conditions(rule)
            except IndicatorAlertError:
                # Skip malformed rules without failing the whole batch.
                continue

            for symbol, exchange in _iter_rule_symbols(db, settings, rule):
                try:
                    _evaluate_rule_for_symbol(
                        db,
                        settings,
                        rule,
                        symbol,
                        exchange,
                        logic,
                        conditions,
                    )
                except IndicatorAlertError:
                    continue

        db.commit()


def _indicator_alerts_loop() -> None:  # pragma: no cover - background loop
    interval = timedelta(minutes=5)
    next_run = _now_ist_naive() + timedelta(minutes=1)

    while not _scheduler_stop_event.is_set():
        now = _now_ist_naive()
        sleep_for = (next_run - now).total_seconds()
        if sleep_for > 0:
            _scheduler_stop_event.wait(timeout=sleep_for)
            if _scheduler_stop_event.is_set():
                return

        try:
            evaluate_indicator_rules_once()
        except Exception:
            # Errors are logged via the global logging config; never kill the loop.
            pass

        next_run = _now_ist_naive() + interval


def schedule_indicator_alerts() -> None:
    """Start a background thread that periodically evaluates indicator rules."""

    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    thread = Thread(
        target=_indicator_alerts_loop,
        name="indicator-alerts",
        daemon=True,
    )
    thread.start()


__all__ = [
    "IndicatorAlertError",
    "evaluate_indicator_rules_once",
    "schedule_indicator_alerts",
]
