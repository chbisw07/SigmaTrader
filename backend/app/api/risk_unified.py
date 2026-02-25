from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.risk_unified import (
    RiskSourceOverrideRead,
    RiskSourceOverrideUpsert,
    UnifiedRiskGlobalRead,
    UnifiedRiskGlobalUpdate,
)
from app.services.risk_unified_store import (
    delete_source_override,
    list_source_overrides,
    read_unified_risk_global,
    upsert_source_override,
    upsert_unified_risk_global,
)

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
        no_trade_rules=str(getattr(g, "no_trade_rules", "") or ""),
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
        no_trade_rules=str(payload.no_trade_rules or ""),
    )
    return UnifiedRiskGlobalRead(
        enabled=bool(row.enabled),
        manual_override_enabled=bool(row.manual_override_enabled),
        baseline_equity_inr=float(row.baseline_equity_inr or 0.0),
        no_trade_rules=str(getattr(row, "no_trade_rules", "") or ""),
        updated_at=row.updated_at,
    )


@router.get("/source-overrides", response_model=list[RiskSourceOverrideRead])
def list_unified_risk_source_overrides(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),  # noqa: ARG001
) -> list[RiskSourceOverrideRead]:
    rows = list_source_overrides(db)
    return [
        RiskSourceOverrideRead(
            source_bucket=str(r.source_bucket),
            product=str(r.product),
            allow_product=r.allow_product,
            allow_short_selling=r.allow_short_selling,
            max_order_value_pct=r.max_order_value_pct,
            max_order_value_abs=r.max_order_value_abs,
            max_quantity_per_order=r.max_quantity_per_order,
            capital_per_trade=r.capital_per_trade,
            max_positions=r.max_positions,
            max_exposure_pct=r.max_exposure_pct,
            risk_per_trade_pct=r.risk_per_trade_pct,
            hard_risk_pct=r.hard_risk_pct,
            stop_loss_mandatory=r.stop_loss_mandatory,
            stop_reference=r.stop_reference,
            atr_period=r.atr_period,
            atr_mult_initial_stop=r.atr_mult_initial_stop,
            fallback_stop_pct=r.fallback_stop_pct,
            min_stop_distance_pct=r.min_stop_distance_pct,
            max_stop_distance_pct=r.max_stop_distance_pct,
            daily_loss_pct=r.daily_loss_pct,
            hard_daily_loss_pct=r.hard_daily_loss_pct,
            max_consecutive_losses=r.max_consecutive_losses,
            entry_cutoff_time=r.entry_cutoff_time,
            force_squareoff_time=r.force_squareoff_time,
            max_trades_per_day=r.max_trades_per_day,
            max_trades_per_symbol_per_day=r.max_trades_per_symbol_per_day,
            min_bars_between_trades=r.min_bars_between_trades,
            cooldown_after_loss_bars=r.cooldown_after_loss_bars,
            slippage_guard_bps=r.slippage_guard_bps,
            gap_guard_pct=r.gap_guard_pct,
            order_type_policy=r.order_type_policy,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.put("/source-overrides", response_model=RiskSourceOverrideRead)
def upsert_unified_risk_source_override(
    payload: RiskSourceOverrideUpsert,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),  # noqa: ARG001
) -> RiskSourceOverrideRead:
    row = upsert_source_override(
        db,
        source_bucket=payload.source_bucket,
        product=payload.product,
        allow_product=payload.allow_product,
        allow_short_selling=payload.allow_short_selling,
        max_order_value_pct=payload.max_order_value_pct,
        max_order_value_abs=payload.max_order_value_abs,
        max_quantity_per_order=payload.max_quantity_per_order,
        capital_per_trade=payload.capital_per_trade,
        max_positions=payload.max_positions,
        max_exposure_pct=payload.max_exposure_pct,
        risk_per_trade_pct=payload.risk_per_trade_pct,
        hard_risk_pct=payload.hard_risk_pct,
        stop_loss_mandatory=payload.stop_loss_mandatory,
        stop_reference=payload.stop_reference,
        atr_period=payload.atr_period,
        atr_mult_initial_stop=payload.atr_mult_initial_stop,
        fallback_stop_pct=payload.fallback_stop_pct,
        min_stop_distance_pct=payload.min_stop_distance_pct,
        max_stop_distance_pct=payload.max_stop_distance_pct,
        daily_loss_pct=payload.daily_loss_pct,
        hard_daily_loss_pct=payload.hard_daily_loss_pct,
        max_consecutive_losses=payload.max_consecutive_losses,
        entry_cutoff_time=payload.entry_cutoff_time,
        force_squareoff_time=payload.force_squareoff_time,
        max_trades_per_day=payload.max_trades_per_day,
        max_trades_per_symbol_per_day=payload.max_trades_per_symbol_per_day,
        min_bars_between_trades=payload.min_bars_between_trades,
        cooldown_after_loss_bars=payload.cooldown_after_loss_bars,
        slippage_guard_bps=payload.slippage_guard_bps,
        gap_guard_pct=payload.gap_guard_pct,
        order_type_policy=payload.order_type_policy,
    )
    return RiskSourceOverrideRead(
        source_bucket=str(row.source_bucket),
        product=str(row.product),
        allow_product=row.allow_product,
        allow_short_selling=row.allow_short_selling,
        max_order_value_pct=row.max_order_value_pct,
        max_order_value_abs=row.max_order_value_abs,
        max_quantity_per_order=row.max_quantity_per_order,
        capital_per_trade=row.capital_per_trade,
        max_positions=row.max_positions,
        max_exposure_pct=row.max_exposure_pct,
        risk_per_trade_pct=row.risk_per_trade_pct,
        hard_risk_pct=row.hard_risk_pct,
        stop_loss_mandatory=row.stop_loss_mandatory,
        stop_reference=row.stop_reference,
        atr_period=row.atr_period,
        atr_mult_initial_stop=row.atr_mult_initial_stop,
        fallback_stop_pct=row.fallback_stop_pct,
        min_stop_distance_pct=row.min_stop_distance_pct,
        max_stop_distance_pct=row.max_stop_distance_pct,
        daily_loss_pct=row.daily_loss_pct,
        hard_daily_loss_pct=row.hard_daily_loss_pct,
        max_consecutive_losses=row.max_consecutive_losses,
        entry_cutoff_time=row.entry_cutoff_time,
        force_squareoff_time=row.force_squareoff_time,
        max_trades_per_day=row.max_trades_per_day,
        max_trades_per_symbol_per_day=row.max_trades_per_symbol_per_day,
        min_bars_between_trades=row.min_bars_between_trades,
        cooldown_after_loss_bars=row.cooldown_after_loss_bars,
        slippage_guard_bps=row.slippage_guard_bps,
        gap_guard_pct=row.gap_guard_pct,
        order_type_policy=row.order_type_policy,
        updated_at=row.updated_at,
    )


@router.delete("/source-overrides/{source_bucket}/{product}", response_model=dict[str, bool])
def delete_unified_risk_source_override(
    source_bucket: str,
    product: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),  # noqa: ARG001
) -> dict[str, bool]:
    ok = delete_source_override(
        db,
        source_bucket=source_bucket.strip().upper(),  # type: ignore[arg-type]
        product=product.strip().upper(),  # type: ignore[arg-type]
    )
    return {"deleted": bool(ok)}


__all__ = ["router"]
