from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Strategy
from app.schemas import StrategyCreate, StrategyRead, StrategyUpdate

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.get("/", response_model=List[StrategyRead])
def list_strategies(db: Session = Depends(get_db)) -> List[Strategy]:
    return db.query(Strategy).order_by(Strategy.id).all()


@router.post(
    "/",
    response_model=StrategyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_strategy(
    payload: StrategyCreate,
    db: Session = Depends(get_db),
) -> Strategy:
    existing = db.query(Strategy).filter(Strategy.name == payload.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strategy with this name already exists.",
        )

    strategy = Strategy(
        name=payload.name,
        description=payload.description,
        execution_mode=payload.execution_mode,
        enabled=payload.enabled,
    )
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


@router.get("/{strategy_id}", response_model=StrategyRead)
def get_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
) -> Strategy:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return strategy


@router.put("/{strategy_id}", response_model=StrategyRead)
def update_strategy(
    strategy_id: int,
    payload: StrategyUpdate,
    db: Session = Depends(get_db),
) -> Strategy:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    update_data = payload.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(strategy, field, value)

    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


__all__ = ["router"]
