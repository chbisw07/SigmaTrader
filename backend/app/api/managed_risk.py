from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import get_settings
from app.db.session import get_db
from app.models import ManagedRiskPosition, Order, User
from app.schemas.managed_risk import ManagedRiskPositionRead, RiskSpec
from app.services.managed_risk import (
    _create_exit_order,
    _distance_from_entry,
    _split_symbol_exchange,
    _update_stop_state,
)

router = APIRouter()


def _current_stop(mrp: ManagedRiskPosition) -> float | None:
    if mrp.stop_distance is None or mrp.entry_price is None:
        return None
    side = (mrp.side or "").strip().upper()
    base = (
        float(mrp.entry_price) - float(mrp.stop_distance)
        if side == "BUY"
        else float(mrp.entry_price) + float(mrp.stop_distance)
    )
    if mrp.is_trailing_active and mrp.trail_price is not None:
        return float(mrp.trail_price)
    return float(base)


def _parse_statuses(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def _exit_status_map(
    db: Session, positions: list[ManagedRiskPosition]
) -> dict[int, str]:
    exit_ids = [p.exit_order_id for p in positions if p.exit_order_id is not None]
    if not exit_ids:
        return {}
    rows = (
        db.query(Order.id, Order.status).filter(Order.id.in_(exit_ids)).all()
    )
    return {int(r[0]): str(r[1]) for r in rows if r[0] is not None}


def _to_read(
    db: Session,
    mrp: ManagedRiskPosition,
    exit_statuses: dict[int, str] | None = None,
) -> ManagedRiskPositionRead:
    spec = RiskSpec.from_json(getattr(mrp, "risk_spec_json", None))
    exit_status = None
    if mrp.exit_order_id is not None:
        if exit_statuses is not None:
            exit_status = exit_statuses.get(int(mrp.exit_order_id))
        else:
            order = db.get(Order, int(mrp.exit_order_id))
            if order is not None:
                exit_status = order.status
    return ManagedRiskPositionRead(
        id=mrp.id,
        user_id=mrp.user_id,
        entry_order_id=mrp.entry_order_id,
        exit_order_id=mrp.exit_order_id,
        exit_order_status=exit_status,
        broker_name=mrp.broker_name,
        symbol=mrp.symbol,
        exchange=mrp.exchange,
        product=mrp.product,
        side=mrp.side,
        qty=mrp.qty,
        execution_target=mrp.execution_target,
        entry_price=mrp.entry_price,
        stop_distance=mrp.stop_distance,
        trail_distance=mrp.trail_distance,
        activation_distance=mrp.activation_distance,
        current_stop=_current_stop(mrp),
        best_favorable_price=mrp.best_favorable_price,
        trail_price=mrp.trail_price,
        is_trailing_active=mrp.is_trailing_active,
        last_ltp=mrp.last_ltp,
        status=mrp.status,
        exit_reason=mrp.exit_reason,
        created_at=mrp.created_at,
        updated_at=mrp.updated_at,
        risk_spec=spec,
    )


def _create_and_execute_exit(
    db: Session,
    *,
    mrp: ManagedRiskPosition,
    reason: str,
) -> None:
    if mrp.exit_order_id is not None:
        return
    from app.api.orders import execute_order_internal

    settings = get_settings()
    exit_order = _create_exit_order(db, mrp=mrp, exit_reason=reason)
    db.commit()
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
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
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


@router.get("/positions", response_model=List[ManagedRiskPositionRead])
def list_managed_risk_positions(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
    status: Optional[str] = Query(None),
    broker_name: Optional[str] = Query(None),
    include_exited: bool = Query(False),
) -> List[ManagedRiskPositionRead]:
    query = db.query(ManagedRiskPosition)
    if user is not None:
        query = query.filter(
            (ManagedRiskPosition.user_id == user.id)
            | (ManagedRiskPosition.user_id.is_(None)),
        )
    statuses = _parse_statuses(status)
    if statuses:
        query = query.filter(ManagedRiskPosition.status.in_(statuses))
    elif not include_exited:
        query = query.filter(
            ManagedRiskPosition.status.in_(["ACTIVE", "EXITING", "PAUSED"])
        )

    if broker_name:
        query = query.filter(
            ManagedRiskPosition.broker_name == broker_name.strip().lower(),
        )

    positions = query.order_by(ManagedRiskPosition.updated_at.desc()).all()
    exit_statuses = _exit_status_map(db, positions)
    return [_to_read(db, mrp, exit_statuses=exit_statuses) for mrp in positions]


@router.post("/positions/{position_id}/exit", response_model=ManagedRiskPositionRead)
def exit_managed_risk_position(
    position_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> ManagedRiskPositionRead:
    mrp = db.get(ManagedRiskPosition, int(position_id))
    if mrp is None:
        raise HTTPException(status_code=404, detail="Managed risk position not found.")
    if user is not None and mrp.user_id not in {None, user.id}:
        raise HTTPException(status_code=403, detail="Forbidden.")
    if mrp.status == "EXITED":
        return _to_read(db, mrp)
    if mrp.exit_order_id is None:
        mrp.status = "EXITING"
        mrp.exit_reason = "MANUAL"
        db.add(mrp)
        db.commit()
    _create_and_execute_exit(db, mrp=mrp, reason=mrp.exit_reason or "MANUAL")
    db.refresh(mrp)
    return _to_read(db, mrp)


@router.post("/positions/{position_id}/pause", response_model=ManagedRiskPositionRead)
def pause_managed_risk_position(
    position_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> ManagedRiskPositionRead:
    mrp = db.get(ManagedRiskPosition, int(position_id))
    if mrp is None:
        raise HTTPException(status_code=404, detail="Managed risk position not found.")
    if user is not None and mrp.user_id not in {None, user.id}:
        raise HTTPException(status_code=403, detail="Forbidden.")
    if mrp.status == "EXITED":
        raise HTTPException(status_code=400, detail="Position already exited.")
    if mrp.status == "EXITING":
        raise HTTPException(status_code=400, detail="Exit already in progress.")
    if mrp.status != "PAUSED":
        mrp.status = "PAUSED"
        db.add(mrp)
        db.commit()
    return _to_read(db, mrp)


@router.post("/positions/{position_id}/resume", response_model=ManagedRiskPositionRead)
def resume_managed_risk_position(
    position_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> ManagedRiskPositionRead:
    mrp = db.get(ManagedRiskPosition, int(position_id))
    if mrp is None:
        raise HTTPException(status_code=404, detail="Managed risk position not found.")
    if user is not None and mrp.user_id not in {None, user.id}:
        raise HTTPException(status_code=403, detail="Forbidden.")
    if mrp.status == "EXITED":
        raise HTTPException(status_code=400, detail="Position already exited.")
    if mrp.status != "PAUSED":
        raise HTTPException(status_code=400, detail="Position is not paused.")
    mrp.status = "ACTIVE"
    db.add(mrp)
    db.commit()
    return _to_read(db, mrp)


@router.patch(
    "/positions/{position_id}/risk-spec", response_model=ManagedRiskPositionRead
)
def update_managed_risk_spec(
    position_id: int,
    payload: RiskSpec,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> ManagedRiskPositionRead:
    mrp = db.get(ManagedRiskPosition, int(position_id))
    if mrp is None:
        raise HTTPException(status_code=404, detail="Managed risk position not found.")
    if user is not None and mrp.user_id not in {None, user.id}:
        raise HTTPException(status_code=403, detail="Forbidden.")
    if mrp.status == "EXITED":
        raise HTTPException(status_code=400, detail="Position already exited.")
    if not payload.stop_loss.enabled:
        raise HTTPException(
            status_code=400,
            detail="stop_loss must be enabled for managed exits.",
        )

    if mrp.entry_price is None or float(mrp.entry_price) <= 0:
        raise HTTPException(
            status_code=400, detail="Entry price is missing for this position."
        )

    settings = get_settings()
    symbol, exchange = _split_symbol_exchange(mrp.symbol, mrp.exchange)
    stop_dist = _distance_from_entry(
        db,
        settings,
        entry_price=float(mrp.entry_price),
        symbol=symbol,
        exchange=exchange,
        spec=payload.stop_loss,
    )
    if stop_dist is None or float(stop_dist) <= 0:
        raise HTTPException(
            status_code=400, detail="Unable to compute stop distance."
        )
    trail_dist = None
    if payload.trailing_stop.enabled:
        trail_dist = _distance_from_entry(
            db,
            settings,
            entry_price=float(mrp.entry_price),
            symbol=symbol,
            exchange=exchange,
            spec=payload.trailing_stop,
        )
    act_dist = None
    if payload.trailing_activation.enabled:
        act_dist = _distance_from_entry(
            db,
            settings,
            entry_price=float(mrp.entry_price),
            symbol=symbol,
            exchange=exchange,
            spec=payload.trailing_activation,
        )

    best = float(mrp.best_favorable_price or mrp.entry_price)
    ltp = float(mrp.last_ltp or mrp.entry_price)
    update = _update_stop_state(
        side=mrp.side,
        entry_price=float(mrp.entry_price),
        stop_distance=float(stop_dist),
        trail_distance=float(trail_dist) if trail_dist else None,
        activation_distance=float(act_dist) if act_dist else None,
        best=best,
        trail=mrp.trail_price,
        is_trailing_active=bool(mrp.is_trailing_active),
        ltp=ltp,
    )

    mrp.risk_spec_json = payload.to_json()
    mrp.stop_distance = float(stop_dist)
    mrp.trail_distance = float(trail_dist) if trail_dist is not None else None
    mrp.activation_distance = float(act_dist) if act_dist is not None else None
    mrp.best_favorable_price = float(update.best)
    mrp.trail_price = float(update.trail) if update.trail is not None else None
    mrp.is_trailing_active = bool(update.is_trailing_active)
    db.add(mrp)
    db.commit()

    if (
        mrp.status == "ACTIVE"
        and update.triggered
        and mrp.exit_order_id is None
        and update.exit_reason
    ):
        mrp.status = "EXITING"
        mrp.exit_reason = update.exit_reason
        db.add(mrp)
        db.commit()
        _create_and_execute_exit(db, mrp=mrp, reason=update.exit_reason)
        db.refresh(mrp)

    return _to_read(db, mrp)


__all__ = ["router"]
