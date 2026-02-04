from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import RiskProfile, User
from app.schemas.risk_compiled import (
    CompiledDrawdownThresholds,
    CompiledRiskEffective,
    CompiledRiskOverride,
    CompiledRiskProfileRef,
    CompiledRiskProvenance,
    DrawdownState,
    RiskCategory,
    RiskProduct,
    RiskSourceBucket,
)
from app.services.risk_engine import (
    _ensure_bootstrap_rows,  # type: ignore[attr-defined]
    apply_drawdown_throttle,
    compute_portfolio_pnl_state,
    drawdown_state,
    resolve_drawdown_config,
)
from app.services.risk_unified_store import get_source_override, read_unified_risk_global

ProvSource = Literal["global", "profile", "source_override", "computed", "default", "unknown"]


@dataclass(frozen=True)
class _ResolveResult:
    value: Any
    provenance: CompiledRiskProvenance
    override: CompiledRiskOverride | None = None


def _profile_ref(p: RiskProfile) -> CompiledRiskProfileRef:
    return CompiledRiskProfileRef(
        id=int(p.id),
        name=str(p.name),
        product=str(p.product),  # type: ignore[arg-type]
        enabled=bool(p.enabled),
        is_default=bool(p.is_default),
    )


def _allow_entries(drawdown: DrawdownState | None, *, category: str) -> bool:
    if drawdown == "HARD_STOP":
        return False
    if drawdown == "DEFENSE" and (category or "").strip().upper() not in {"ETF", "LC"}:
        return False
    return True


def _resolve(
    *,
    field: str,
    profile_value: Any,
    override_value: Any,
    profile_name: str | None,
    source_bucket: str,
    product: str,
) -> _ResolveResult:
    if override_value is not None:
        prov = CompiledRiskProvenance(source="source_override", detail=f"{source_bucket}/{product}")
        ov = None
        if profile_value != override_value:
            ov = CompiledRiskOverride(
                field=field,
                from_value=profile_value,
                to_value=override_value,
                reason="Source override",
                source="source_override",
            )
        return _ResolveResult(value=override_value, provenance=prov, override=ov)
    prov_src: ProvSource = "profile" if profile_name is not None else "default"
    return _ResolveResult(
        value=profile_value,
        provenance=CompiledRiskProvenance(source=prov_src, detail=profile_name),
        override=None,
    )


