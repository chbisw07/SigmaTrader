from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.risk_policy import RiskPolicy
from app.services.risk_policy_store import (
    default_risk_policy,
    get_risk_policy,
    reset_risk_policy,
    set_risk_policy,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class RiskPolicyRead(BaseModel):
    policy: RiskPolicy
    source: str  # db|default


@router.get("", response_model=RiskPolicyRead)
def read_risk_policy(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RiskPolicyRead:
    policy, source = get_risk_policy(db, settings)
    return RiskPolicyRead(policy=policy, source=source)


@router.get("/defaults", response_model=RiskPolicy)
def read_default_risk_policy() -> RiskPolicy:
    return default_risk_policy()


@router.put("", response_model=RiskPolicy)
def update_risk_policy(
    payload: RiskPolicy,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RiskPolicy:
    return set_risk_policy(db, settings, payload)


@router.post("/reset", response_model=RiskPolicy)
def reset_risk_policy_to_defaults(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RiskPolicy:
    return reset_risk_policy(db, settings)


__all__ = ["router"]
