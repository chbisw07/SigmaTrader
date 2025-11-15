from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Order
from app.schemas.orders import OrderRead, OrderStatusUpdate

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.get("/queue", response_model=List[OrderRead])
def list_manual_queue(
    strategy_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> List[Order]:
    """Return orders currently in the manual WAITING queue."""

    query = db.query(Order).filter(
        Order.status == "WAITING",
        Order.mode == "MANUAL",
        Order.simulated.is_(False),
    )
    if strategy_id is not None:
        query = query.filter(Order.strategy_id == strategy_id)
    return query.order_by(Order.created_at).all()


@router.get("/{order_id}", response_model=OrderRead)
def get_order(order_id: int, db: Session = Depends(get_db)) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return order


@router.patch("/{order_id}/status", response_model=OrderRead)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
) -> Order:
    """Minimal status update endpoint for manual queue workflows.

    For now we only support transitions between WAITING and CANCELLED,
    which is enough to model a basic manual queue cancel operation
    without touching broker integration.
    """

    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if order.status not in {"WAITING", "CANCELLED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only WAITING/CANCELLED orders can be updated via this endpoint.",
        )

    target_status = payload.status
    if order.status == target_status:
        return order

    order.status = target_status
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


__all__ = ["router"]
