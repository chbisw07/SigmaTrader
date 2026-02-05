from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict
from app.schemas.holdings_exit import HoldingsExitConfigUpdate
from app.schemas.risk_engine import (
    DrawdownThresholdUpsert,
    RiskProfileCreate,
    SymbolRiskCategoryUpsert,
)
from app.schemas.risk_unified import RiskSourceOverrideUpsert, UnifiedRiskGlobalUpdate


class RiskSettingsBundleV1(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    exported_at: datetime | None = None
    exported_by: str | None = None

    warnings: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)

    global_settings: UnifiedRiskGlobalUpdate
    risk_profiles: list[RiskProfileCreate]
    drawdown_thresholds: list[DrawdownThresholdUpsert]
    source_overrides: list[RiskSourceOverrideUpsert]

    # Symbol categories are user-scoped in the UI (plus optional app-wide defaults).
    symbol_categories_global: list[SymbolRiskCategoryUpsert] = Field(default_factory=list)
    symbol_categories_user: list[SymbolRiskCategoryUpsert] = Field(default_factory=list)

    holdings_exit_config: HoldingsExitConfigUpdate

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")


class RiskSettingsImportResult(BaseModel):
    ok: bool = True
    imported_at: datetime
    counts: dict[str, int] = Field(default_factory=dict)

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="forbid")


__all__ = ["RiskSettingsBundleV1", "RiskSettingsImportResult"]