def compile_risk_policy(
    db: Session,
    settings: Settings,
    *,
    user: User | None,
    product: RiskProduct,
    category: RiskCategory,
    source_bucket: RiskSourceBucket = "TRADINGVIEW",
    order_type: str | None = None,
    scenario: DrawdownState | None = None,
    symbol: str | None = None,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    """UI-facing "Effective Risk Summary" for the unified risk system."""

    now_utc = datetime.now(UTC)
    _ensure_bootstrap_rows(db)

    g = read_unified_risk_global(db)
    baseline_equity = float(g.baseline_equity_inr or 0.0)

    # Select the default enabled profile for this product.
    prof = (
        db.query(RiskProfile)
        .filter(
            RiskProfile.enabled.is_(True),
            RiskProfile.is_default.is_(True),
            RiskProfile.product == (product or "CNC"),
        )
        .one_or_none()
    )
    if prof is None:
        prof = (
            db.query(RiskProfile)
            .filter(RiskProfile.enabled.is_(True), RiskProfile.product == (product or "CNC"))
            .order_by(RiskProfile.id)
            .first()
        )

    src = (source_bucket or "TRADINGVIEW").strip().upper()
    if src not in {"TRADINGVIEW", "SIGMATRADER", "MANUAL"}:
        src = "TRADINGVIEW"

    src_override = None
    if src != "MANUAL" and prof is not None:
        src_override = get_source_override(
            db,
            source_bucket=src,  # type: ignore[arg-type]
            product=str(prof.product).strip().upper(),  # type: ignore[arg-type]
        )

    profile_name = str(prof.name) if prof is not None else None

    provenance: dict[str, CompiledRiskProvenance] = {
        "risk_enabled": CompiledRiskProvenance(source="global"),
        "manual_override_enabled": CompiledRiskProvenance(source="global"),
        "baseline_equity_inr": CompiledRiskProvenance(source="global"),
    }
    overrides: list[CompiledRiskOverride] = []

    # Drawdown state (live, with optional what-if override).
    dd_cfg = resolve_drawdown_config(db, product=product, category=category)
    thresholds = None
    if dd_cfg is not None:
        thresholds = CompiledDrawdownThresholds(
            caution_pct=float(dd_cfg.caution_pct),
            defense_pct=float(dd_cfg.defense_pct),
            hard_stop_pct=float(dd_cfg.hard_stop_pct),
        )

    pnl_state = compute_portfolio_pnl_state(
        db,
        user_id=(user.id if user is not None else None),
        baseline_equity=baseline_equity,
        now_utc=now_utc,
    )
    dd_pct = float(pnl_state.drawdown_pct)

    dd_state: DrawdownState | None = None
    missing_thresholds_reason: str | None = None
    if dd_cfg is not None:
        dd_state = drawdown_state(dd_pct, dd_cfg)
    elif src != "MANUAL":
        missing_thresholds_reason = f"Missing drawdown thresholds for {product}+{category} (configure in Settings)."
    if scenario is not None:
        dd_state = scenario
        provenance["drawdown_state"] = CompiledRiskProvenance(source="computed", detail="what_if_override")
    else:
        provenance["drawdown_state"] = CompiledRiskProvenance(source="computed", detail="live_dd_pct")

    # Resolve fields with precedence: source override -> profile.
    def pv(attr: str, default: Any) -> Any:
        return getattr(prof, attr, default) if prof is not None else default

    def ov(attr: str) -> Any:
        return getattr(src_override, attr, None) if src_override is not None else None

    resolved: dict[str, Any] = {}
    for field, attr, default in (
        ("capital_per_trade", "capital_per_trade", 0.0),
        ("max_positions", "max_positions", 0),
        ("max_exposure_pct", "max_exposure_pct", 0.0),
        ("daily_loss_pct", "daily_loss_pct", 0.0),
        ("hard_daily_loss_pct", "hard_daily_loss_pct", 0.0),
        ("max_consecutive_losses", "max_consecutive_losses", 0),
        ("risk_per_trade_pct", "risk_per_trade_pct", 0.0),
        ("hard_risk_pct", "hard_risk_pct", 0.0),
        ("stop_loss_mandatory", "stop_loss_mandatory", True),
        ("stop_reference", "stop_reference", "ATR"),
        ("atr_period", "atr_period", 14),
        ("atr_mult_initial_stop", "atr_mult_initial_stop", 2.0),
        ("fallback_stop_pct", "fallback_stop_pct", 1.0),
        ("min_stop_distance_pct", "min_stop_distance_pct", 0.5),
        ("max_stop_distance_pct", "max_stop_distance_pct", 3.0),
        ("entry_cutoff_time", "entry_cutoff_time", None),
        ("force_squareoff_time", "force_squareoff_time", None),
        ("max_trades_per_day", "max_trades_per_day", None),
        ("max_trades_per_symbol_per_day", "max_trades_per_symbol_per_day", None),
        ("min_bars_between_trades", "min_bars_between_trades", None),
        ("cooldown_after_loss_bars", "cooldown_after_loss_bars", None),
    ):
        r = _resolve(
            field=field,
            profile_value=pv(attr, default),
            override_value=ov(attr),
            profile_name=profile_name,
            source_bucket=src,
            product=str(product),
        )
        resolved[field] = r.value
        provenance[field] = r.provenance
        if r.override is not None:
            overrides.append(r.override)

    # Drawdown throttle applies to capital_per_trade and max_positions.
    cap_before = float(resolved["capital_per_trade"] or 0.0)
    max_pos_before = int(resolved["max_positions"] or 0)
    cap_eff, max_pos_eff, dd_reasons = apply_drawdown_throttle(
        capital_per_trade=cap_before,
        max_positions=max_pos_before,
        state=dd_state or "NORMAL",
        category=str(category),
    )

    throttle_multiplier = 1.0
    if cap_before > 0 and cap_eff > 0:
        throttle_multiplier = float(cap_eff) / float(cap_before)

    if float(cap_eff) != float(cap_before):
        overrides.append(
            CompiledRiskOverride(
                field="capital_per_trade",
                from_value=cap_before,
                to_value=float(cap_eff),
                reason="Drawdown throttle",
                source="computed",
            )
        )
        provenance["capital_per_trade"] = CompiledRiskProvenance(source="computed", detail="drawdown_throttle")
    if int(max_pos_eff) != int(max_pos_before):
        overrides.append(
            CompiledRiskOverride(
                field="max_positions",
                from_value=max_pos_before,
                to_value=int(max_pos_eff),
                reason="Drawdown throttle",
                source="computed",
            )
        )
        provenance["max_positions"] = CompiledRiskProvenance(source="computed", detail="drawdown_throttle")

    resolved["capital_per_trade"] = float(cap_eff)
    resolved["max_positions"] = int(max_pos_eff)

    allow_new_entries = _allow_entries(dd_state, category=str(category))
    if missing_thresholds_reason is not None:
        allow_new_entries = False

    # Source gating + per-order caps.
    allow_product = True
    allow_short_selling = True
    max_order_value_pct = None
    max_order_value_abs = None
    max_qty_per_order = None
    order_type_policy = None
    slippage_guard_bps = None
    gap_guard_pct = None
    if src != "MANUAL" and src_override is not None:
        if getattr(src_override, "allow_product", None) is False:
            allow_product = False
        if src_override.allow_short_selling is not None:
            allow_short_selling = bool(src_override.allow_short_selling)
        if src_override.max_order_value_pct is not None:
            max_order_value_pct = float(src_override.max_order_value_pct)
        if src_override.max_order_value_abs is not None:
            max_order_value_abs = float(src_override.max_order_value_abs)
        if src_override.max_quantity_per_order is not None:
            max_qty_per_order = float(src_override.max_quantity_per_order)
        order_type_policy = src_override.order_type_policy
        slippage_guard_bps = src_override.slippage_guard_bps
        gap_guard_pct = src_override.gap_guard_pct

    provenance["allow_product"] = CompiledRiskProvenance(
        source="source_override" if src_override is not None else "default",
        detail=(f"{src}/{product}" if src_override is not None else None),
    )
    provenance["allow_short_selling"] = CompiledRiskProvenance(
        source="source_override" if src_override is not None else "default",
        detail=(f"{src}/{product}" if src_override is not None else None),
    )

    blocking_reasons = list(dd_reasons)
    if missing_thresholds_reason is not None:
        blocking_reasons.append(missing_thresholds_reason)
    if not allow_product:
        blocking_reasons.append(f"{src} {product} disabled by Risk Settings.")

    eff = CompiledRiskEffective(
        allow_new_entries=bool(g.enabled) and bool(allow_new_entries and allow_product),
        blocking_reasons=blocking_reasons,
        drawdown_state=dd_state,
        throttle_multiplier=float(throttle_multiplier),
        profile=_profile_ref(prof) if prof is not None else None,
        thresholds=thresholds,
        allow_product=bool(allow_product),
        allow_short_selling=bool(allow_short_selling),
        max_order_value_pct=max_order_value_pct,
        max_order_value_abs=max_order_value_abs,
        max_quantity_per_order=max_qty_per_order,
        order_type_policy=order_type_policy,
        slippage_guard_bps=slippage_guard_bps,
        gap_guard_pct=gap_guard_pct,
        capital_per_trade=float(resolved["capital_per_trade"]),
        max_positions=int(resolved["max_positions"]),
        max_exposure_pct=float(resolved["max_exposure_pct"]),
        daily_loss_pct=float(resolved["daily_loss_pct"]),
        hard_daily_loss_pct=float(resolved["hard_daily_loss_pct"]),
        max_consecutive_losses=int(resolved["max_consecutive_losses"]),
        risk_per_trade_pct=float(resolved["risk_per_trade_pct"]),
        hard_risk_pct=float(resolved["hard_risk_pct"]),
        stop_loss_mandatory=bool(resolved["stop_loss_mandatory"]),
        stop_reference=str(resolved["stop_reference"]),
        atr_period=int(resolved["atr_period"]),
        atr_mult_initial_stop=float(resolved["atr_mult_initial_stop"]),
        fallback_stop_pct=float(resolved["fallback_stop_pct"]),
        min_stop_distance_pct=float(resolved["min_stop_distance_pct"]),
        max_stop_distance_pct=float(resolved["max_stop_distance_pct"]),
        entry_cutoff_time=(str(resolved["entry_cutoff_time"]) if resolved["entry_cutoff_time"] else None),
        force_squareoff_time=(str(resolved["force_squareoff_time"]) if resolved["force_squareoff_time"] else None),
        max_trades_per_day=(
            int(resolved["max_trades_per_day"])
            if resolved["max_trades_per_day"] is not None
            else None
        ),
        max_trades_per_symbol_per_day=(
            int(resolved["max_trades_per_symbol_per_day"])
            if resolved["max_trades_per_symbol_per_day"] is not None
            else None
        ),
        min_bars_between_trades=(
            int(resolved["min_bars_between_trades"])
            if resolved["min_bars_between_trades"] is not None
            else None
        ),
        cooldown_after_loss_bars=(
            int(resolved["cooldown_after_loss_bars"])
            if resolved["cooldown_after_loss_bars"] is not None
            else None
        ),
    )

    # Pydantic v1/v2 compatibility.
    eff_payload = eff.model_dump() if hasattr(eff, "model_dump") else eff.dict()
    overrides_payload = [o.model_dump() if hasattr(o, "model_dump") else o.dict() for o in overrides]
    provenance_payload = {k: (v.model_dump() if hasattr(v, "model_dump") else v.dict()) for k, v in provenance.items()}

    return {
        "context": {
            "product": product,
            "category": category,
            "source_bucket": src,
            "order_type": order_type,
            "scenario": scenario,
            "symbol": symbol,
            "strategy_id": strategy_id,
        },
        "inputs": {
            "compiled_at": now_utc,
            "risk_enabled": bool(g.enabled),
            "manual_override_enabled": bool(g.manual_override_enabled),
            "baseline_equity_inr": float(baseline_equity),
            "drawdown_pct": float(dd_pct) if baseline_equity > 0 else None,
        },
        "effective": eff_payload,
        "overrides": overrides_payload,
        "provenance": provenance_payload,
    }


__all__ = ["compile_risk_policy"]
