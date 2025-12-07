from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import RiskSettings
from app.pydantic_compat import model_to_dict
from app.schemas import (
    RiskScope,
    RiskSettingsCreate,
    RiskSettingsRead,
    RiskSettingsUpdate,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.get("/", response_model=List[RiskSettingsRead])
def list_risk_settings(
    scope: Optional[RiskScope] = Query(None),
    strategy_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
) -> List[RiskSettings]:
    query = db.query(RiskSettings)
    if scope is not None:
        query = query.filter(RiskSettings.scope == scope)
    if strategy_id is not None:
        query = query.filter(RiskSettings.strategy_id == strategy_id)
    return query.order_by(RiskSettings.id).all()


@router.post(
    "/",
    response_model=RiskSettingsRead,
    status_code=status.HTTP_201_CREATED,
)
def create_risk_settings(
    payload: RiskSettingsCreate,
    db: Session = Depends(get_db),
) -> RiskSettings:
    existing = (
        db.query(RiskSettings)
        .filter(
            RiskSettings.scope == payload.scope,
            RiskSettings.strategy_id == payload.strategy_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Risk settings for this scope/strategy already exist.",
        )

    entity = RiskSettings(**model_to_dict(payload))
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


@router.get("/{risk_id}", response_model=RiskSettingsRead)
def get_risk_settings(
    risk_id: int,
    db: Session = Depends(get_db),
) -> RiskSettings:
    entity = db.get(RiskSettings, risk_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return entity


@router.put("/{risk_id}", response_model=RiskSettingsRead)
def update_risk_settings(
    risk_id: int,
    payload: RiskSettingsUpdate,
    db: Session = Depends(get_db),
) -> RiskSettings:
    entity = db.get(RiskSettings, risk_id)
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    update_data = model_to_dict(payload, exclude_unset=True)

    if "scope" in update_data or "strategy_id" in update_data:
        scope = update_data.get("scope", entity.scope)
        strategy_id = update_data.get("strategy_id", entity.strategy_id)
        existing = (
            db.query(RiskSettings)
            .filter(
                RiskSettings.id != risk_id,
                RiskSettings.scope == scope,
                RiskSettings.strategy_id == strategy_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Risk settings for this scope/strategy already exist.",
            )

    for field, value in update_data.items():
        setattr(entity, field, value)

    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


__all__ = ["router"]
