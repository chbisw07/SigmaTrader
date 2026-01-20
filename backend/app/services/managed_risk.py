from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.clients import AngelOneClient, AngelOneSession, ZerodhaClient
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.core.market_hours import is_market_open_now
from app.db.session import SessionLocal
from app.models import BrokerConnection, ManagedRiskPosition, Order, Position
from app.schemas.managed_risk import DistanceSpec, RiskSpec
from app.schemas.risk_policy import RiskPolicy
from app.services.broker_instruments import resolve_broker_symbol_and_token
from app.services.broker_secrets import get_broker_secret
from app.services.market_data import load_series
from app.services.risk_policy_enforcement import is_group_enforced
from app.services.system_events import record_system_event

logger = logging.getLogger(__name__)

_scheduler_started = False
_scheduler_stop_event = Event()


def _now_utc() -> datetime:
    return datetime.now(UTC)


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


def _atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int,
) -> float | None:
    if period <= 1:
        return None
    n = min(len(closes), len(highs), len(lows))
    if n < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(float(tr))
    if len(trs) < period:
        return None
    # Wilder ATR
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return float(atr_val)


def _compute_atr_distance(
    db: Session,
    settings: Settings,
    *,
    symbol: str,
    exchange: str,
    spec: DistanceSpec,
) -> float | None:
    now = _now_utc()
    tf = spec.atr_tf
    # Keep the fetch window bounded; enough for ATR(period) even on daily bars.
    window_days = 30 if tf in {"1m", "5m", "15m", "30m", "1h"} else 120
    start = now - timedelta(days=window_days)
    end = now
    try:
        candles = load_series(
            db,
            settings,
            symbol=symbol,
            exchange=exchange,
            timeframe=tf,  # type: ignore[arg-type]
            start=start,
            end=end,
            allow_fetch=True,
        )
    except Exception:
        candles = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for c in candles or []:
        try:
            h = float(c.get("high") or 0.0)
            lo = float(c.get("low") or 0.0)
            cl = float(c.get("close") or 0.0)
        except Exception:
            continue
        if h <= 0 or lo <= 0 or cl <= 0:
            continue
        highs.append(h)
        lows.append(lo)
        closes.append(cl)
    atr_val = _atr(highs, lows, closes, int(spec.atr_period))
    if atr_val is None or atr_val <= 0:
        return None
    return float(atr_val) * float(spec.value)


def _distance_from_entry(
    db: Session,
    settings: Settings,
    *,
    entry_price: float,
    symbol: str,
    exchange: str,
    spec: DistanceSpec,
) -> float | None:
    if not spec.enabled:
        return None
    mode = (spec.mode or "PCT").strip().upper()
    if mode == "ABS":
        return float(spec.value)
    if mode == "PCT":
        return float(entry_price) * float(spec.value) / 100.0
    if mode == "ATR":
        return _compute_atr_distance(
            db,
            settings,
            symbol=symbol,
            exchange=exchange,
            spec=spec,
        )
    return None


@dataclass(frozen=True)
class StopUpdate:
    best: float
    trail: float | None
    is_trailing_active: bool
    current_stop: float
    triggered: bool
    exit_reason: str | None


