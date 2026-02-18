from __future__ import annotations

import hashlib
import json
from typing import List

from pydantic import BaseModel, Field


class RiskPolicyConfig(BaseModel):
    version: str = "v1"

    # Core limits
    max_per_trade_risk_pct: float = 1.0
    max_open_positions: int = 20

    # Symbol policy
    allow_symbols: List[str] = Field(default_factory=list)
    deny_symbols: List[str] = Field(default_factory=list)

    # Quote / sanity checks
    quote_max_age_sec: int = 10
    require_nonzero_quotes: bool = True

    def normalized(self) -> "RiskPolicyConfig":
        # Deterministic normalization for hashing and traceability.
        return RiskPolicyConfig(
            version=str(self.version),
            max_per_trade_risk_pct=float(self.max_per_trade_risk_pct),
            max_open_positions=int(self.max_open_positions),
            allow_symbols=sorted({str(s).upper() for s in self.allow_symbols if str(s).strip()}),
            deny_symbols=sorted({str(s).upper() for s in self.deny_symbols if str(s).strip()}),
            quote_max_age_sec=int(self.quote_max_age_sec),
            require_nonzero_quotes=bool(self.require_nonzero_quotes),
        )

    def content_hash(self) -> str:
        norm = self.normalized()
        raw = json.dumps(norm.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def default_policy() -> RiskPolicyConfig:
    return RiskPolicyConfig()


def load_policy_from_json(raw: str) -> RiskPolicyConfig:
    return RiskPolicyConfig.model_validate_json(raw)
