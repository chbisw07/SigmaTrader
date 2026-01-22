from __future__ import annotations

from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.holdings import HoldingGoalRead, HoldingGoalUpsert
from app.services.holdings_goals import delete_goal, list_goals, upsert_goal

router = APIRouter()


@router.get("/", response_model=List[HoldingGoalRead])
def list_holding_goals(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    broker_name: str | None = Query(None, min_length=1),
) -> List[HoldingGoalRead]:
    broker = broker_name.strip().lower() if broker_name else None
    return list_goals(db, user_id=user.id, broker_name=broker)


@router.put("/", response_model=HoldingGoalRead)
def upsert_holding_goal(
    payload: HoldingGoalUpsert,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> HoldingGoalRead:
    try:
        goal = upsert_goal(db, user_id=user.id, payload=payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return goal


@router.delete("/", response_model=dict)
def delete_holding_goal(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    symbol: str = Query(..., min_length=1),
    exchange: str | None = Query(None),
    broker_name: str | None = Query(None),
) -> dict:
    try:
        removed = delete_goal(
            db,
            user_id=user.id,
            symbol=symbol,
            exchange=exchange,
            broker_name=broker_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Holding goal not found.",
        )
    return {"deleted": True}