def _update_stop_state(
    *,
    side: str,
    entry_price: float,
    stop_distance: float,
    trail_distance: float | None,
    activation_distance: float | None,
    best: float,
    trail: float | None,
    is_trailing_active: bool,
    ltp: float,
) -> StopUpdate:
    side_u = (side or "").strip().upper()
    if side_u not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    if stop_distance <= 0:
        raise ValueError("stop_distance must be > 0")

    initial_sl = (
        float(entry_price) - float(stop_distance)
        if side_u == "BUY"
        else float(entry_price) + float(stop_distance)
    )

    if side_u == "BUY":
        best2 = max(float(best), float(ltp))
        active2 = bool(is_trailing_active)
        if trail_distance is not None and trail_distance > 0:
            if activation_distance is not None and activation_distance > 0:
                if best2 >= float(entry_price) + float(activation_distance):
                    active2 = True
            else:
                active2 = True
        else:
            active2 = False

        trail2 = trail
        if active2 and trail_distance is not None and trail_distance > 0:
            candidate = best2 - float(trail_distance)
            if trail2 is None:
                trail2 = candidate
            else:
                trail2 = max(float(trail2), candidate)

            # Trailing should never be worse than the initial SL.
            trail2 = max(float(trail2), float(initial_sl))

        current_stop = (
            float(trail2) if active2 and trail2 is not None else float(initial_sl)
        )
        triggered = float(ltp) <= current_stop
        if triggered and active2 and trail2 is not None:
            reason = "TRAIL"
        else:
            reason = "SL" if triggered else None
        return StopUpdate(
            best=float(best2),
            trail=float(trail2) if trail2 is not None else None,
            is_trailing_active=bool(active2),
            current_stop=float(current_stop),
            triggered=bool(triggered),
            exit_reason=reason,
        )

    # SELL (short / MIS)
    best2 = min(float(best), float(ltp))
    active2 = bool(is_trailing_active)
    if trail_distance is not None and trail_distance > 0:
        if activation_distance is not None and activation_distance > 0:
            if best2 <= float(entry_price) - float(activation_distance):
                active2 = True
        else:
            active2 = True
    else:
        active2 = False

    trail2 = trail
    if active2 and trail_distance is not None and trail_distance > 0:
        candidate = best2 + float(trail_distance)
        if trail2 is None:
            trail2 = candidate
        else:
            trail2 = min(float(trail2), candidate)
        trail2 = min(float(trail2), float(initial_sl))

    current_stop = (
        float(trail2) if active2 and trail2 is not None else float(initial_sl)
    )
    triggered = float(ltp) >= current_stop
    if triggered and active2 and trail2 is not None:
        reason = "TRAIL"
    else:
        reason = "SL" if triggered else None
    return StopUpdate(
        best=float(best2),
        trail=float(trail2) if trail2 is not None else None,
        is_trailing_active=bool(active2),
        current_stop=float(current_stop),
        triggered=bool(triggered),
        exit_reason=reason,
    )


def _get_zerodha_client(
    db: Session, settings: Settings, *, user_id: int
) -> ZerodhaClient:
    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "zerodha",
            BrokerConnection.user_id == user_id,
        )
        .order_by(BrokerConnection.updated_at.desc())
        .first()
    )
    if conn is None:
        raise RuntimeError("Zerodha is not connected.")

    api_key = get_broker_secret(db, settings, "zerodha", "api_key", user_id=user_id)
    if not api_key:
        raise RuntimeError("Zerodha API key is not configured.")

    from kiteconnect import KiteConnect  # type: ignore[import]

    access_token = decrypt_token(settings, conn.access_token_encrypted)
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return ZerodhaClient(kite)


def _get_angelone_client(
    db: Session, settings: Settings, *, user_id: int
) -> AngelOneClient:
    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker_name == "angelone",
            BrokerConnection.user_id == user_id,
        )
        .order_by(BrokerConnection.updated_at.desc())
        .first()
    )
    if conn is None:
        raise RuntimeError("AngelOne is not connected.")

    api_key = get_broker_secret(db, settings, "angelone", "api_key", user_id=user_id)
    if not api_key:
        raise RuntimeError("SmartAPI API key is not configured.")

    raw = decrypt_token(settings, conn.access_token_encrypted)
    import json

    parsed = json.loads(raw) if raw else {}
    jwt = str(parsed.get("jwt_token") or "")
    if not jwt:
        raise RuntimeError("AngelOne session is missing jwt_token.")

    session = AngelOneSession(
        jwt_token=jwt,
        refresh_token=str(parsed.get("refresh_token") or "") or None,
        feed_token=str(parsed.get("feed_token") or "") or None,
        client_code=str(parsed.get("client_code") or "") or None,
    )
    return AngelOneClient(api_key=api_key, session=session)


