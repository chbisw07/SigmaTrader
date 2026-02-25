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
    no_trade_rules: str


def get_or_create_risk_global_config(db: Session) -> RiskGlobalConfig:
    row = db.query(RiskGlobalConfig).filter(RiskGlobalConfig.singleton_key == "GLOBAL").one_or_none()
    if row is not None:
        return row
    row = RiskGlobalConfig(
        singleton_key="GLOBAL",
        enabled=True,
        manual_override_enabled=False,
        baseline_equity_inr=1_000_000.0,
        no_trade_rules="",
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
        no_trade_rules=str(getattr(row, "no_trade_rules", "") or ""),
    )


def upsert_unified_risk_global(
    db: Session,
    *,
    enabled: bool,
    manual_override_enabled: bool,
    baseline_equity_inr: float,
    no_trade_rules: str | None = None,
) -> RiskGlobalConfig:
    row = get_or_create_risk_global_config(db)
    row.enabled = bool(enabled)
    row.manual_override_enabled = bool(manual_override_enabled)
    row.baseline_equity_inr = float(baseline_equity_inr or 0.0)
    if no_trade_rules is not None:
        row.no_trade_rules = str(no_trade_rules)
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


def list_source_overrides(db: Session) -> list[RiskSourceOverride]:
    return (
        db.query(RiskSourceOverride)
        .order_by(RiskSourceOverride.source_bucket.asc(), RiskSourceOverride.product.asc())
        .all()
    )


def upsert_source_override(
    db: Session,
    *,
    source_bucket: Literal["TRADINGVIEW", "SIGMATRADER"],
    product: RiskProduct,
    allow_product: bool | None = None,
    allow_short_selling: bool | None = None,
    max_order_value_pct: float | None = None,
    max_order_value_abs: float | None = None,
    max_quantity_per_order: float | None = None,
    capital_per_trade: float | None = None,
    max_positions: int | None = None,
    max_exposure_pct: float | None = None,
    risk_per_trade_pct: float | None = None,
    hard_risk_pct: float | None = None,
    stop_loss_mandatory: bool | None = None,
    stop_reference: str | None = None,
    atr_period: int | None = None,
    atr_mult_initial_stop: float | None = None,
    fallback_stop_pct: float | None = None,
    min_stop_distance_pct: float | None = None,
    max_stop_distance_pct: float | None = None,
    daily_loss_pct: float | None = None,
    hard_daily_loss_pct: float | None = None,
    max_consecutive_losses: int | None = None,
    entry_cutoff_time: str | None = None,
    force_squareoff_time: str | None = None,
    max_trades_per_day: int | None = None,
    max_trades_per_symbol_per_day: int | None = None,
    min_bars_between_trades: int | None = None,
    cooldown_after_loss_bars: int | None = None,
    slippage_guard_bps: float | None = None,
    gap_guard_pct: float | None = None,
    order_type_policy: str | None = None,
) -> RiskSourceOverride:
    row = (
        db.query(RiskSourceOverride)
        .filter(
            RiskSourceOverride.source_bucket == source_bucket,
            RiskSourceOverride.product == product,
        )
        .one_or_none()
    )
    if row is None:
        row = RiskSourceOverride(source_bucket=source_bucket, product=product)
        db.add(row)

    row.allow_product = allow_product
    row.allow_short_selling = allow_short_selling
    row.max_order_value_pct = max_order_value_pct
    row.max_order_value_abs = max_order_value_abs
    row.max_quantity_per_order = max_quantity_per_order

    row.capital_per_trade = capital_per_trade
    row.max_positions = max_positions
    row.max_exposure_pct = max_exposure_pct

    row.risk_per_trade_pct = risk_per_trade_pct
    row.hard_risk_pct = hard_risk_pct
    row.stop_loss_mandatory = stop_loss_mandatory
    row.stop_reference = stop_reference
    row.atr_period = atr_period
    row.atr_mult_initial_stop = atr_mult_initial_stop
    row.fallback_stop_pct = fallback_stop_pct
    row.min_stop_distance_pct = min_stop_distance_pct
    row.max_stop_distance_pct = max_stop_distance_pct

    row.daily_loss_pct = daily_loss_pct
    row.hard_daily_loss_pct = hard_daily_loss_pct
    row.max_consecutive_losses = max_consecutive_losses

    row.entry_cutoff_time = entry_cutoff_time
    row.force_squareoff_time = force_squareoff_time
    row.max_trades_per_day = max_trades_per_day
    row.max_trades_per_symbol_per_day = max_trades_per_symbol_per_day
    row.min_bars_between_trades = min_bars_between_trades
    row.cooldown_after_loss_bars = cooldown_after_loss_bars

    row.slippage_guard_bps = slippage_guard_bps
    row.gap_guard_pct = gap_guard_pct
    row.order_type_policy = order_type_policy

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_source_override(
    db: Session,
    *,
    source_bucket: Literal["TRADINGVIEW", "SIGMATRADER"],
    product: RiskProduct,
) -> bool:
    row = (
        db.query(RiskSourceOverride)
        .filter(
            RiskSourceOverride.source_bucket == source_bucket,
            RiskSourceOverride.product == product,
        )
        .one_or_none()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


__all__ = [
    "RiskProduct",
    "RiskSourceBucket",
    "UnifiedRiskGlobal",
    "get_or_create_risk_global_config",
    "read_unified_risk_global",
    "upsert_unified_risk_global",
    "get_source_override",
    "list_source_overrides",
    "upsert_source_override",
    "delete_source_override",
]
