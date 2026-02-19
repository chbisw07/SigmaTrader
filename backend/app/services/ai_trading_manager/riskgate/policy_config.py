from __future__ import annotations

import hashlib
import json
from typing import List

from pydantic import BaseModel, Field


class RiskPolicyConfig(BaseModel):
    version: str = "v1"

    # Core limits
    max_per_trade_risk_pct: float = 1.0
    max_per_trade_notional_pct: float = 25.0
    max_open_positions: int = 20
    max_symbols_per_plan: int = 5
    max_total_exposure_pct: float = 100.0

    allowed_products: List[str] = Field(default_factory=lambda: ["CNC", "MIS"])
    allowed_order_types: List[str] = Field(default_factory=lambda: ["MARKET", "LIMIT", "SL", "SL-M"])

    # Symbol policy
    allow_symbols: List[str] = Field(default_factory=list)
    deny_symbols: List[str] = Field(default_factory=list)

    # Quote / sanity checks
    quote_max_age_sec: int = 10
    require_nonzero_quotes: bool = True
    max_limit_price_deviation_pct: float = 2.0

    def normalized(self) -> "RiskPolicyConfig":
        # Deterministic normalization for hashing and traceability.
        return RiskPolicyConfig(
            version=str(self.version),
            max_per_trade_risk_pct=float(self.max_per_trade_risk_pct),
            max_per_trade_notional_pct=float(self.max_per_trade_notional_pct),
            max_open_positions=int(self.max_open_positions),
            max_symbols_per_plan=int(self.max_symbols_per_plan),
            max_total_exposure_pct=float(self.max_total_exposure_pct),
            allowed_products=sorted({str(s).upper() for s in self.allowed_products if str(s).strip()}),
            allowed_order_types=sorted({str(s).upper() for s in self.allowed_order_types if str(s).strip()}),
            allow_symbols=sorted({str(s).upper() for s in self.allow_symbols if str(s).strip()}),
            deny_symbols=sorted({str(s).upper() for s in self.deny_symbols if str(s).strip()}),
            quote_max_age_sec=int(self.quote_max_age_sec),
            require_nonzero_quotes=bool(self.require_nonzero_quotes),
            max_limit_price_deviation_pct=float(self.max_limit_price_deviation_pct),
        )

    def content_hash(self) -> str:
        norm = self.normalized()
        raw = json.dumps(norm.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def default_policy() -> RiskPolicyConfig:
    return RiskPolicyConfig()


def load_policy_from_json(raw: str) -> RiskPolicyConfig:
    return RiskPolicyConfig.model_validate_json(raw)