def _fetch_ltp(
    db: Session,
    settings: Settings,
    *,
    broker_name: str,
    user_id: int,
    symbol: str,
    exchange: str,
) -> float:
    broker = (broker_name or "zerodha").strip().lower()
    if broker == "zerodha":
        client = _get_zerodha_client(db, settings, user_id=user_id)
        return float(client.get_ltp(exchange=exchange, tradingsymbol=symbol))
    if broker == "angelone":
        resolved = resolve_broker_symbol_and_token(
            db,
            broker_name="angelone",
            exchange=exchange,
            symbol=symbol,
        )
        if resolved is None:
            raise RuntimeError(
                f"AngelOne instrument mapping missing for {exchange}:{symbol}."
            )
        broker_symbol, token = resolved
        client = _get_angelone_client(db, settings, user_id=user_id)
        return float(
            client.get_ltp(
                exchange=exchange,
                tradingsymbol=broker_symbol,
                symboltoken=token,
            )
        )
    raise RuntimeError(f"LTP not supported for broker: {broker}")


def ensure_managed_risk_for_executed_order(
    db: Session,
    settings: Settings,
    *,
    order: Order,
    filled_qty: float,
    avg_price: float | None,
    policy: RiskPolicy | None = None,
) -> ManagedRiskPosition | None:
    if getattr(order, "is_exit", False):
        return None
    raw_order_spec = RiskSpec.from_json(getattr(order, "risk_spec_json", None))
    stop_rules_enforced = bool(policy is not None and is_group_enforced(policy, "stop_rules"))

    def _policy_spec() -> RiskSpec | None:
        if not stop_rules_enforced or policy is None:
            return None
        sr = policy.stop_rules
        tr = policy.trade_risk
        stop_ref = (tr.stop_reference or "ATR").strip().upper()
        if stop_ref == "FIXED_PCT":
            stop_pct = float(sr.fallback_stop_pct)
            # Apply percent clamp up-front so the stored spec matches the
            # resulting absolute distance.
            stop_pct = max(float(sr.min_stop_distance_pct), min(stop_pct, float(sr.max_stop_distance_pct)))
            act_pct = float(getattr(sr, "trail_activation_pct", 0.0) or 0.0)
            return RiskSpec(
                stop_loss=DistanceSpec(
                    enabled=True,
                    mode="PCT",
                    value=float(stop_pct),
                ),
                trailing_stop=DistanceSpec(
                    enabled=bool(sr.trailing_stop_enabled),
                    mode="PCT",
                    value=float(stop_pct),
                ),
                trailing_activation=DistanceSpec(
                    enabled=bool(sr.trailing_stop_enabled) and float(act_pct) > 0,
                    mode="PCT",
                    value=float(act_pct),
                ),
                exit_order_type="MARKET",
            )
        # ATR basis (default).
        act_atr = float(sr.trail_activation_atr)
        return RiskSpec(
            stop_loss=DistanceSpec(
                enabled=True,
                mode="ATR",
                value=float(sr.initial_stop_atr),
                atr_period=int(sr.atr_period),
                atr_tf="1d",
            ),
            trailing_stop=DistanceSpec(
                enabled=bool(sr.trailing_stop_enabled),
                mode="ATR",
                value=float(sr.initial_stop_atr),
                atr_period=int(sr.atr_period),
                atr_tf="1d",
            ),
            trailing_activation=DistanceSpec(
                enabled=bool(sr.trailing_stop_enabled) and float(act_atr) > 0,
                mode="ATR",
                value=float(act_atr),
                atr_period=int(sr.atr_period),
                atr_tf="1d",
            ),
            exit_order_type="MARKET",
        )

    base = _policy_spec()
    if base is None and raw_order_spec is None:
        return None

    # Merge order-specific exits additively (cannot disable policy stops).
    spec = base or RiskSpec()
    if raw_order_spec is not None:
        if raw_order_spec.stop_loss.enabled:
            spec.stop_loss = raw_order_spec.stop_loss
        if raw_order_spec.trailing_stop.enabled:
            spec.trailing_stop = raw_order_spec.trailing_stop
        if raw_order_spec.trailing_activation.enabled:
            spec.trailing_activation = raw_order_spec.trailing_activation
        if raw_order_spec.exit_order_type:
            spec.exit_order_type = raw_order_spec.exit_order_type

    side = (order.side or "").strip().upper()
    product = (order.product or "").strip().upper()
    if side == "SELL" and product != "MIS":
        # Selling delivery holdings is not a short entry; allow this order to
        # reduce an existing long managed-risk position but do not create a new
        # short managed-risk position.
        create_entry = False
    else:
        create_entry = True

    if avg_price is None or avg_price <= 0:
        # Best-effort fallback: use persisted order price when it exists.
        if order.price is None or float(order.price) <= 0:
            return None
        avg_price = float(order.price)

    symbol, exchange = _split_symbol_exchange(order.symbol, order.exchange)

    stop_dist = _distance_from_entry(
        db,
        settings,
        entry_price=float(avg_price),
        symbol=symbol,
        exchange=exchange,
        spec=spec.stop_loss,
    )
    if stop_dist is None or stop_dist <= 0:
        # If ATR computation fails, fall back to fixed percent when policy is
        # enabled.
        if stop_rules_enforced and policy is not None:
            sr = policy.stop_rules
            stop_pct = float(sr.fallback_stop_pct)
            stop_pct = max(float(sr.min_stop_distance_pct), min(stop_pct, float(sr.max_stop_distance_pct)))
            stop_dist = float(avg_price) * stop_pct / 100.0
        else:
            return None

    if stop_rules_enforced and policy is not None:
        sr = policy.stop_rules
        min_abs = float(avg_price) * float(sr.min_stop_distance_pct) / 100.0
        max_abs = float(avg_price) * float(sr.max_stop_distance_pct) / 100.0
        stop_dist = max(float(min_abs), min(float(stop_dist), float(max_abs)))
        # Global policy is authoritative: per-order overrides may tighten but
        # must not loosen the policy-derived stop distance.
        if base is not None:
            policy_stop = _distance_from_entry(
                db,
                settings,
                entry_price=float(avg_price),
                symbol=symbol,
                exchange=exchange,
                spec=base.stop_loss,
            )
            if policy_stop is None or float(policy_stop) <= 0:
                stop_pct = float(sr.fallback_stop_pct)
                stop_pct = max(
                    float(sr.min_stop_distance_pct),
                    min(stop_pct, float(sr.max_stop_distance_pct)),
                )
                policy_stop = float(avg_price) * stop_pct / 100.0
            policy_stop = max(float(min_abs), min(float(policy_stop), float(max_abs)))
            if float(stop_dist) > float(policy_stop):
                stop_dist = float(policy_stop)
                spec.stop_loss = base.stop_loss

    trail_dist = _distance_from_entry(
        db,
        settings,
        entry_price=float(avg_price),
        symbol=symbol,
        exchange=exchange,
        spec=spec.trailing_stop,
    )
    act_dist = _distance_from_entry(
        db,
        settings,
        entry_price=float(avg_price),
        symbol=symbol,
        exchange=exchange,
        spec=spec.trailing_activation,
    )
    if spec.trailing_stop.enabled and (trail_dist is None or float(trail_dist) <= 0):
        trail_dist = float(stop_dist)

    if stop_rules_enforced and policy is not None and spec.trailing_stop.enabled and trail_dist is not None:
        sr = policy.stop_rules
        min_abs = float(avg_price) * float(sr.min_stop_distance_pct) / 100.0
        max_abs = float(avg_price) * float(sr.max_stop_distance_pct) / 100.0
        trail_dist = max(float(min_abs), min(float(trail_dist), float(max_abs)))
        if base is not None and base.trailing_stop.enabled:
            policy_trail = _distance_from_entry(
                db,
                settings,
                entry_price=float(avg_price),
                symbol=symbol,
                exchange=exchange,
                spec=base.trailing_stop,
            )
            if policy_trail is None or float(policy_trail) <= 0:
                policy_trail = float(stop_dist)
            policy_trail = max(float(min_abs), min(float(policy_trail), float(max_abs)))
            if float(trail_dist) > float(policy_trail):
                trail_dist = float(policy_trail)
                spec.trailing_stop = base.trailing_stop

    if spec.trailing_activation.enabled and (act_dist is None or float(act_dist) <= 0):
        # Best-effort fallback when ATR activation is requested but data is
        # missing: scale activation off the stop distance.
        if stop_rules_enforced and policy is not None and policy.trade_risk.stop_reference == "ATR":
            base_atr = float(policy.stop_rules.initial_stop_atr) or 1.0
            act_atr = float(policy.stop_rules.trail_activation_atr) or 0.0
            if act_atr > 0 and base_atr > 0:
                act_dist = float(stop_dist) * (act_atr / base_atr)
    if (
        stop_rules_enforced
        and policy is not None
        and base is not None
        and base.trailing_activation.enabled
        and spec.trailing_activation.enabled
        and act_dist is not None
        and float(act_dist) > 0
    ):
        policy_act = _distance_from_entry(
            db,
            settings,
            entry_price=float(avg_price),
            symbol=symbol,
            exchange=exchange,
            spec=base.trailing_activation,
        )
        if policy_act is None or float(policy_act) <= 0:
            # If ATR activation can't be computed, keep the current act_dist
            # (already best-effort).
            policy_act = float(act_dist)
        if float(act_dist) > float(policy_act):
            act_dist = float(policy_act)
            spec.trailing_activation = base.trailing_activation

    # Initialize per spec.
    best = float(avg_price)
    init = _update_stop_state(
        side=side,
        entry_price=float(avg_price),
        stop_distance=float(stop_dist),
        trail_distance=float(trail_dist) if trail_dist else None,
        activation_distance=float(act_dist) if act_dist else None,
        best=float(best),
        trail=None,
        is_trailing_active=False,
        ltp=float(avg_price),
    )

    trail_initial: float | None = None
    trailing_active_initial = False
    if spec.trailing_stop.enabled:
        trailing_active_initial = not spec.trailing_activation.enabled
        trail_initial = init.current_stop if trailing_active_initial else None

    # Position-level: maintain at most one ACTIVE managed-risk row for a
    # broker+symbol+product+side (per user).
    existing_same = (
        db.query(ManagedRiskPosition)
        .filter(
            ManagedRiskPosition.user_id == order.user_id,
            ManagedRiskPosition.broker_name == (order.broker_name or "zerodha").strip().lower(),
            ManagedRiskPosition.symbol == symbol,
            ManagedRiskPosition.exchange == exchange,
            ManagedRiskPosition.product == product,
            ManagedRiskPosition.side == side,
            ManagedRiskPosition.status.in_(["ACTIVE"]),
        )
        .order_by(ManagedRiskPosition.updated_at.desc())
        .first()
    )
    opposite_side = "SELL" if side == "BUY" else "BUY"
    existing_opp = (
        db.query(ManagedRiskPosition)
        .filter(
            ManagedRiskPosition.user_id == order.user_id,
            ManagedRiskPosition.broker_name == (order.broker_name or "zerodha").strip().lower(),
            ManagedRiskPosition.symbol == symbol,
            ManagedRiskPosition.exchange == exchange,
            ManagedRiskPosition.product == product,
            ManagedRiskPosition.side == opposite_side,
            ManagedRiskPosition.status.in_(["ACTIVE"]),
        )
        .order_by(ManagedRiskPosition.updated_at.desc())
        .first()
    )

    # Reduce/close opposite-side managed risk on fills that net out exposure.
    add_qty = float(filled_qty or 0.0)
    if existing_opp is not None and add_qty > 0:
        before = float(existing_opp.qty or 0.0)
        remaining_opp = max(before - add_qty, 0.0)
        if remaining_opp <= 0:
            add_qty = max(add_qty - before, 0.0)
            existing_opp.qty = 0.0
            existing_opp.status = "EXITED"
            existing_opp.exit_reason = existing_opp.exit_reason or "MANUAL"
            existing_opp.updated_at = _now_utc()
            db.add(existing_opp)
            db.flush()
        else:
            existing_opp.qty = float(remaining_opp)
            existing_opp.updated_at = _now_utc()
            db.add(existing_opp)
            db.flush()
            # This fill only reduced the opposite position; do not create a new
            # managed-risk entry for the other side.
            add_qty = 0.0

    if not create_entry or add_qty <= 0:
        return None

    if existing_same is not None:
        prev_qty = float(existing_same.qty or 0.0)
        next_qty = prev_qty + float(add_qty)
        if next_qty > 0 and avg_price is not None and avg_price > 0:
            existing_same.entry_price = (
                (float(existing_same.entry_price) * prev_qty + float(avg_price) * float(add_qty))
                / next_qty
            )
        existing_same.qty = float(next_qty)
        existing_same.risk_spec_json = spec.to_json()
        existing_same.updated_at = _now_utc()
        db.add(existing_same)
        db.flush()
        return existing_same

    exec_target = (
        getattr(order, "execution_target", None) or "LIVE"
    ).strip().upper() or "LIVE"
    mrp = ManagedRiskPosition(
        user_id=order.user_id,
        entry_order_id=int(order.id),
        broker_name=(order.broker_name or "zerodha").strip().lower() or "zerodha",
        symbol=symbol,
        exchange=exchange,
        product=product,
        side=side,
        qty=float(add_qty or order.qty or 0.0),
        execution_target=exec_target,
        risk_spec_json=spec.to_json(),
        entry_price=float(avg_price),
        stop_distance=float(stop_dist),
        trail_distance=float(trail_dist) if trail_dist else None,
        activation_distance=float(act_dist) if act_dist else None,
        best_favorable_price=float(best),
        trail_price=float(trail_initial) if trail_initial is not None else None,
        is_trailing_active=bool(trailing_active_initial),
        last_ltp=None,
        status="ACTIVE",
        exit_order_id=None,
        exit_reason=None,
    )
    db.add(mrp)
    db.flush()
    record_system_event(
        db,
        level="INFO",
        category="risk",
        message="Managed risk position created",
        correlation_id="managed-risk",
        details={
            "managed_risk_id": mrp.id,
            "entry_order_id": order.id,
            "symbol": symbol,
            "exchange": exchange,
            "side": side,
            "qty": mrp.qty,
        },
    )
    return mrp


