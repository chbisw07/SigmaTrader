from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Event, Thread
from typing import Any

from sqlalchemy.orm import Session

from app.clients import ZerodhaClient
from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.db.session import SessionLocal
from app.holdings_exit.symbols import normalize_holding_symbol_exchange
from app.models import BrokerConnection, Order, HoldingExitSubscription
from app.services.broker_secrets import get_broker_secret
from app.services.holdings_exit_config import get_holdings_exit_config_with_source
from app.services.holdings_exit_store import utc_now, write_holding_exit_event

logger = logging.getLogger(__name__)

_scheduler_started = False
_scheduler_stop_event = Event()


@dataclass(frozen=True)
class HoldingSnapshot:
    exchange: str
    symbol: str
    qty: float
    avg_price: float | None


def _as_float(v: object, default: float | None = None) -> float | None:
    if v is None:
        return default
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _get_zerodha_client(db: Session, settings: Settings, *, user_id: int) -> ZerodhaClient:
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


def _build_holdings_map(raw: list[dict[str, Any]]) -> dict[tuple[str, str], HoldingSnapshot]:
    out: dict[tuple[str, str], HoldingSnapshot] = {}
    for entry in raw or []:
        if not isinstance(entry, dict):
            continue
        sym_raw = entry.get("tradingsymbol")
        exch_raw = entry.get("exchange") or "NSE"
        qty = _as_float(entry.get("quantity"), 0.0)
        avg = _as_float(entry.get("average_price"))
        if not isinstance(sym_raw, str) or not isinstance(exch_raw, str):
            continue
        sym, exch = normalize_holding_symbol_exchange(sym_raw, str(exch_raw))
        if not sym or not exch:
            continue
        out[(exch, sym)] = HoldingSnapshot(
            exchange=exch,
            symbol=sym,
            qty=float(qty or 0.0),
            avg_price=float(avg) if avg is not None else None,
        )
    return out


def _terminal_order_status(status: str) -> str:
    return str(status or "").strip().upper()


def _is_order_success_terminal(status_u: str) -> bool:
    return status_u in {"EXECUTED", "PARTIALLY_EXECUTED"}


def _is_order_failure_terminal(status_u: str) -> bool:
    return status_u in {"FAILED", "REJECTED", "REJECTED_RISK", "CANCELLED"}


