from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.risk_compiled import CompiledRiskResponse, DrawdownState, RiskCategory, RiskProduct
from app.services.risk_compiler import compile_risk_policy

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.get("/compiled", response_model=CompiledRiskResponse)
def get_compiled_risk_policy(
    product: RiskProduct = Query(...),
    category: RiskCategory = Query(...),
    scenario: DrawdownState | None = Query(default=None),
    symbol: str | None = Query(default=None),
    strategy_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CompiledRiskResponse:
    compiled = compile_risk_policy(
        db,
        settings,
        user=None,
        product=product,
        category=category,
        scenario=scenario,
        symbol=symbol,
        strategy_id=strategy_id,
    )
    return CompiledRiskResponse(**compiled)


__all__ = ["router"]
