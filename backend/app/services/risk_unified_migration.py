from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import DrawdownThreshold, RiskGlobalConfig, RiskProfile, RiskSourceOverride, SymbolRiskCategory
from app.services.risk_policy_store import get_risk_policy
from app.services.risk_unified_store import get_or_create_risk_global_config

logger = logging.getLogger(__name__)

_DEFAULT_BASELINE_EQUITY_INR = 1_000_000.0
_DEFAULT_CATEGORY = "LC"
_CATEGORIES = ("LC", "MC", "SC", "ETF")
_DEFAULT_CAPITAL_PER_TRADE = 20_000.0
_DEFAULT_MAX_POSITIONS = 6
_DEFAULT_MAX_EXPOSURE_PCT = 60.0


def migrate_legacy_risk_policy_v1_to_unified(db: Session, settings: Settings) -> bool:
    """Best-effort, idempotent migration from legacy Risk Policy JSON to unified risk tables.

    We only copy values that are required to avoid immediate breakage when switching
    enforcement to unified (baseline equity, and key per-product caps).
    """

    # Ensure singleton exists.
    existing_global = (
        db.query(RiskGlobalConfig)
        .filter(RiskGlobalConfig.singleton_key == "GLOBAL")
        .one_or_none()
    )
    global_row = get_or_create_risk_global_config(db)

    # Load v1 policy if present; if not, still seed the unified tables so the
    # unified engine can run in fresh installs/tests (do not depend on legacy).
    try:
        policy, source = get_risk_policy(db, settings)
    except Exception:
        policy, source = None, "unavailable"

    # Even when the legacy policy is the built-in default, we still ensure the
    # unified tables are seeded so the profile-based engine can operate without
    # blocking on missing rows.

    changed = False

    # Align unified enforcement toggle with legacy v1, but only on first creation
    # to avoid overwriting explicit unified edits.
    if existing_global is None and policy is not None:
        try:
            global_row.enabled = bool(getattr(policy, "enabled", True))
            changed = True
        except Exception:
            pass

    # Baseline equity drives drawdown and daily loss checks; without it the unified engine blocks entries.
    v1_equity = 0.0
    try:
        if policy is not None:
            v1_equity = float(
                getattr(getattr(policy, "equity", None), "manual_equity_inr", 0.0) or 0.0
            )
    except Exception:
        v1_equity = 0.0
    if float(global_row.baseline_equity_inr or 0.0) <= 0:
        if v1_equity > 0:
            global_row.baseline_equity_inr = float(v1_equity)
        else:
            global_row.baseline_equity_inr = float(_DEFAULT_BASELINE_EQUITY_INR)
        changed = True

    # Map a few global caps into both product profiles (CNC/MIS) so behavior remains similar.
    cap_per_trade = 0.0
    try:
        if policy is not None:
            cap_per_trade = float(
                getattr(getattr(policy, "position_sizing", None), "capital_per_trade", 0.0) or 0.0
            )
    except Exception:
        cap_per_trade = 0.0
    max_positions = 0
    try:
        if policy is not None:
            max_positions = int(
                getattr(getattr(policy, "account_risk", None), "max_open_positions", 0) or 0
            )
    except Exception:
        max_positions = 0
    max_exposure_pct = 0.0
    try:
        if policy is not None:
            max_exposure_pct = float(
                getattr(getattr(policy, "account_risk", None), "max_exposure_pct", 0.0) or 0.0
            )
    except Exception:
        max_exposure_pct = 0.0
    daily_loss_pct = 0.0
    try:
        if policy is not None:
            daily_loss_pct = float(
                getattr(getattr(policy, "account_risk", None), "max_daily_loss_pct", 0.0) or 0.0
            )
    except Exception:
        daily_loss_pct = 0.0
    max_losses = 0
    try:
        if policy is not None:
            max_losses = int(
                getattr(getattr(policy, "loss_controls", None), "max_consecutive_losses", 0) or 0
            )
    except Exception:
        max_losses = 0

    # Per-trade + stop model settings (used for risk_per_trade enforcement).
    risk_per_trade_pct = 0.0
    hard_risk_pct = 0.0
    stop_loss_mandatory = True
    stop_reference = "ATR"
    atr_period = 14
    atr_mult_initial_stop = 2.0
    fallback_stop_pct = 1.0
    min_stop_distance_pct = 0.5
    max_stop_distance_pct = 3.0
    try:
        if policy is not None:
            risk_per_trade_pct = float(
                getattr(getattr(policy, "trade_risk", None), "max_risk_per_trade_pct", 0.0) or 0.0
            )
            hard_risk_pct = float(
                getattr(getattr(policy, "trade_risk", None), "hard_max_risk_pct", 0.0) or 0.0
            )
            stop_loss_mandatory = bool(
                getattr(getattr(policy, "trade_risk", None), "stop_loss_mandatory", True)
            )
            stop_reference = str(
                getattr(getattr(policy, "trade_risk", None), "stop_reference", "ATR") or "ATR"
            ).strip().upper()
            atr_period = int(getattr(getattr(policy, "stop_rules", None), "atr_period", 14) or 14)
            atr_mult_initial_stop = float(
                getattr(getattr(policy, "stop_rules", None), "initial_stop_atr", 2.0) or 2.0
            )
            fallback_stop_pct = float(
                getattr(getattr(policy, "stop_rules", None), "fallback_stop_pct", 1.0) or 1.0
            )
            min_stop_distance_pct = float(
                getattr(getattr(policy, "stop_rules", None), "min_stop_distance_pct", 0.5) or 0.5
            )
            max_stop_distance_pct = float(
                getattr(getattr(policy, "stop_rules", None), "max_stop_distance_pct", 3.0) or 3.0
            )
    except Exception:
        pass

    for prod in ("CNC", "MIS"):
        prof = (
            db.query(RiskProfile)
            .filter(RiskProfile.product == prod, RiskProfile.enabled.is_(True))
            .order_by(RiskProfile.is_default.desc(), RiskProfile.id.asc())
            .first()
        )
        if prof is None:
            prof = RiskProfile(
                name=f"Default {prod}",
                product=prod,
                enabled=True,
                is_default=True,
                # Safe defaults so the v2 engine can size orders immediately in fresh installs/tests.
                capital_per_trade=float(_DEFAULT_CAPITAL_PER_TRADE),
                max_positions=int(_DEFAULT_MAX_POSITIONS),
                max_exposure_pct=float(_DEFAULT_MAX_EXPOSURE_PCT),
                # Avoid requiring broker-margin tuning out of the box.
                leverage_mode="OFF",
            )
            db.add(prof)
            changed = True
        # Ensure fresh installs do not end up with blocking zero values.
        if float(getattr(prof, "capital_per_trade", 0.0) or 0.0) <= 0:
            prof.capital_per_trade = float(_DEFAULT_CAPITAL_PER_TRADE)
            changed = True
        if int(getattr(prof, "max_positions", 0) or 0) <= 0:
            prof.max_positions = int(_DEFAULT_MAX_POSITIONS)
            changed = True
        if float(getattr(prof, "max_exposure_pct", 0.0) or 0.0) <= 0:
            prof.max_exposure_pct = float(_DEFAULT_MAX_EXPOSURE_PCT)
            changed = True
        # Stop model defaults (ensure non-null, reasonable settings).
        if getattr(prof, "stop_reference", None) is None:
            prof.stop_reference = "ATR"
            changed = True
        if int(getattr(prof, "atr_period", 0) or 0) <= 0:
            prof.atr_period = 14
            changed = True
        if float(getattr(prof, "atr_mult_initial_stop", 0.0) or 0.0) <= 0:
            prof.atr_mult_initial_stop = 2.0
            changed = True
        if float(getattr(prof, "fallback_stop_pct", 0.0) or 0.0) <= 0:
            prof.fallback_stop_pct = 1.0
            changed = True
        if float(getattr(prof, "min_stop_distance_pct", 0.0) or 0.0) <= 0:
            prof.min_stop_distance_pct = 0.5
            changed = True
        if float(getattr(prof, "max_stop_distance_pct", 0.0) or 0.0) <= 0:
            prof.max_stop_distance_pct = 3.0
            changed = True
        if cap_per_trade > 0 and float(getattr(prof, "capital_per_trade", 0.0) or 0.0) <= 0:
            prof.capital_per_trade = float(cap_per_trade)
            changed = True
        if max_positions > 0 and int(getattr(prof, "max_positions", 0) or 0) <= 0:
            prof.max_positions = int(max_positions)
            changed = True
        if max_exposure_pct > 0 and float(getattr(prof, "max_exposure_pct", 0.0) or 0.0) <= 0:
            prof.max_exposure_pct = float(max_exposure_pct)
            changed = True
        if daily_loss_pct > 0 and float(getattr(prof, "daily_loss_pct", 0.0) or 0.0) <= 0:
            prof.daily_loss_pct = float(daily_loss_pct)
            changed = True
        if daily_loss_pct > 0 and float(getattr(prof, "hard_daily_loss_pct", 0.0) or 0.0) <= 0:
            prof.hard_daily_loss_pct = float(daily_loss_pct)
            changed = True
        if max_losses > 0 and int(getattr(prof, "max_consecutive_losses", 0) or 0) <= 0:
            prof.max_consecutive_losses = int(max_losses)
            changed = True
        if risk_per_trade_pct > 0 and float(getattr(prof, "risk_per_trade_pct", 0.0) or 0.0) <= 0:
            prof.risk_per_trade_pct = float(risk_per_trade_pct)
            changed = True
        if hard_risk_pct > 0 and float(getattr(prof, "hard_risk_pct", 0.0) or 0.0) <= 0:
            prof.hard_risk_pct = float(hard_risk_pct)
            changed = True
        # Stop model from v1 (only when profile still looks default-ish).
        cur_ref = str(getattr(prof, "stop_reference", "") or "ATR").strip().upper() or "ATR"
        if stop_reference in {"ATR", "FIXED_PCT"} and cur_ref == "ATR" and stop_reference != cur_ref:
            prof.stop_reference = stop_reference
            changed = True
        if bool(getattr(prof, "stop_loss_mandatory", True)) is True and stop_loss_mandatory is False:
            prof.stop_loss_mandatory = False
            changed = True
        # Only set advanced stop knobs when they are still at defaults.
        if int(getattr(prof, "atr_period", 14) or 14) == 14:
            prof.atr_period = int(atr_period or 14)
            changed = True
        if float(getattr(prof, "atr_mult_initial_stop", 2.0) or 2.0) == 2.0:
            prof.atr_mult_initial_stop = float(atr_mult_initial_stop or 2.0)
            changed = True
        if float(getattr(prof, "fallback_stop_pct", 1.0) or 1.0) == 1.0:
            prof.fallback_stop_pct = float(fallback_stop_pct or 1.0)
            changed = True
        if float(getattr(prof, "min_stop_distance_pct", 0.5) or 0.5) == 0.5:
            prof.min_stop_distance_pct = float(min_stop_distance_pct or 0.5)
            changed = True
        if float(getattr(prof, "max_stop_distance_pct", 3.0) or 3.0) == 3.0:
            prof.max_stop_distance_pct = float(max_stop_distance_pct or 3.0)
            changed = True
        db.add(prof)

    # Source overrides: map legacy per-source/product overrides (best-effort, no overwrite).
    if policy is not None:
        exec_safety = getattr(policy, "execution_safety", None)
        allow_short = bool(getattr(exec_safety, "allow_short_selling", True)) if exec_safety is not None else True
        max_order_value_pct = (
            float(getattr(exec_safety, "max_order_value_pct", 0.0) or 0.0)
            if exec_safety is not None
            else 0.0
        )

        for source in ("TRADINGVIEW", "SIGMATRADER"):
            for prod in ("CNC", "MIS"):
                try:
                    ovr = policy.product_overrides(source=source, product=prod)
                except Exception:
                    ovr = None
                if ovr is None:
                    continue

                row = (
                    db.query(RiskSourceOverride)
                    .filter(
                        RiskSourceOverride.source_bucket == source,
                        RiskSourceOverride.product == prod,
                    )
                    .one_or_none()
                )
                if row is None:
                    row = RiskSourceOverride(source_bucket=source, product=prod)
                    db.add(row)
                    changed = True

                allow = getattr(ovr, "allow", None)
                if row.allow_product is None and allow is False:
                    row.allow_product = False
                    changed = True

                if row.allow_short_selling is None and allow_short is False:
                    row.allow_short_selling = False
                    changed = True

                if row.max_order_value_pct is None and max_order_value_pct > 0:
                    row.max_order_value_pct = float(max_order_value_pct)
                    changed = True

                for k_src, k_dst in (
                    ("max_order_value_abs", "max_order_value_abs"),
                    ("max_quantity_per_order", "max_quantity_per_order"),
                    ("capital_per_trade", "capital_per_trade"),
                    ("max_risk_per_trade_pct", "risk_per_trade_pct"),
                    ("hard_max_risk_pct", "hard_risk_pct"),
                ):
                    cur = getattr(row, k_dst, None)
                    nxt = getattr(ovr, k_src, None)
                    if cur is None and nxt is not None:
                        setattr(row, k_dst, nxt)
                        changed = True

                db.add(row)

    # Ensure global default symbol risk category exists so enforcement doesn't
    # block new/unseen symbols in fresh installs. Per-user mappings still win.
    try:
        default_cat = (
            db.query(SymbolRiskCategory)
            .filter(
                SymbolRiskCategory.user_id.is_(None),
                SymbolRiskCategory.broker_name == "*",
                SymbolRiskCategory.exchange == "*",
                SymbolRiskCategory.symbol == "*",
            )
            .one_or_none()
        )
        if default_cat is None:
            db.add(
                SymbolRiskCategory(
                    user_id=None,
                    broker_name="*",
                    exchange="*",
                    symbol="*",
                    risk_category=_DEFAULT_CATEGORY,
                )
            )
            changed = True
    except Exception:
        pass

    # Ensure drawdown threshold rows exist for all categories (defaults to 0 => no gating).
    try:
        for prod in ("CNC", "MIS"):
            for cat in _CATEGORIES:
                row = (
                    db.query(DrawdownThreshold)
                    .filter(
                        DrawdownThreshold.user_id.is_(None),
                        DrawdownThreshold.product == prod,
                        DrawdownThreshold.category == cat,
                    )
                    .one_or_none()
                )
                if row is None:
                    db.add(
                        DrawdownThreshold(
                            user_id=None,
                            product=prod,
                            category=cat,
                            caution_pct=0.0,
                            defense_pct=0.0,
                            hard_stop_pct=0.0,
                        )
                    )
                    changed = True
    except Exception:
        pass

    if changed:
        db.add(global_row)
        db.commit()
        logger.info("Migrated legacy risk policy v1 into unified risk settings.", extra={"extra": {"source": source}})
    return changed


__all__ = ["migrate_legacy_risk_policy_v1_to_unified"]
