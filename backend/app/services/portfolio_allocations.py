from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Group, GroupMember, Order


def _now_utc() -> datetime:
    return datetime.now(UTC)


def apply_portfolio_allocation_fill(
    db: Session,
    *,
    portfolio_group_id: int,
    symbol: str,
    exchange: str,
    side: str,
    filled_qty: float,
    avg_price: Optional[float],
) -> None:
    """Apply an executed order fill to portfolio allocation baseline fields.

    - For BUY: increases reference_qty and updates reference_price using weighted
      average.
    - For SELL: decreases reference_qty (floored at 0); reference_price is preserved.
    """

    if filled_qty <= 0:
        return

    sym_u = (symbol or "").strip().upper()
    exch_u = (exchange or "NSE").strip().upper()
    side_u = (side or "").strip().upper()
    if not sym_u or side_u not in {"BUY", "SELL"}:
        return

    group = db.get(Group, int(portfolio_group_id))
    if group is None or group.kind != "PORTFOLIO":
        return

    member = (
        db.query(GroupMember)
        .filter(
            GroupMember.group_id == group.id,
            func.upper(GroupMember.symbol) == sym_u,
            func.upper(func.coalesce(GroupMember.exchange, "NSE")) == exch_u,
        )
        .one_or_none()
    )

    if member is None:
        if side_u != "BUY":
            return
        member = GroupMember(
            group_id=group.id,
            symbol=sym_u,
            exchange=exch_u,
            target_weight=None,
            notes=None,
            reference_qty=0,
            reference_price=None,
        )
        db.add(member)
        db.flush()

    old_qty = int(member.reference_qty or 0)
    dq = int(round(float(filled_qty)))
    if dq <= 0:
        return

    if side_u == "SELL":
        member.reference_qty = max(0, old_qty - dq)
        group.updated_at = _now_utc()
        db.add(member)
        db.add(group)
        return

    # BUY
    new_qty = old_qty + dq
    member.reference_qty = new_qty

    fill_price = float(avg_price) if avg_price is not None else None
    old_price = float(member.reference_price) if member.reference_price else None
    if fill_price is not None and fill_price > 0:
        if old_price is not None and old_price > 0 and old_qty > 0:
            member.reference_price = (old_qty * old_price + dq * fill_price) / new_qty
        else:
            member.reference_price = fill_price
    # else: keep old reference_price

    group.updated_at = _now_utc()
    db.add(member)
    db.add(group)


def apply_portfolio_allocation_for_executed_order(
    db: Session,
    *,
    order: Order,
    filled_qty: float,
    avg_price: Optional[float],
) -> None:
    gid = getattr(order, "portfolio_group_id", None)
    if gid is None:
        return
    apply_portfolio_allocation_fill(
        db,
        portfolio_group_id=int(gid),
        symbol=order.symbol,
        exchange=(order.exchange or "NSE"),
        side=order.side,
        filled_qty=filled_qty,
        avg_price=avg_price,
    )


__all__ = [
    "apply_portfolio_allocation_fill",
    "apply_portfolio_allocation_for_executed_order",
]
