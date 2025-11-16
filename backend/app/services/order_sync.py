from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.clients import ZerodhaClient
from app.models import Order


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


def sync_order_statuses(db: Session, client: ZerodhaClient) -> int:
    """Synchronize order statuses with Zerodha using the order book.

    This function:
    - Fetches the full Zerodha order book via `client.list_orders()`.
    - Matches entries by `zerodha_order_id` against local `Order` rows.
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

    db_orders: List[Order] = (
        db.query(Order).filter(Order.zerodha_order_id.isnot(None)).all()
    )
    for order in db_orders:
        z_entry = by_id.get(order.zerodha_order_id or "")
        if not z_entry:
            continue

        z_status_raw = z_entry.get("status")
        if not isinstance(z_status_raw, str):
            continue

        new_status = _map_zerodha_status(z_status_raw)
        if new_status is None or new_status == order.status:
            continue

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

        db.add(order)
        updated += 1

    if updated:
        db.commit()

    return updated


__all__ = ["sync_order_statuses"]