def _compute_exit_qty(
    *,
    holdings_qty: float,
    size_mode: str,
    size_value: float,
    min_qty: int,
) -> int:
    hold = float(holdings_qty or 0.0)
    if hold <= 0:
        return 0

    mode = str(size_mode or "").strip().upper()
    sv = float(size_value or 0.0)

    desired = 0
    if mode == "ABS_QTY":
        desired = int(sv)
    elif mode == "PCT_OF_POSITION":
        desired = int((hold * sv) // 100.0)
    else:
        desired = 0

    if desired <= 0:
        desired = int(min_qty)

    desired = max(int(min_qty), int(desired))
    desired = min(int(desired), int(hold))
    return int(max(0, desired))


def _trigger_target_price(
    *,
    sub: HoldingExitSubscription,
    avg_buy: float | None,
) -> float | None:
    kind = str(sub.trigger_kind or "").strip().upper()
    tv = float(sub.trigger_value or 0.0)
    if kind == "TARGET_ABS_PRICE":
        return float(tv)
    if kind == "TARGET_PCT_FROM_AVG_BUY":
        if avg_buy is None or float(avg_buy) <= 0:
            return None
        return float(avg_buy) * (1.0 + float(tv) / 100.0)
    return None


def _schedule_next_eval(now: datetime, *, poll_sec: float) -> datetime:
    poll = float(poll_sec or 5.0)
    if poll <= 0:
        poll = 5.0
    return now + timedelta(seconds=poll)


def _reconcile_pending_orders(
    db: Session,
    *,
    settings: Settings,
    now: datetime,
    poll_sec: float,
) -> int:
    processed = 0
    subs = (
        db.query(HoldingExitSubscription)
        .filter(HoldingExitSubscription.pending_order_id.isnot(None))
        .order_by(HoldingExitSubscription.updated_at.asc())
        .limit(int(getattr(settings, "holdings_exit_max_per_cycle", 200) or 200))
        .all()
    )
    for sub in subs:
        order_id = int(sub.pending_order_id or 0)
        if order_id <= 0:
            continue
        order = db.get(Order, order_id)
        if order is None:
            sub.pending_order_id = None
            sub.status = "ERROR"
            sub.last_error = "Pending order record is missing."
            sub.updated_at = now
            sub.next_eval_at = _schedule_next_eval(now, poll_sec=poll_sec)
            db.add(sub)
            db.commit()
            write_holding_exit_event(
                db,
                subscription_id=sub.id,
                event_type="SUB_ERROR",
                details={"reason": "missing_order", "pending_order_id": order_id},
            )
            processed += 1
            continue

        status_u = _terminal_order_status(order.status)
        if _is_order_success_terminal(status_u):
            sub.pending_order_id = None
            sub.status = "COMPLETED"
            sub.last_error = None
            sub.updated_at = now
            sub.next_eval_at = None
            db.add(sub)
            db.commit()
            write_holding_exit_event(
                db,
                subscription_id=sub.id,
                event_type="SUB_COMPLETED",
                details={"order_id": int(order.id), "order_status": status_u},
            )
            processed += 1
            continue

        if _is_order_failure_terminal(status_u):
            sub.pending_order_id = None
            sub.status = "ERROR"
            sub.last_error = (
                f"Exit order ended with status={status_u}: {order.error_message}"
                if order.error_message
                else f"Exit order ended with status={status_u}."
            )
            sub.updated_at = now
            sub.next_eval_at = None
            db.add(sub)
            db.commit()
            write_holding_exit_event(
                db,
                subscription_id=sub.id,
                event_type="ORDER_FAILED",
                details={"order_id": int(order.id), "order_status": status_u},
            )
            processed += 1
            continue

        # Still pending (WAITING/SENDING/SENT/VALIDATED): keep watching.
        sub.next_eval_at = _schedule_next_eval(now, poll_sec=poll_sec)
        sub.updated_at = now
        db.add(sub)
        db.commit()
        processed += 1
    return processed


def _evaluate_active_subscriptions(
    db: Session,
    *,
    settings: Settings,
    now: datetime,
    poll_sec: float,
) -> int:
    processed = 0

    due = (
        db.query(HoldingExitSubscription)
        .filter(
            HoldingExitSubscription.status == "ACTIVE",
            HoldingExitSubscription.pending_order_id.is_(None),
            (
                (HoldingExitSubscription.next_eval_at.is_(None))
                | (HoldingExitSubscription.next_eval_at <= now)
            ),
            (
                (HoldingExitSubscription.cooldown_until.is_(None))
                | (HoldingExitSubscription.cooldown_until <= now)
            ),
        )
        .order_by(HoldingExitSubscription.updated_at.asc())
        .limit(int(getattr(settings, "holdings_exit_max_per_cycle", 200) or 200))
        .all()
    )
    if not due:
        return 0

    # Group by (broker_name, user_id) so we can fetch holdings/LTP in bulk.
    groups: dict[tuple[str, int], list[HoldingExitSubscription]] = {}
    for sub in due:
        if sub.user_id is None:
            sub.status = "ERROR"
            sub.last_error = "Subscription is missing user_id."
            sub.updated_at = now
            db.add(sub)
            db.commit()
            write_holding_exit_event(
                db,
                subscription_id=sub.id,
                event_type="SUB_ERROR",
                details={"reason": "missing_user_id"},
            )
            continue
        key = (str(sub.broker_name or "").strip().lower(), int(sub.user_id))
        groups.setdefault(key, []).append(sub)

    for (broker, user_id), subs in groups.items():
        if broker != "zerodha":
            for sub in subs:
                sub.status = "ERROR"
                sub.last_error = f"Unsupported broker: {broker}"
                sub.updated_at = now
                db.add(sub)
                db.commit()
                write_holding_exit_event(
                    db,
                    subscription_id=sub.id,
                    event_type="SUB_ERROR",
                    details={"reason": "unsupported_broker", "broker_name": broker},
                )
            continue

        try:
            client = _get_zerodha_client(db, settings, user_id=user_id)
        except Exception as exc:
            for sub in subs:
                sub.last_error = f"Broker unavailable: {exc}"
                sub.last_evaluated_at = now
                sub.next_eval_at = _schedule_next_eval(now, poll_sec=poll_sec)
                sub.updated_at = now
                db.add(sub)
                db.commit()
                write_holding_exit_event(
                    db,
                    subscription_id=sub.id,
                    event_type="EVAL_SKIPPED_BROKER_UNAVAILABLE",
                    details={"broker_name": broker, "error": str(exc)},
                )
                processed += 1
            continue

        raw_holdings = client.list_holdings()
        holdings_map = _build_holdings_map(raw_holdings)

        instruments: list[tuple[str, str]] = []
        for sub in subs:
            instruments.append(
                (
                    str(sub.exchange or "NSE").strip().upper(),
                    str(sub.symbol or "").strip().upper(),
                )
            )
        ltp_map = client.get_ltp_bulk(sorted(set(instruments)))

        for sub in subs:
            # MVP posture enforcement (should also be enforced in the API).
            if str(sub.product or "").strip().upper() != "CNC":
                sub.status = "ERROR"
                sub.last_error = "Only product=CNC is supported (MVP)."
                sub.updated_at = now
                db.add(sub)
                db.commit()
                write_holding_exit_event(
                    db,
                    subscription_id=sub.id,
                    event_type="SUB_ERROR",
                    details={"reason": "unsupported_product", "product": sub.product},
                )
                processed += 1
                continue
            if str(sub.dispatch_mode or "").strip().upper() != "MANUAL":
                sub.status = "ERROR"
                sub.last_error = "dispatch_mode=AUTO is not supported (MVP)."
                sub.updated_at = now
                db.add(sub)
                db.commit()
                write_holding_exit_event(
                    db,
                    subscription_id=sub.id,
                    event_type="SUB_ERROR",
                    details={"reason": "unsupported_dispatch_mode", "dispatch_mode": sub.dispatch_mode},
                )
                processed += 1
                continue

            sym_u, exch_u = normalize_holding_symbol_exchange(sub.symbol, sub.exchange)
            snap = holdings_map.get((exch_u, sym_u))
            if snap is None or float(snap.qty) <= 0:
                # Nothing left to sell; subscription naturally completes.
                sub.status = "COMPLETED"
                sub.pending_order_id = None
                sub.last_error = None
                sub.updated_at = now
                sub.next_eval_at = None
                db.add(sub)
                db.commit()
                write_holding_exit_event(
                    db,
                    subscription_id=sub.id,
                    event_type="SUB_COMPLETED",
                    details={"reason": "no_holdings"},
                )
                processed += 1
                continue

            px = ltp_map.get((exch_u, sym_u)) or {}
            ltp = _as_float(px.get("last_price"))
            prev_close = _as_float(px.get("prev_close"))
            target_price = _trigger_target_price(sub=sub, avg_buy=snap.avg_price)
            price_snapshot = {
                "exchange": exch_u,
                "symbol": sym_u,
                "ltp": ltp,
                "prev_close": prev_close,
                "avg_buy": snap.avg_price,
                "target_price": target_price,
            }

            sub.last_evaluated_at = now
            sub.updated_at = now

            if ltp is None or float(ltp) <= 0:
                sub.last_error = "Missing quote."
                sub.next_eval_at = _schedule_next_eval(now, poll_sec=poll_sec)
                db.add(sub)
                db.commit()
                write_holding_exit_event(
                    db,
                    subscription_id=sub.id,
                    event_type="EVAL_SKIPPED_MISSING_QUOTE",
                    details={"reason": "missing_quote"},
                    price_snapshot=price_snapshot,
                )
                processed += 1
                continue

            write_holding_exit_event(
                db,
                subscription_id=sub.id,
                event_type="EVAL",
                details={"status": "ACTIVE"},
                price_snapshot=price_snapshot,
            )

            if target_price is None or float(target_price) <= 0:
                sub.status = "ERROR"
                sub.last_error = "Cannot compute target price (missing avg buy?)."
                sub.next_eval_at = None
                db.add(sub)
                db.commit()
                write_holding_exit_event(
                    db,
                    subscription_id=sub.id,
                    event_type="SUB_ERROR",
                    details={"reason": "missing_target_price"},
                    price_snapshot=price_snapshot,
                )
                processed += 1
                continue

            triggered = float(ltp) >= float(target_price)
            if not triggered:
                sub.last_error = None
                sub.next_eval_at = _schedule_next_eval(now, poll_sec=poll_sec)
                db.add(sub)
                db.commit()
                processed += 1
                continue

            # Trigger met: create a WAITING manual exit order.
            qty = _compute_exit_qty(
                holdings_qty=snap.qty,
                size_mode=sub.size_mode,
                size_value=sub.size_value,
                min_qty=int(sub.min_qty),
            )
            if qty <= 0:
                sub.status = "ERROR"
                sub.last_error = "Computed exit quantity is 0."
                sub.next_eval_at = None
                db.add(sub)
                db.commit()
                write_holding_exit_event(
                    db,
                    subscription_id=sub.id,
                    event_type="SUB_ERROR",
                    details={"reason": "qty_zero"},
                    price_snapshot=price_snapshot,
                )
                processed += 1
                continue

            # Make order identity discoverable in the UI.
            client_order_id = f"HEXIT:{sub.id}:{int(now.timestamp() * 1000)}"

            order = Order(
                user_id=sub.user_id,
                alert_id=None,
                strategy_id=None,
                portfolio_group_id=None,
                client_order_id=client_order_id,
                symbol=sym_u,
                exchange=exch_u,
                side="SELL",
                qty=float(qty),
                price=None,
                order_type=str(sub.order_type or "MARKET").strip().upper(),
                product="CNC",
                gtt=False,
                synthetic_gtt=False,
                status="WAITING",
                mode="MANUAL",
                execution_target=str(sub.execution_target or "LIVE").strip().upper(),
                broker_name=broker,
                broker_order_id=None,
                zerodha_order_id=None,
                broker_account_id=None,
                error_message="Holdings exit automation (queued).",
                simulated=False,
                risk_spec_json=None,
                is_exit=True,
                created_at=now,
                updated_at=now,
            )
            sub.pending_order_id = None  # set after flush
            sub.status = "ORDER_CREATED"
            sub.last_triggered_at = now
            sub.cooldown_until = now + timedelta(seconds=int(sub.cooldown_seconds or 0))
            sub.next_eval_at = _schedule_next_eval(now, poll_sec=poll_sec)
            sub.last_error = None

            db.add(order)
            db.add(sub)
            db.flush()
            sub.pending_order_id = int(order.id)
            db.add(sub)
            db.commit()
            db.refresh(order)
            db.refresh(sub)

            write_holding_exit_event(
                db,
                subscription_id=sub.id,
                event_type="TRIGGER_MET",
                details={
                    "order_id": int(order.id),
                    "qty": float(qty),
                    "client_order_id": client_order_id,
                },
                price_snapshot=price_snapshot,
            )
            write_holding_exit_event(
                db,
                subscription_id=sub.id,
                event_type="ORDER_CREATED",
                details={"order_id": int(order.id), "status": order.status},
                price_snapshot=price_snapshot,
            )
            processed += 1

    return processed


def process_holdings_exit_once() -> int:
    settings = get_settings()

    now = utc_now()
    poll_sec = float(getattr(settings, "holdings_exit_poll_interval_sec", 5.0) or 5.0)

    processed = 0
    with SessionLocal() as db:
        # Always reconcile existing pending orders so the UI reflects terminal outcomes,
        # even if the feature is currently disabled (no new triggers while disabled).
        processed += _reconcile_pending_orders(
            db,
            settings=settings,
            now=now,
            poll_sec=poll_sec,
        )
        cfg, _source = get_holdings_exit_config_with_source(db, settings)
        if bool(cfg.enabled):
            processed += _evaluate_active_subscriptions(
                db,
                settings=settings,
                now=now,
                poll_sec=poll_sec,
            )
    return processed


def _holdings_exit_loop() -> None:  # pragma: no cover - background loop
    settings = get_settings()
    poll = float(getattr(settings, "holdings_exit_poll_interval_sec", 5.0) or 5.0)
    if poll <= 0:
        poll = 5.0
    while not _scheduler_stop_event.is_set():
        try:
            process_holdings_exit_once()
        except Exception:
            pass
        _scheduler_stop_event.wait(timeout=poll)


def schedule_holdings_exit() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        return
    _scheduler_started = True
    thread = Thread(
        target=_holdings_exit_loop,
        name="holdings-exit",
        daemon=True,
    )
    thread.start()


__all__ = ["process_holdings_exit_once", "schedule_holdings_exit"]
