from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.models import RiskGlobalConfig, RiskSourceOverride

RiskSourceBucket = Literal["TRADINGVIEW", "SIGMATRADER", "MANUAL"]
RiskProduct = Literal["CNC", "MIS"]


@dataclass(frozen=True)
class UnifiedRiskGlobal:
    enabled: bool
    manual_override_enabled: bool
    baseline_equity_inr: float


def get_or_create_risk_global_config(db: Session) -> RiskGlobalConfig:
    row = db.query(RiskGlobalConfig).filter(RiskGlobalConfig.singleton_key == "GLOBAL").one_or_none()
    if row is not None:
        return row
    row = RiskGlobalConfig(
        singleton_key="GLOBAL",
        enabled=True,
        manual_override_enabled=False,
        baseline_equity_inr=0.0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def read_unified_risk_global(db: Session) -> UnifiedRiskGlobal:
    row = get_or_create_risk_global_config(db)
    return UnifiedRiskGlobal(
        enabled=bool(row.enabled),
        manual_override_enabled=bool(row.manual_override_enabled),
        baseline_equity_inr=float(row.baseline_equity_inr or 0.0),
    )


def upsert_unified_risk_global(
    db: Session,
    *,
    enabled: bool,
    manual_override_enabled: bool,
    baseline_equity_inr: float,
) -> RiskGlobalConfig:
    row = get_or_create_risk_global_config(db)
    row.enabled = bool(enabled)
    row.manual_override_enabled = bool(manual_override_enabled)
    row.baseline_equity_inr = float(baseline_equity_inr or 0.0)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_source_override(
    db: Session,
    *,
    source_bucket: RiskSourceBucket,
    product: RiskProduct,
) -> RiskSourceOverride | None:
    if source_bucket == "MANUAL":
        return None
    return (
        db.query(RiskSourceOverride)
        .filter(
            RiskSourceOverride.source_bucket == source_bucket,
            RiskSourceOverride.product == product,
        )
        .one_or_none()
    )


__all__ = [
    "RiskProduct",
    "RiskSourceBucket",
    "UnifiedRiskGlobal",
    "get_or_create_risk_global_config",
    "read_unified_risk_global",
    "upsert_unified_risk_global",
    "get_source_override",
]

