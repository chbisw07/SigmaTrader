from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.risk_unified import UnifiedRiskGlobalRead, UnifiedRiskGlobalUpdate
from app.services.risk_unified_store import read_unified_risk_global, upsert_unified_risk_global

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.get("/global", response_model=UnifiedRiskGlobalRead)
def read_unified_risk_global_settings(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),  # noqa: ARG001 - keep signature stable
) -> UnifiedRiskGlobalRead:
    g = read_unified_risk_global(db)
    # We expose updated_at via model row, but the dataclass doesn't include it.
    from app.models import RiskGlobalConfig

    row = db.query(RiskGlobalConfig).filter(RiskGlobalConfig.singleton_key == "GLOBAL").one_or_none()
    return UnifiedRiskGlobalRead(
        enabled=bool(g.enabled),
        manual_override_enabled=bool(g.manual_override_enabled),
        baseline_equity_inr=float(g.baseline_equity_inr),
        updated_at=(row.updated_at if row is not None else None),
    )


@router.put("/global", response_model=UnifiedRiskGlobalRead)
def update_unified_risk_global_settings(
    payload: UnifiedRiskGlobalUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),  # noqa: ARG001
) -> UnifiedRiskGlobalRead:
    row = upsert_unified_risk_global(
        db,
        enabled=bool(payload.enabled),
        manual_override_enabled=bool(payload.manual_override_enabled),
        baseline_equity_inr=float(payload.baseline_equity_inr or 0.0),
    )
    return UnifiedRiskGlobalRead(
        enabled=bool(row.enabled),
        manual_override_enabled=bool(row.manual_override_enabled),
        baseline_equity_inr=float(row.baseline_equity_inr or 0.0),
        updated_at=row.updated_at,
    )


__all__ = ["router"]

