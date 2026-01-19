from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.pydantic_compat import PYDANTIC_V2, ConfigDict

OrderSourceBucket = Literal["TRADINGVIEW", "SIGMATRADER"]
ProductType = Literal["MIS", "CNC"]


class ManualEquitySettings(BaseModel):
    equity_mode: Literal["MANUAL"] = "MANUAL"
    manual_equity_inr: float = Field(default=1_000_000.0, gt=0)


class AccountRiskSettings(BaseModel):
    max_daily_loss_pct: float = Field(default=1.0, ge=0.0, le=100.0)
    max_daily_loss_abs: float | None = None
    max_open_positions: int = Field(default=6, ge=0)
    max_concurrent_symbols: int = Field(default=6, ge=0)
    max_exposure_pct: float = Field(default=60.0, ge=0.0, le=100.0)


class TradeRiskSettings(BaseModel):
    max_risk_per_trade_pct: float = Field(default=0.5, ge=0.0, le=100.0)
    hard_max_risk_pct: float = Field(default=0.75, ge=0.0, le=100.0)
    stop_loss_mandatory: bool = True
    stop_reference: Literal["ATR", "FIXED_PCT"] = "ATR"


class PositionSizingSettings(BaseModel):
    sizing_mode: Literal["FIXED_CAPITAL"] = "FIXED_CAPITAL"
    capital_per_trade: float = Field(default=20_000.0, ge=0.0)
    allow_scale_in: bool = False
    pyramiding: int = Field(default=1, ge=1)


class StopRulesSettings(BaseModel):
    atr_period: int = Field(default=14, ge=2, le=200)
    initial_stop_atr: float = Field(default=2.0, ge=0.0, le=50.0)
    fallback_stop_pct: float = Field(
        default=1.0,
        ge=0.0,
        le=100.0,
        description="Used when ATR data is unavailable and stop_reference=ATR.",
    )
    min_stop_distance_pct: float = Field(default=0.5, ge=0.0, le=100.0)
    max_stop_distance_pct: float = Field(default=3.0, ge=0.0, le=100.0)
    trailing_stop_enabled: bool = True
    trail_activation_atr: float = Field(default=2.5, ge=0.0, le=50.0)


class TradeFrequencySettings(BaseModel):
    max_trades_per_symbol_per_day: int = Field(default=2, ge=0)
    min_bars_between_trades: int = Field(default=10, ge=0)
    cooldown_after_loss_bars: int = Field(default=20, ge=0)


class LossControlsSettings(BaseModel):
    max_consecutive_losses: int = Field(default=3, ge=0)
    pause_after_loss_streak: bool = True
    pause_duration: str = "EOD"


class CorrelationRulesSettings(BaseModel):
    max_same_sector_positions: int = Field(default=2, ge=0)
    sector_correlation_limit: float = Field(default=0.7, ge=0.0, le=1.0)


class ExecutionSafetySettings(BaseModel):
    allow_mis: bool = False
    allow_cnc: bool = True
    allow_short_selling: bool = True
    max_order_value_pct: float = Field(default=2.5, ge=0.0, le=100.0)
    reject_if_margin_exceeded: bool = True


class EmergencyControlsSettings(BaseModel):
    # NOTE: Default is False; a True default would halt all executions.
    panic_stop: bool = False
    stop_all_trading_on_error: bool = True
    stop_on_unexpected_qty: bool = True


class ProductOverrides(BaseModel):
    allow: bool | None = None
    max_order_value_abs: float | None = Field(default=None, ge=0.0)
    max_quantity_per_order: float | None = Field(default=None, ge=0.0)
    capital_per_trade: float | None = Field(default=None, ge=0.0)
    max_risk_per_trade_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    hard_max_risk_pct: float | None = Field(default=None, ge=0.0, le=100.0)


class RiskPolicy(BaseModel):
    version: int = 1
    enabled: bool = False
    equity: ManualEquitySettings = ManualEquitySettings()
    account_risk: AccountRiskSettings = AccountRiskSettings()
    trade_risk: TradeRiskSettings = TradeRiskSettings()
    position_sizing: PositionSizingSettings = PositionSizingSettings()
    stop_rules: StopRulesSettings = StopRulesSettings()
    trade_frequency: TradeFrequencySettings = TradeFrequencySettings()
    loss_controls: LossControlsSettings = LossControlsSettings()
    correlation_rules: CorrelationRulesSettings = CorrelationRulesSettings()
    execution_safety: ExecutionSafetySettings = ExecutionSafetySettings()
    emergency_controls: EmergencyControlsSettings = EmergencyControlsSettings()
    overrides: dict[str, dict[str, ProductOverrides]] = Field(
        default_factory=lambda: {
            "TRADINGVIEW": {"MIS": ProductOverrides(), "CNC": ProductOverrides()},
            "SIGMATRADER": {"MIS": ProductOverrides(), "CNC": ProductOverrides()},
        }
    )

    def product_overrides(
        self, *, source: OrderSourceBucket, product: ProductType
    ) -> ProductOverrides:
        raw = (self.overrides or {}).get(source, {}).get(product)
        if isinstance(raw, ProductOverrides):
            return raw
        if isinstance(raw, dict):
            return ProductOverrides(**raw)
        return ProductOverrides()

    def to_dict(self) -> dict[str, Any]:
        if PYDANTIC_V2:
            return self.model_dump()
        return self.dict()  # pragma: no cover

    if PYDANTIC_V2:
        model_config = ConfigDict(extra="ignore")


__all__ = [
    "OrderSourceBucket",
    "ProductType",
    "ManualEquitySettings",
    "AccountRiskSettings",
    "TradeRiskSettings",
    "PositionSizingSettings",
    "StopRulesSettings",
    "TradeFrequencySettings",
    "LossControlsSettings",
    "CorrelationRulesSettings",
    "ExecutionSafetySettings",
    "EmergencyControlsSettings",
    "ProductOverrides",
    "RiskPolicy",
]