def _mark_exit_executed(db: Session, *, exit_order_id: int) -> int:
    now = _now_utc()
    q = db.query(ManagedRiskPosition).filter(
        ManagedRiskPosition.exit_order_id == int(exit_order_id),
        ManagedRiskPosition.status.in_(["ACTIVE", "EXITING"]),
    )
    updated = q.update(
        {
            ManagedRiskPosition.status: "EXITED",
            ManagedRiskPosition.updated_at: now,
        },
        synchronize_session=False,
    )
    return int(updated or 0)


def mark_managed_risk_exit_executed(db: Session, *, exit_order_id: int) -> int:
    """Mark a managed risk position as EXITED when its exit order is executed."""

    updated = _mark_exit_executed(db, exit_order_id=exit_order_id)
    if updated:
        record_system_event(
            db,
            level="INFO",
            category="risk",
            message="Managed risk position exited",
            correlation_id="managed-risk",
            details={"exit_order_id": int(exit_order_id)},
        )
    return int(updated)


def _mark_manual_exit_if_position_closed(
    db: Session, *, mrp: ManagedRiskPosition
) -> bool:
    pos = (
        db.query(Position)
        .filter(
            Position.broker_name == mrp.broker_name,
            Position.symbol == mrp.symbol,
            Position.exchange == mrp.exchange,
            Position.product == mrp.product,
        )
        .one_or_none()
    )
    if pos is None:
        # If positions are not synced/available, do not assume the position is
        # closed; keep monitoring (restart-safe, avoids false MANUAL exits).
        return False
    else:
        if (mrp.side or "").strip().upper() == "BUY":
            qty = float(pos.qty or 0.0)
            closed = qty <= 0.0
            if not closed:
                mrp.qty = float(qty)
        else:
            qty = float(pos.qty or 0.0)
            closed = qty >= 0.0
            if not closed:
                mrp.qty = float(abs(qty))
    if not closed:
        return False
    mrp.status = "EXITED"
    mrp.exit_reason = mrp.exit_reason or "MANUAL"
    db.add(mrp)
    return True


