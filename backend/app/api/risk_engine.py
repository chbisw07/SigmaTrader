from __future__ import annotations

import json
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models import (
    AlertDecisionLog,
    DrawdownThreshold,
    RiskProfile,
    SymbolRiskCategory,
    User,
)
from app.schemas.risk_engine import (
    AlertDecisionLogRead,
    DrawdownThresholdRead,
    DrawdownThresholdUpsert,
    RiskProfileCreate,
    RiskProfileRead,
    RiskProfileUpdate,
    SymbolRiskCategoryRead,
    SymbolRiskCategoryUpsert,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _model_to_dict(obj: Any) -> dict[str, Any]:
    return {k: getattr(obj, k) for k in obj.__mapper__.columns.keys()}  # type: ignore[attr-defined]


@router.get("/risk-profiles", response_model=list[RiskProfileRead])
def list_risk_profiles(
    db: Session = Depends(get_db),
) -> list[RiskProfileRead]:
    rows = db.query(RiskProfile).order_by(RiskProfile.product, RiskProfile.name).all()
    return [RiskProfileRead(**_model_to_dict(r)) for r in rows]


@router.post("/risk-profiles", response_model=RiskProfileRead)
def create_risk_profile(
    payload: RiskProfileCreate,
    db: Session = Depends(get_db),
) -> RiskProfileRead:
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="name is required.",
        )
    row = db.query(RiskProfile).filter(RiskProfile.name == name).one_or_none()
    if row is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Risk profile name already exists.",
        )
    data = (
        payload.model_dump()  # type: ignore[attr-defined]
        if hasattr(payload, "model_dump")
        else payload.dict()  # type: ignore[call-arg]
    )
    row = RiskProfile(**data)  # type: ignore[arg-type]
    db.add(row)
    if bool(getattr(row, "is_default", False)):
        db.query(RiskProfile).filter(
            RiskProfile.product == row.product,
            RiskProfile.id != row.id,
        ).update({RiskProfile.is_default: False}, synchronize_session=False)
    db.commit()
    db.refresh(row)
    return RiskProfileRead(**_model_to_dict(row))


