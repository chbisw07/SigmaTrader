from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import RiskProfile
from app.services.risk_policy_store import get_risk_policy
from app.services.risk_unified_store import get_or_create_risk_global_config

logger = logging.getLogger(__name__)


def migrate_legacy_risk_policy_v1_to_unified(db: Session, settings: Settings) -> bool:
    """Best-effort, idempotent migration from legacy Risk Policy JSON to unified risk tables.

    We only copy values that are required to avoid immediate breakage when switching
    enforcement to unified (baseline equity, and key per-product caps).
    """

    # Ensure singleton exists.
    global_row = get_or_create_risk_global_config(db)

    # Load v1 policy if present; if not, do nothing.
    try:
        policy, source = get_risk_policy(db, settings)
    except Exception:
        return False

    # If policy was never customized, there's nothing meaningful to migrate.
    if str(source or "").strip().lower() == "default":
        return False

    changed = False

    # Baseline equity drives v2 drawdown and daily loss checks; without it v2 blocks entries.
    try:
        v1_equity = float(getattr(getattr(policy, "equity", None), "manual_equity_inr", 0.0) or 0.0)
    except Exception:
        v1_equity = 0.0
    if float(global_row.baseline_equity_inr or 0.0) <= 0 and v1_equity > 0:
        global_row.baseline_equity_inr = float(v1_equity)
        changed = True

    # Map a few global caps into both product profiles (CNC/MIS) so behavior remains similar.
    try:
        cap_per_trade = float(getattr(getattr(policy, "position_sizing", None), "capital_per_trade", 0.0) or 0.0)
    except Exception:
        cap_per_trade = 0.0
    try:
        max_positions = int(getattr(getattr(policy, "account_risk", None), "max_open_positions", 0) or 0)
    except Exception:
        max_positions = 0
    try:
        max_exposure_pct = float(getattr(getattr(policy, "account_risk", None), "max_exposure_pct", 0.0) or 0.0)
    except Exception:
        max_exposure_pct = 0.0
    try:
        daily_loss_pct = float(getattr(getattr(policy, "account_risk", None), "max_daily_loss_pct", 0.0) or 0.0)
    except Exception:
        daily_loss_pct = 0.0
    try:
        max_losses = int(getattr(getattr(policy, "loss_controls", None), "max_consecutive_losses", 0) or 0)
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
            continue
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
        if max_losses > 0 and int(getattr(prof, "max_consecutive_losses", 0) or 0) <= 0:
            prof.max_consecutive_losses = int(max_losses)
            changed = True
        db.add(prof)

    if changed:
        db.add(global_row)
        db.commit()
        logger.info("Migrated legacy risk policy v1 into unified risk settings.", extra={"extra": {"source": source}})
    return changed


__all__ = ["migrate_legacy_risk_policy_v1_to_unified"]