def _create_exit_order(
    db: Session,
    *,
    mrp: ManagedRiskPosition,
    exit_reason: str,
) -> Order:
    side = (mrp.side or "").strip().upper()
    exit_side = "SELL" if side == "BUY" else "BUY"
    exec_target = (
        getattr(mrp, "execution_target", None) or "LIVE"
    ).strip().upper() or "LIVE"
    order = Order(
        user_id=mrp.user_id,
        broker_name=mrp.broker_name,
        alert_id=None,
        strategy_id=None,
        portfolio_group_id=None,
        symbol=mrp.symbol,
        exchange=mrp.exchange,
        side=exit_side,
        qty=float(mrp.qty),
        price=None,
        trigger_price=None,
        trigger_percent=None,
        order_type="MARKET",
        product=mrp.product,
        gtt=False,
        synthetic_gtt=False,
        status="WAITING",
        mode="AUTO",
        execution_target=exec_target,
        simulated=False,
        error_message=None,
        risk_spec_json=None,
        is_exit=True,
    )
    db.add(order)
    db.flush()
    mrp.exit_order_id = int(order.id)
    mrp.exit_reason = str(exit_reason or "").strip().upper() or "SL"
    db.add(mrp)
    db.flush()
    record_system_event(
        db,
        level="INFO",
        category="risk",
        message="Managed risk exit order created",
        correlation_id="managed-risk",
        details={
            "managed_risk_id": mrp.id,
            "exit_order_id": order.id,
            "exit_reason": mrp.exit_reason,
            "symbol": mrp.symbol,
            "side": order.side,
            "qty": order.qty,
        },
    )
    return order


