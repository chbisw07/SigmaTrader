from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.clients import AngelOneClient
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

def _map_angelone_status(status: str) -> Optional[str]:
    """Map SmartAPI order status strings to internal Order.status values."""

    s = (status or "").strip().upper()
    if not s:
        return None

    if s in {"COMPLETE", "COMPLETED", "TRADED", "EXECUTED"}:
        return "EXECUTED"
    if s in {"CANCELLED", "CANCELED"}:
        return "CANCELLED"
    if s == "REJECTED":
        return "REJECTED"
    if s in {
        "OPEN",
        "PENDING",
        "TRIGGER PENDING",
        "MODIFIED",
        "SUBMITTED",
        "CONFIRM",
    }:
        return "SENT"

    return None


def sync_order_statuses_angelone(
    db: Session,
    client: AngelOneClient,
    *,
    user_id: int | None = None,
) -> int:
    """Synchronize order statuses with AngelOne (SmartAPI) order book."""

    book: List[Dict[str, object]] = client.list_orders()
    by_id: Dict[str, Dict[str, object]] = {}
    for entry in book:
        if not isinstance(entry, dict):
            continue
        oid = entry.get("orderid") or entry.get("orderId") or entry.get("order_id")
        if oid is not None:
            by_id[str(oid)] = entry

    if not by_id:
        return 0

    q = db.query(Order).filter(
        Order.broker_name == "angelone",
        Order.broker_order_id.isnot(None),
    )
    if user_id is not None:
        q = q.filter((Order.user_id == user_id) | (Order.user_id.is_(None)))
    db_orders: List[Order] = q.all()

    updated = 0
    for order in db_orders:
        entry = by_id.get(order.broker_order_id or "")
        if not entry:
            continue

        status_raw = entry.get("status")
        if not isinstance(status_raw, str):
            continue

        new_status = _map_angelone_status(status_raw)
        if new_status is None or new_status == order.status:
            continue

        prev_status = order.status
        order.status = new_status
        if new_status == "REJECTED":
            msg = (
                entry.get("text")
                or entry.get("statusmessage")
                or entry.get("statusMessage")
                or entry.get("message")
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

            filled_qty = (
                _as_float(entry.get("filledshares"))
                or _as_float(entry.get("filledShares"))
                or _as_float(entry.get("filledqty"))
                or _as_float(entry.get("filledQty"))
                or _as_float(entry.get("quantity"))
            )
            if filled_qty is None:
                filled_qty = float(order.qty or 0.0)

            avg_price = (
                _as_float(entry.get("averageprice"))
                or _as_float(entry.get("averagePrice"))
                or _as_float(entry.get("avgprice"))
                or _as_float(entry.get("avgPrice"))
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

    if updated:
        db.commit()

    return updated


__all__ = ["sync_order_statuses_angelone"]
