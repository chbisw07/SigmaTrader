from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.ai_trading_manager import AiTmJournalEvent, AiTmManagePlaybook, AiTmPositionShadow
from app.services.ai_trading_manager.journal import append_journal_event


def _json_loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _best_playbook_for_shadow(db: Session, *, shadow: AiTmPositionShadow) -> Optional[AiTmManagePlaybook]:
    # Precedence: POSITION -> SYMBOL -> PORTFOLIO_DEFAULT (enabled only).
    rows = (
        db.execute(select(AiTmManagePlaybook).where(AiTmManagePlaybook.enabled.is_(True)))
        .scalars()
        .all()
    )
    pos: AiTmManagePlaybook | None = None
    sym: AiTmManagePlaybook | None = None
    default: AiTmManagePlaybook | None = None
    for r in rows:
        st = str(r.scope_type or "").upper()
        if st == "POSITION" and str(r.scope_key or "") == str(shadow.shadow_id):
            pos = r
        if st == "SYMBOL" and str(r.scope_key or "").upper() == str(shadow.symbol or "").upper():
            sym = r
        if st == "PORTFOLIO_DEFAULT" and (r.scope_key is None or str(r.scope_key or "").strip() == ""):
            default = r
    return pos or sym or default


def _last_review_at(db: Session, *, shadow_id: str) -> datetime | None:
    row = (
        db.execute(
            select(AiTmJournalEvent)
            .where(
                AiTmJournalEvent.position_shadow_id == shadow_id,
                AiTmJournalEvent.event_type == "REVIEW",
            )
            .order_by(desc(AiTmJournalEvent.ts))
            .limit(1)
        )
        .scalars()
        .first()
    )
    return row.ts if row is not None else None


def _recent_review_has_proposal_key(db: Session, *, shadow_id: str, proposal_key: str, lookback_days: int = 60) -> bool:
    try:
        from datetime import timedelta

        since = datetime.now(UTC) - timedelta(days=int(lookback_days))
    except Exception:
        since = datetime.now(UTC)
    rows = (
        db.execute(
            select(AiTmJournalEvent)
            .where(
                AiTmJournalEvent.position_shadow_id == shadow_id,
                AiTmJournalEvent.event_type == "REVIEW",
                AiTmJournalEvent.ts >= since,
            )
            .order_by(desc(AiTmJournalEvent.ts))
            .limit(200)
        )
        .scalars()
        .all()
    )
    for r in rows:
        pr = _json_loads(r.playbook_result_json or "{}", {}) if r.playbook_result_json else {}
        for p in pr.get("proposals") or []:
            if isinstance(p, dict) and str(p.get("proposal_key") or "") == proposal_key:
                return True
    return False


