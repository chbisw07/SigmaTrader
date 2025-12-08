from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models import Strategy, User
from app.schemas import StrategyCreate, StrategyRead, StrategyUpdate
from app.schemas.strategies import StrategyScope

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.get("/", response_model=List[StrategyRead])
def list_strategies(db: Session = Depends(get_db)) -> List[Strategy]:
    return db.query(Strategy).order_by(Strategy.id).all()


@router.get("/templates", response_model=List[StrategyRead])
def list_strategy_templates(
    symbol: Optional[str] = Query(
        default=None,
        description="Optional symbol to filter LOCAL templates for that symbol.",
        min_length=1,
    ),
    scope: Optional[StrategyScope] = Query(
        default=None,
        description="Optional scope filter (GLOBAL or LOCAL).",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[StrategyRead]:
    """List strategies that are usable as alert templates.

    This endpoint is intended for the indicator alert UI. It returns:
    - All GLOBAL strategies.
    - LOCAL strategies owned by the current user and, when a symbol is
      provided, scoped to that symbol.
    """

    query = db.query(Strategy).filter(
        (Strategy.scope.isnot(None)) | (Strategy.dsl_expression.isnot(None))
    )

    if scope is not None:
        query = query.filter(Strategy.scope == scope)

    # Owner scoping: include built-in templates (owner_id is NULL and
    # is_builtin=True) and user-owned templates.
    query = query.filter((Strategy.owner_id.is_(None)) | (Strategy.owner_id == user.id))

    if symbol:
        # For now, LOCAL strategies are symbol-agnostic; symbol-specific
        # scoping can be added later via an additional column. The filter is
        # kept here so the API surface is stable.
        pass

    strategies = query.order_by(Strategy.name).all()
    return strategies


@router.post(
    "/",
    response_model=StrategyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_strategy(
    payload: StrategyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
        execution_target=payload.execution_target,
        paper_poll_interval_sec=payload.paper_poll_interval_sec,
        enabled=payload.enabled,
        owner_id=user.id,
        scope=payload.scope,
        dsl_expression=payload.dsl_expression,
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
    user: User = Depends(get_current_user),
) -> Strategy:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Only allow editing of non-builtin strategies that belong to the user.
    if strategy.is_builtin and strategy.owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Built-in strategies cannot be modified.",
        )
    if strategy.owner_id is not None and strategy.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found.",
        )

    update_data = payload.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(strategy, field, value)

    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    return strategy


__all__ = ["router"]
