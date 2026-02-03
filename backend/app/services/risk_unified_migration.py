from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import DrawdownThreshold, RiskProfile, SymbolRiskCategory
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

    # Baseline equity drives v2 drawdown and daily loss checks; without it v2 blocks entries.
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
        db.add(prof)

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
