from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.clients import ZerodhaClient
from app.core.config import get_settings
from app.models import Order
from app.services.managed_risk import (
    ensure_managed_risk_for_executed_order,
    mark_managed_risk_exit_executed,
    resolve_managed_risk_profile,
)
from app.services.portfolio_allocations import (
    apply_portfolio_allocation_for_executed_order,
)

def _map_zerodha_status(status: str) -> Optional[str]:
    """Map Zerodha order status strings to internal Order.status values."""

    s = status.upper()
    if s == "COMPLETE":
        return "EXECUTED"
    if s in {"CANCELLED", "CANCELLED AMO"}:
        return "CANCELLED"
    if s == "REJECTED":
        return "REJECTED"
    if s in {"OPEN", "OPEN PENDING", "TRIGGER PENDING", "AMO REQ RECEIVED"}:
        return "SENT"
    # For unknown statuses, keep the current internal status.
    return None


def sync_order_statuses(
    db: Session,
    client: ZerodhaClient,
    *,
    user_id: int | None = None,
) -> int:
    """Synchronize order statuses with Zerodha using the order book.

    This function:
    - Fetches the full Zerodha order book via `client.list_orders()`.
    - Matches entries by `broker_order_id` against local `Order` rows for
      broker_name='zerodha'.
    - Updates `Order.status` and, for rejected orders, `error_message`.

    Returns:
        The number of orders whose status was updated.
    """

    book: List[Dict[str, object]] = client.list_orders()
    by_id: Dict[str, Dict[str, object]] = {}
    for entry in book:
        order_id = entry.get("order_id")
        if order_id is not None:
            by_id[str(order_id)] = entry

    if not by_id:
        return 0

    def _as_str(v: object) -> str:
        return str(v or "").strip()

    def _as_upper(v: object) -> str:
        return _as_str(v).upper()

    def _as_int(v: object) -> int | None:
        if v is None:
            return None
        try:
            return int(float(v))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _parse_zerodha_ts(v: object) -> datetime | None:
        s = _as_str(v)
        if not s:
            return None
        # Zerodha order book timestamps are typically like: "2026-02-13 12:45:06"
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    def _split_symbol_and_exchange(*, symbol: str, exchange: str | None) -> tuple[str, str]:
        exch = (exchange or "NSE").strip().upper() or "NSE"
        ts = (symbol or "").strip()
        if ":" in ts:
            ex2, ts2 = ts.split(":", 1)
            if ex2.strip():
                exch = ex2.strip().upper()
            ts = ts2.strip()
        return exch, ts.strip().upper()

    def _fingerprint_from_local(order: Order) -> tuple[str, str, str, int, str, str, float | None, float | None]:
        exch, ts = _split_symbol_and_exchange(symbol=str(order.symbol or ""), exchange=order.exchange)
        side = _as_upper(getattr(order, "side", ""))
        qty = _as_int(getattr(order, "qty", None)) or 0
        product = _as_upper(getattr(order, "product", ""))
        otype = _as_upper(getattr(order, "order_type", ""))
        price = float(order.price) if getattr(order, "price", None) is not None else None
        trigger = (
            float(order.trigger_price)
            if getattr(order, "trigger_price", None) is not None
            else None
        )
        # Only include price/trigger if they are meaningful (reduces false mismatches for MARKET).
        if price is not None and price <= 0:
            price = None
        if trigger is not None and trigger <= 0:
            trigger = None
        return (exch, ts, side, qty, product, otype, price, trigger)

    def _fingerprint_from_broker(
        entry: Dict[str, object],
    ) -> tuple[str, str, str, int, str, str, float | None, float | None] | None:
        exch = _as_upper(entry.get("exchange"))
        ts = _as_upper(entry.get("tradingsymbol") or entry.get("trading_symbol"))
        if not exch or not ts:
            return None
        side = _as_upper(entry.get("transaction_type"))
        qty = _as_int(entry.get("quantity")) or 0
        product = _as_upper(entry.get("product"))
        otype = _as_upper(entry.get("order_type"))

        price_v = entry.get("price")
        trigger_v = entry.get("trigger_price")
        price: float | None = None
        trigger: float | None = None
        try:
            if price_v is not None and float(price_v) > 0:
                price = float(price_v)
        except Exception:
            price = None
        try:
            if trigger_v is not None and float(trigger_v) > 0:
                trigger = float(trigger_v)
        except Exception:
            trigger = None
        return (exch, ts, side, qty, product, otype, price, trigger)

    def _approx_created_to_broker_delta(order: Order, broker_ts: datetime) -> float | None:
        created_at = getattr(order, "created_at", None)
        if created_at is None:
            return None
        try:
            # `created_at` is stored as UTC; broker timestamps are typically in local exchange time.
            created_utc = created_at
            if isinstance(created_at, datetime) and created_at.tzinfo is not None:
                created_utc = created_at.astimezone(UTC)
            created_naive = created_utc.replace(tzinfo=None)  # type: ignore[union-attr]
            ist_offset = timedelta(hours=5, minutes=30)
            diff_utc = abs((broker_ts - created_naive).total_seconds())
            diff_ist = abs((broker_ts - (created_naive + ist_offset)).total_seconds())
            return min(diff_utc, diff_ist)
        except Exception:
            return None

    updated = 0

    q = db.query(Order).filter(
        Order.broker_name == "zerodha",
        (Order.broker_order_id.isnot(None)) | (Order.zerodha_order_id.isnot(None)),
    )
    if user_id is not None:
        q = q.filter((Order.user_id == user_id) | (Order.user_id.is_(None)))
    db_orders: List[Order] = q.all()
    linked_broker_ids: set[str] = set()
    for order in db_orders:
        lookup_id = order.broker_order_id or order.zerodha_order_id or ""
        if lookup_id:
            linked_broker_ids.add(str(lookup_id))
        z_entry = by_id.get(lookup_id)
        if not z_entry:
            continue

        z_status_raw = z_entry.get("status")
        if not isinstance(z_status_raw, str):
            continue

        new_status = _map_zerodha_status(z_status_raw)
        if new_status is None or new_status == order.status:
            continue

        prev_status = order.status
        order.status = new_status

        if new_status == "REJECTED":
            # Try to capture a useful rejection message if available.
            msg = (
                z_entry.get("status_message")
                or z_entry.get("status_message_short")
                or z_entry.get("message")
            )
            if isinstance(msg, str) and msg:
                order.error_message = msg

        if prev_status != "EXECUTED" and new_status == "EXECUTED":

            def _as_float(v: object) -> float | None:
                if v is None:
                    return None
                try:
                    return float(v)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    return None

            filled_qty = _as_float(z_entry.get("filled_quantity")) or _as_float(
                z_entry.get("quantity")
            )
            if filled_qty is None:
                filled_qty = float(order.qty or 0.0)

            avg_price = _as_float(z_entry.get("average_price")) or _as_float(
                z_entry.get("price")
            )
            if avg_price is None and order.price is not None:
                avg_price = float(order.price)

            apply_portfolio_allocation_for_executed_order(
                db,
                order=order,
                filled_qty=float(filled_qty or 0.0),
                avg_price=avg_price,
            )
            settings = get_settings()
            try:
                prof = resolve_managed_risk_profile(db, product=str(order.product or "MIS"))
                ensure_managed_risk_for_executed_order(
                    db,
                    settings,
                    order=order,
                    filled_qty=float(filled_qty or 0.0),
                    avg_price=avg_price,
                    risk_profile=prof,
                )
            except Exception:
                pass
            try:
                mark_managed_risk_exit_executed(db, exit_order_id=int(order.id))
            except Exception:
                pass

        db.add(order)
        updated += 1

    # Best-effort reconciliation:
    # If an order was requeued/executed outside of the normal flow (or a previous
    # response failed after broker placement), we may have local WAITING orders
    # without broker ids even though the broker shows a matching order. Try to
    # match conservatively by order "shape" and recent timestamps.
    now_utc = datetime.now(UTC)
    reconcile_cutoff = now_utc - timedelta(hours=12)

    q2 = (
        db.query(Order)
        .filter(
            Order.broker_name == "zerodha",
            Order.simulated.is_(False),
            Order.status == "WAITING",
            Order.broker_order_id.is_(None),
            Order.zerodha_order_id.is_(None),
            Order.created_at >= reconcile_cutoff,
        )
    )
    if user_id is not None:
        q2 = q2.filter((Order.user_id == user_id) | (Order.user_id.is_(None)))

    candidates_local: List[Order] = q2.all()
    if candidates_local:
        fp_to_entries: Dict[
            tuple[str, str, str, int, str, str, float | None, float | None],
            List[Dict[str, object]],
        ] = {}
        for entry in book:
            oid = entry.get("order_id")
            if oid is None:
                continue
            oid_s = str(oid)
            if oid_s in linked_broker_ids:
                continue
            fp = _fingerprint_from_broker(entry)
            if fp is None:
                continue
            fp_to_entries.setdefault(fp, []).append(entry)

        for order in candidates_local:
            fp = _fingerprint_from_local(order)
            entries = fp_to_entries.get(fp) or []
            if not entries:
                continue

            # Prefer a unique match; if multiple, use nearest timestamp within a tight window.
            chosen: Dict[str, object] | None = None
            if len(entries) == 1:
                chosen = entries[0]
            else:
                best: tuple[float, Dict[str, object]] | None = None
                for e in entries:
                    ts = _parse_zerodha_ts(e.get("order_timestamp") or e.get("exchange_timestamp"))
                    if ts is None:
                        continue
                    d = _approx_created_to_broker_delta(order, ts)
                    if d is None:
                        continue
                    if best is None or d < best[0]:
                        best = (d, e)
                # Only accept if reasonably close to avoid mismatching older duplicates.
                if best is not None and best[0] <= 30 * 60:
                    chosen = best[1]

            if chosen is None:
                continue

            broker_order_id = str(chosen.get("order_id") or "")
            if not broker_order_id or broker_order_id in linked_broker_ids:
                continue

            z_status_raw = chosen.get("status")
            if not isinstance(z_status_raw, str):
                continue

            prev_status = order.status
            mapped = _map_zerodha_status(z_status_raw) or order.status
            order.broker_order_id = broker_order_id
            order.zerodha_order_id = broker_order_id
            order.status = mapped
            if order.sent_at is None:
                order.sent_at = now_utc

            if mapped == "REJECTED":
                msg = (
                    chosen.get("status_message")
                    or chosen.get("status_message_short")
                    or chosen.get("message")
                )
                if isinstance(msg, str) and msg:
                    order.error_message = msg

            if prev_status != "EXECUTED" and mapped == "EXECUTED":

                def _as_float(v: object) -> float | None:
                    if v is None:
                        return None
                    try:
                        return float(v)  # type: ignore[arg-type]
                    except (TypeError, ValueError):
                        return None

                filled_qty = _as_float(chosen.get("filled_quantity")) or _as_float(
                    chosen.get("quantity")
                )
                if filled_qty is None:
                    filled_qty = float(order.qty or 0.0)

                avg_price = _as_float(chosen.get("average_price")) or _as_float(
                    chosen.get("price")
                )
                if avg_price is None and order.price is not None:
                    avg_price = float(order.price)

                apply_portfolio_allocation_for_executed_order(
                    db,
                    order=order,
                    filled_qty=float(filled_qty or 0.0),
                    avg_price=avg_price,
                )
                settings = get_settings()
                try:
                    prof = resolve_managed_risk_profile(
                        db, product=str(order.product or "MIS")
                    )
                    ensure_managed_risk_for_executed_order(
                        db,
                        settings,
                        order=order,
                        filled_qty=float(filled_qty or 0.0),
                        avg_price=avg_price,
                        risk_profile=prof,
                    )
                except Exception:
                    pass
                try:
                    mark_managed_risk_exit_executed(db, exit_order_id=int(order.id))
                except Exception:
                    pass

            linked_broker_ids.add(broker_order_id)
            db.add(order)
            updated += 1

    if updated:
        db.commit()

    return updated


__all__ = ["sync_order_statuses"]