def process_managed_risk_once() -> int:
    settings = get_settings()
    if not bool(getattr(settings, "managed_risk_enabled", True)):
        return 0
    if not is_market_open_now():
        return 0

    max_per_cycle = int(getattr(settings, "managed_risk_max_per_cycle", 200) or 200)

    from app.api.orders import execute_order_internal

    processed = 0
    now = _now_utc()
    with SessionLocal() as db:
        rows: list[ManagedRiskPosition] = (
            db.query(ManagedRiskPosition)
            .filter(ManagedRiskPosition.status.in_(["ACTIVE", "EXITING"]))
            .order_by(ManagedRiskPosition.updated_at.asc())
            .limit(max_per_cycle)
            .all()
        )
        if not rows:
            return 0

        for mrp in rows:
            # If we have an exit order already, reconcile its outcome and/or
            # ensure it's submitted (idempotent to restarts).
            if mrp.exit_order_id is not None:
                exit_order = db.get(Order, int(mrp.exit_order_id))
                if exit_order is not None and exit_order.status == "EXECUTED":
                    if _mark_exit_executed(db, exit_order_id=int(exit_order.id)):
                        db.commit()
                    processed += 1
                    continue

            if mrp.status == "EXITING" and mrp.exit_order_id is None:
                try:
                    exit_order = _create_exit_order(
                        db,
                        mrp=mrp,
                        exit_reason=mrp.exit_reason or "SL",
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                    processed += 1
                    continue
                try:
                    execute_order_internal(
                        int(exit_order.id),
                        db=db,
                        settings=settings,
                        correlation_id="managed-risk",
                    )
                    db.refresh(exit_order)
                except HTTPException as exc:
                    db.refresh(exit_order)
                    if exit_order.status == "WAITING":
                        exit_order.status = "FAILED"
                        detail = (
                            exc.detail
                            if isinstance(exc.detail, str)
                            else str(exc.detail)
                        )
                        exit_order.error_message = detail
                        db.add(exit_order)
                        db.commit()
                except Exception as exc:
                    db.refresh(exit_order)
                    if exit_order.status == "WAITING":
                        exit_order.status = "FAILED"
                        exit_order.error_message = str(exc)
                        db.add(exit_order)
                        db.commit()
                processed += 1
                continue

            if mrp.status != "ACTIVE":
                processed += 1
                continue

            if _mark_manual_exit_if_position_closed(db, mrp=mrp):
                db.commit()
                processed += 1
                continue

            if mrp.user_id is None:
                processed += 1
                continue

            try:
                ltp = _fetch_ltp(
                    db,
                    settings,
                    broker_name=mrp.broker_name,
                    user_id=int(mrp.user_id),
                    symbol=mrp.symbol,
                    exchange=mrp.exchange,
                )
            except Exception:
                processed += 1
                continue

            if mrp.stop_distance is None or float(mrp.stop_distance) <= 0:
                processed += 1
                continue

            trail_distance = float(mrp.trail_distance) if mrp.trail_distance else None
            activation_distance = (
                float(mrp.activation_distance) if mrp.activation_distance else None
            )
            trail_price = (
                float(mrp.trail_price) if mrp.trail_price is not None else None
            )
            update = _update_stop_state(
                side=mrp.side,
                entry_price=float(mrp.entry_price),
                stop_distance=float(mrp.stop_distance),
                trail_distance=trail_distance,
                activation_distance=activation_distance,
                best=float(mrp.best_favorable_price),
                trail=trail_price,
                is_trailing_active=bool(mrp.is_trailing_active),
                ltp=float(ltp),
            )

            mrp.best_favorable_price = float(update.best)
            mrp.trail_price = float(update.trail) if update.trail is not None else None
            mrp.is_trailing_active = bool(update.is_trailing_active)
            mrp.last_ltp = float(ltp)
            mrp.updated_at = now
            db.add(mrp)
            db.commit()

            if not update.triggered or not update.exit_reason:
                processed += 1
                continue

            # Compare-and-set to avoid duplicate exits.
            updated = (
                db.query(ManagedRiskPosition)
                .filter(
                    ManagedRiskPosition.id == mrp.id,
                    ManagedRiskPosition.status == "ACTIVE",
                    ManagedRiskPosition.exit_order_id.is_(None),
                )
                .update(
                    {
                        ManagedRiskPosition.status: "EXITING",
                        ManagedRiskPosition.exit_reason: update.exit_reason,
                        ManagedRiskPosition.updated_at: now,
                        ManagedRiskPosition.last_ltp: float(ltp),
                    },
                    synchronize_session=False,
                )
            )
            if not updated:
                db.commit()
                processed += 1
                continue
            db.commit()

            # Create and submit the exit order.
            with SessionLocal() as db2:
                mrp2 = db2.get(ManagedRiskPosition, int(mrp.id))
                if mrp2 is None:
                    processed += 1
                    continue
                try:
                    exit_order = _create_exit_order(
                        db2,
                        mrp=mrp2,
                        exit_reason=update.exit_reason,
                    )
                    db2.commit()
                except Exception:
                    db2.rollback()
                    processed += 1
                    continue
                try:
                    execute_order_internal(
                        int(exit_order.id),
                        db=db2,
                        settings=settings,
                        correlation_id="managed-risk",
                    )
                    db2.refresh(exit_order)
                except HTTPException as exc:
                    db2.refresh(exit_order)
                    if exit_order.status == "WAITING":
                        exit_order.status = "FAILED"
                        detail = (
                            exc.detail
                            if isinstance(exc.detail, str)
                            else str(exc.detail)
                        )
                        exit_order.error_message = detail
                        db2.add(exit_order)
                        db2.commit()
                except Exception as exc:
                    db2.refresh(exit_order)
                    if exit_order.status == "WAITING":
                        exit_order.status = "FAILED"
                        exit_order.error_message = str(exc)
                        db2.add(exit_order)
                        db2.commit()

            processed += 1

    return processed


def _managed_risk_loop() -> None:  # pragma: no cover - background loop
    settings = get_settings()
    poll = float(getattr(settings, "managed_risk_poll_interval_sec", 2.0) or 2.0)
    if poll <= 0:
        poll = 2.0
    while not _scheduler_stop_event.is_set():
        try:
            process_managed_risk_once()
        except Exception:
            pass
        _scheduler_stop_event.wait(timeout=poll)


def schedule_managed_risk() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    thread = Thread(
        target=_managed_risk_loop,
        name="managed-risk",
        daemon=True,
    )
    thread.start()


__all__ = [
    "process_managed_risk_once",
    "schedule_managed_risk",
    "ensure_managed_risk_for_executed_order",
    "mark_managed_risk_exit_executed",
    "_update_stop_state",
]