@router.put("/risk-profiles/{profile_id}", response_model=RiskProfileRead)
def update_risk_profile(
    profile_id: int,
    payload: RiskProfileUpdate,
    db: Session = Depends(get_db),
) -> RiskProfileRead:
    row = db.get(RiskProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    patch = (
        payload.model_dump(exclude_unset=True)  # type: ignore[attr-defined]
        if hasattr(payload, "model_dump")
        else payload.dict(exclude_unset=True)  # type: ignore[call-arg]
    )
    if "name" in patch and str(patch["name"] or "").strip() != row.name:
        existing = (
            db.query(RiskProfile)
            .filter(RiskProfile.name == str(patch["name"]).strip())
            .one_or_none()
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Risk profile name already exists.",
            )
    for k, v in patch.items():
        setattr(row, k, v)
    db.add(row)

    # Enforce at most one default profile per product.
    if bool(getattr(row, "is_default", False)):
        db.query(RiskProfile).filter(
            RiskProfile.product == row.product,
            RiskProfile.id != row.id,
        ).update({RiskProfile.is_default: False}, synchronize_session=False)

    db.commit()
    db.refresh(row)
    return RiskProfileRead(**_model_to_dict(row))


@router.delete("/risk-profiles/{profile_id}", response_model=dict[str, str])
def delete_risk_profile(
    profile_id: int,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = db.get(RiskProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    db.delete(row)
    db.commit()
    return {"status": "deleted"}


@router.get("/drawdown-thresholds", response_model=list[DrawdownThresholdRead])
def list_drawdown_thresholds(
    db: Session = Depends(get_db),
) -> list[DrawdownThresholdRead]:
    rows = (
        db.query(DrawdownThreshold)
        .order_by(DrawdownThreshold.product, DrawdownThreshold.category)
        .all()
    )
    return [DrawdownThresholdRead(**_model_to_dict(r)) for r in rows]


@router.put("/drawdown-thresholds", response_model=list[DrawdownThresholdRead])
def upsert_drawdown_thresholds(
    payload: list[DrawdownThresholdUpsert],
    db: Session = Depends(get_db),
) -> list[DrawdownThresholdRead]:
    out: list[DrawdownThreshold] = []
    for item in payload:
        row = (
            db.query(DrawdownThreshold)
            .filter(
                DrawdownThreshold.user_id.is_(None),
                DrawdownThreshold.product == item.product,
                DrawdownThreshold.category == item.category,
            )
            .one_or_none()
        )
        if row is None:
            row = DrawdownThreshold(
                user_id=None,
                product=item.product,
                category=item.category,
                caution_pct=float(item.caution_pct),
                defense_pct=float(item.defense_pct),
                hard_stop_pct=float(item.hard_stop_pct),
            )
            db.add(row)
        else:
            row.caution_pct = float(item.caution_pct)
            row.defense_pct = float(item.defense_pct)
            row.hard_stop_pct = float(item.hard_stop_pct)
            db.add(row)
        out.append(row)
    db.commit()
    for row in out:
        db.refresh(row)
    return [DrawdownThresholdRead(**_model_to_dict(r)) for r in out]


@router.get("/symbol-categories", response_model=list[SymbolRiskCategoryRead])
def list_symbol_categories(
    broker_name: str = Query(default="zerodha"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SymbolRiskCategoryRead]:
    broker = (broker_name or "zerodha").strip().lower() or "zerodha"
    query = db.query(SymbolRiskCategory).filter(SymbolRiskCategory.user_id == user.id)
    if broker != "*":
        query = query.filter(SymbolRiskCategory.broker_name.in_([broker, "*"]))
    rows = query.order_by(SymbolRiskCategory.exchange, SymbolRiskCategory.symbol).all()
    return [SymbolRiskCategoryRead(**_model_to_dict(r)) for r in rows]


@router.put("/symbol-categories", response_model=SymbolRiskCategoryRead)
def upsert_symbol_category(
    payload: SymbolRiskCategoryUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SymbolRiskCategoryRead:
    broker = (payload.broker_name or "zerodha").strip().lower() or "zerodha"
    symbol = payload.symbol.strip().upper()
    exchange = (payload.exchange or "NSE").strip().upper() or "NSE"
    row = (
        db.query(SymbolRiskCategory)
        .filter(
            SymbolRiskCategory.user_id == user.id,
            SymbolRiskCategory.broker_name == broker,
            SymbolRiskCategory.symbol == symbol,
            SymbolRiskCategory.exchange == exchange,
        )
        .one_or_none()
    )
    if row is None:
        row = SymbolRiskCategory(
            user_id=user.id,
            broker_name=broker,
            symbol=symbol,
            exchange=exchange,
            risk_category=payload.risk_category,
        )
        db.add(row)
    else:
        row.risk_category = payload.risk_category
        db.add(row)
    db.commit()
    db.refresh(row)
    return SymbolRiskCategoryRead(**_model_to_dict(row))


@router.put("/symbol-categories/bulk", response_model=list[SymbolRiskCategoryRead])
def bulk_upsert_symbol_categories(
    payload: list[SymbolRiskCategoryUpsert],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SymbolRiskCategoryRead]:
    rows: list[SymbolRiskCategory] = []
    for item in payload:
        broker = (item.broker_name or "zerodha").strip().lower() or "zerodha"
        symbol = item.symbol.strip().upper()
        exchange = (item.exchange or "NSE").strip().upper() or "NSE"
        row = (
            db.query(SymbolRiskCategory)
            .filter(
                SymbolRiskCategory.user_id == user.id,
                SymbolRiskCategory.broker_name == broker,
                SymbolRiskCategory.symbol == symbol,
                SymbolRiskCategory.exchange == exchange,
            )
            .one_or_none()
        )
        if row is None:
            row = SymbolRiskCategory(
                user_id=user.id,
                broker_name=broker,
                symbol=symbol,
                exchange=exchange,
                risk_category=item.risk_category,
            )
            db.add(row)
        else:
            row.risk_category = item.risk_category
            db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return [SymbolRiskCategoryRead(**_model_to_dict(r)) for r in rows]


@router.get("/decision-log", response_model=list[AlertDecisionLogRead])
def list_alert_decision_log(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AlertDecisionLogRead]:
    rows = (
        db.query(AlertDecisionLog)
        .filter((AlertDecisionLog.user_id == user.id) | (AlertDecisionLog.user_id.is_(None)))
        .order_by(AlertDecisionLog.created_at.desc())
        .limit(limit)
        .all()
    )
    # Keep JSON fields as raw strings (UI can render).
    return [AlertDecisionLogRead(**_model_to_dict(r)) for r in rows]


__all__ = ["router"]
