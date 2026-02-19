from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.ai_trading_manager import AiTmJournalEvent, AiTmManagePlaybook, AiTmPositionShadow
from app.schemas.ai_trading_manager import PlaybookDecision, PlaybookDecisionKind


def _json_loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback


@dataclass(frozen=True)
class IntentContext:
    intent_type: str  # ENTRY/ADD/REDUCE/EXIT/STOP_UPDATE
    source: str  # MANUAL_UI/TV_ALERT/AI_ASSISTANT/SYSTEM
    symbol: str
    product: str
    qty: float | None = None
    notes: str | None = None


def _best_playbook_for_shadow(db: Session, *, shadow: AiTmPositionShadow) -> Optional[AiTmManagePlaybook]:
    # Precedence: POSITION -> SYMBOL -> PORTFOLIO_DEFAULT (enabled or disabled; engine will no-op if disabled)
    rows = db.execute(select(AiTmManagePlaybook)).scalars().all()
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


def _recent_event_count(
    db: Session,
    *,
    shadow_id: str,
    event_type: str,
    lookback_hours: int = 24,
) -> int:
    # Best-effort; SQLite timestamp comparisons are ok with UTCDateTime storage.
    since = datetime.now(UTC)
    try:
        from datetime import timedelta

        since = since - timedelta(hours=int(lookback_hours))
    except Exception:
        pass
    rows = db.execute(
        select(AiTmJournalEvent)
        .where(
            AiTmJournalEvent.position_shadow_id == shadow_id,
            AiTmJournalEvent.event_type == event_type,
            AiTmJournalEvent.ts >= since,
        )
        .order_by(desc(AiTmJournalEvent.ts))
    ).scalars().all()
    return len(rows)


def evaluate_playbook_pretrade(
    db: Session,
    *,
    shadow: AiTmPositionShadow | None,
    intent: IntentContext,
) -> PlaybookDecision:
    """Deterministic PlaybookEngine (pre-trade). RiskGate remains supreme.

    If no playbook exists or playbook.enabled=false -> ALLOW with no adjustments.
    """

    if shadow is None:
        return PlaybookDecision(
            decision=PlaybookDecisionKind.allow,
            rationale="No position context; playbook not applied.",
        )

    pb = _best_playbook_for_shadow(db, shadow=shadow)
    if pb is None or not bool(pb.enabled):
        return PlaybookDecision(decision=PlaybookDecisionKind.allow, rationale="Playbook disabled (default).")

    intent_type = str(intent.intent_type or "").upper()
    qty = intent.qty

    # Safety: exits that reduce risk should not be blocked except invalid qty/product/short creation.
    if intent_type in {"REDUCE", "EXIT"}:
        if qty is not None and (qty <= 0 or qty > float(shadow.qty_current or 0.0)):
            return PlaybookDecision(
                decision=PlaybookDecisionKind.block,
                rationale="Invalid reduce/exit quantity for current position.",
                adjustments={"reason_code": "INVALID_QTY"},
            )
        # Strategy exit handling (TV alerts).
        beh = str(pb.behavior_on_strategy_exit or "ALLOW_AS_IS").upper()
        if str(intent.source or "").upper() == "TV_ALERT" and beh == "CONVERT_TO_PARTIAL":
            scale = _json_loads(pb.scale_policy_json or "{}", {})
            pct = float(scale.get("strategy_exit_partial_pct") or 0.5)
            pct = max(0.0, min(1.0, pct))
            target_qty = max(1.0, float(shadow.qty_current or 0.0) * pct)
            adj_qty = int(target_qty) if float(target_qty).is_integer() else float(target_qty)
            return PlaybookDecision(
                decision=PlaybookDecisionKind.adjust,
                rationale="Converted strategy exit to partial per playbook.",
                adjustments={"qty": adj_qty, "behavior_on_strategy_exit": "CONVERT_TO_PARTIAL"},
            )
        return PlaybookDecision(decision=PlaybookDecisionKind.allow, rationale="Risk-reducing intent allowed.")

    if intent_type in {"ENTRY", "ADD"}:
        scale = _json_loads(pb.scale_policy_json or "{}", {})
        max_adds = scale.get("max_adds_per_day")
        if max_adds is not None:
            try:
                max_adds_i = int(max_adds)
                if max_adds_i >= 0:
                    adds = _recent_event_count(db, shadow_id=shadow.shadow_id, event_type="ADD", lookback_hours=24)
                    if adds >= max_adds_i:
                        return PlaybookDecision(
                            decision=PlaybookDecisionKind.warn,
                            rationale="Playbook scale-in cap reached for today; RiskGate still applies.",
                            adjustments={"reason_code": "SCALEIN_CAP_REACHED", "adds_today": adds, "cap": max_adds_i},
                        )
            except Exception:
                pass
        return PlaybookDecision(decision=PlaybookDecisionKind.allow, rationale="Playbook allows entry/add.")

    if intent_type == "STOP_UPDATE":
        return PlaybookDecision(decision=PlaybookDecisionKind.allow, rationale="Stop update allowed.")

    return PlaybookDecision(decision=PlaybookDecisionKind.allow, rationale="Intent allowed.")


__all__ = ["IntentContext", "evaluate_playbook_pretrade"]
