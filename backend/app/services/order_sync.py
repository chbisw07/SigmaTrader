from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.clients import ZerodhaClient
from app.core.config import get_settings
from app.models import Order
from app.services.managed_risk import (
    ensure_managed_risk_for_executed_order,
    mark_managed_risk_exit_executed,
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

    updated = 0

    q = db.query(Order).filter(
        Order.broker_name == "zerodha",
        (Order.broker_order_id.isnot(None)) | (Order.zerodha_order_id.isnot(None)),
    )
    if user_id is not None:
        q = q.filter((Order.user_id == user_id) | (Order.user_id.is_(None)))
    db_orders: List[Order] = q.all()
    for order in db_orders:
        lookup_id = order.broker_order_id or order.zerodha_order_id or ""
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
                ensure_managed_risk_for_executed_order(
                    db,
                    settings,
                    order=order,
                    filled_qty=float(filled_qty or 0.0),
                    avg_price=avg_price,
                )
            except Exception:
                pass
            try:
                mark_managed_risk_exit_executed(db, exit_order_id=int(order.id))
            except Exception:
                pass

        db.add(order)
        updated += 1

    if updated:
        db.commit()

    return updated


__all__ = ["sync_order_statuses"]