def _build_proposals(*, shadow: AiTmPositionShadow, playbook: AiTmManagePlaybook) -> List[Dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    exit_policy = _json_loads(playbook.exit_policy_json or "{}", {})
    scale_policy = _json_loads(playbook.scale_policy_json or "{}", {})

    qty = float(shadow.qty_current or 0.0)
    avg = float(shadow.avg_price) if shadow.avg_price is not None else None
    pnl_pct = float(shadow.pnl_pct) if shadow.pnl_pct is not None else None

    protective = exit_policy.get("protective_stop") if isinstance(exit_policy, dict) else None
    if isinstance(protective, dict) and avg is not None:
        stype = str(protective.get("type") or "").upper()
        if stype == "FIXED_PCT":
            pct = float(protective.get("pct") or 0.0)
            stop_px = avg * (1.0 - pct / 100.0)
            proposals.append(
                {
                    "proposal_key": f"STOP_FIXED_PCT_{pct}",
                    "intent_type": "STOP_UPDATE",
                    "stop_price": round(float(stop_px), 2),
                    "rationale": f"Protective stop at -{pct:.2f}% from avg buy.",
                }
            )

    take_profit = exit_policy.get("take_profit") if isinstance(exit_policy, dict) else None
    if isinstance(take_profit, dict) and pnl_pct is not None and qty > 0:
        tptype = str(take_profit.get("type") or "").upper()
        if tptype == "LADDER":
            steps = take_profit.get("steps") or []
            if isinstance(steps, list):
                for step in steps:
                    if not isinstance(step, dict):
                        continue
                    pct = float(step.get("pct") or 0.0)
                    exit_pct = float(step.get("exit_pct") or 0.0)
                    if pct <= 0 or exit_pct <= 0:
                        continue
                    if pnl_pct >= pct:
                        proposal_key = f"TP_LADDER_{pct}"
                        target_qty = max(1.0, qty * (exit_pct / 100.0))
                        proposals.append(
                            {
                                "proposal_key": proposal_key,
                                "intent_type": "REDUCE",
                                "qty": int(target_qty) if float(target_qty).is_integer() else float(target_qty),
                                "rationale": f"Take-profit ladder step at +{pct:.2f}% (exit {exit_pct:.0f}%).",
                            }
                        )

    # Strategy exit partial conversion tuning is enforced pre-trade; surface config here for clarity.
    beh = str(playbook.behavior_on_strategy_exit or "").upper()
    if beh == "CONVERT_TO_PARTIAL":
        pct = float(scale_policy.get("strategy_exit_partial_pct") or 0.5)
        proposals.append(
            {
                "proposal_key": "TV_EXIT_PARTIAL",
                "intent_type": "INFO",
                "rationale": f"TV exits convert to partial ({pct * 100:.0f}%) when enabled.",
            }
        )
    return proposals


def run_manage_playbook_reviews(
    db: Session,
    settings: Settings,
    *,
    account_id: str = "default",
) -> Dict[str, Any]:
    """Deterministic monitoring loop for playbooks.

    Produces REVIEW journal events and (for mode=PROPOSE/EXECUTE) safe ActionCard-style proposals.
    Execution (broker calls) is intentionally NOT done here; the order/queue pipeline remains the source of truth.
    """
    _ = settings
    now = datetime.now(UTC)
    shadows = (
        db.execute(
            select(AiTmPositionShadow).where(
                AiTmPositionShadow.broker_account_id == account_id,
                AiTmPositionShadow.status == "OPEN",
            )
        )
        .scalars()
        .all()
    )
    reviewed = 0
    proposed = 0
    for s in shadows:
        pb = _best_playbook_for_shadow(db, shadow=s)
        if pb is None:
            continue

        cadence_min = int(pb.review_cadence_min or 60)
        last = _last_review_at(db, shadow_id=s.shadow_id)
        if last is not None:
            delta_min = (now - last).total_seconds() / 60.0
            if delta_min < float(cadence_min):
                continue

        mode = str(pb.mode or "OBSERVE").upper()
        proposals: list[dict[str, Any]] = []
        if mode in {"PROPOSE", "EXECUTE"}:
            for p in _build_proposals(shadow=s, playbook=pb):
                key = str(p.get("proposal_key") or "")
                if key and _recent_review_has_proposal_key(db, shadow_id=s.shadow_id, proposal_key=key):
                    continue
                proposals.append(p)
            proposed += len(proposals)

        append_journal_event(
            db,
            shadow_id=s.shadow_id,
            ts=now,
            event_type="REVIEW",
            source="SYSTEM",
            intent_payload={
                "symbol": s.symbol,
                "product": s.product,
                "qty": s.qty_current,
                "avg_price": s.avg_price,
                "ltp": s.ltp,
                "pnl_abs": s.pnl_abs,
                "pnl_pct": s.pnl_pct,
            },
            playbook_result={
                "playbook_id": pb.playbook_id,
                "mode": mode,
                "horizon": pb.horizon,
                "proposals": proposals,
            },
            notes="Scheduled review.",
        )
        reviewed += 1

    return {"reviewed": reviewed, "proposals": proposed}


__all__ = ["run_manage_playbook_reviews"]

