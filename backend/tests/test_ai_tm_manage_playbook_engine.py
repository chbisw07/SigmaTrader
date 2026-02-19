from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.ai_trading_manager import AiTmJournalEvent, AiTmManagePlaybook, AiTmPositionShadow
from app.schemas.ai_trading_manager import PlaybookDecisionKind
from app.services.ai_trading_manager.manage_playbook_engine import IntentContext, evaluate_playbook_pretrade


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    os.environ["ST_CRYPTO_KEY"] = "test-ai-tm-playbook"
    os.environ["ST_HASH_SALT"] = "test-hash-salt"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _mk_shadow(db, *, qty: float = 10.0) -> AiTmPositionShadow:
    now = datetime.now(UTC)
    shadow_id = uuid4().hex
    s = AiTmPositionShadow(
        shadow_id=shadow_id,
        broker_account_id="default",
        symbol="SBIN",
        product="CNC",
        side="LONG",
        qty_current=float(qty),
        avg_price=100.0,
        first_seen_at=now,
        last_seen_at=now,
        source="BROKER_DIRECT",
        status="OPEN",
        st_trade_id=None,
        broker_position_key_hash=f"k-{shadow_id}",
        broker_instrument_id_hash=None,
        ltp=101.0,
        pnl_abs=10.0,
        pnl_pct=1.0,
        created_at=now,
        updated_at=now,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_playbook_disabled_is_noop() -> None:
    with SessionLocal() as db:
        shadow = _mk_shadow(db, qty=10.0)
        pb = AiTmManagePlaybook(
            playbook_id="pb1",
            scope_type="POSITION",
            scope_key=shadow.shadow_id,
            enabled=False,
            mode="OBSERVE",
            horizon="SWING",
            review_cadence_min=60,
            exit_policy_json="{}",
            scale_policy_json="{}",
            execution_style="LIMIT_BBO",
            allow_strategy_exits=True,
            behavior_on_strategy_exit="ALLOW_AS_IS",
            notes=None,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(pb)
        db.commit()

        dec = evaluate_playbook_pretrade(
            db,
            shadow=shadow,
            intent=IntentContext(intent_type="EXIT", source="TV_ALERT", symbol="SBIN", product="CNC", qty=5.0),
        )
        assert dec.decision == PlaybookDecisionKind.allow
        assert dec.adjustments == {}


def test_tv_exit_can_convert_to_partial_when_enabled() -> None:
    with SessionLocal() as db:
        shadow = _mk_shadow(db, qty=20.0)
        pb = AiTmManagePlaybook(
            playbook_id="pb2",
            scope_type="POSITION",
            scope_key=shadow.shadow_id,
            enabled=True,
            mode="OBSERVE",
            horizon="SWING",
            review_cadence_min=60,
            exit_policy_json="{}",
            scale_policy_json='{"strategy_exit_partial_pct":0.5}',
            execution_style="LIMIT_BBO",
            allow_strategy_exits=True,
            behavior_on_strategy_exit="CONVERT_TO_PARTIAL",
            notes=None,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(pb)
        db.commit()

        dec = evaluate_playbook_pretrade(
            db,
            shadow=shadow,
            intent=IntentContext(intent_type="EXIT", source="TV_ALERT", symbol="SBIN", product="CNC", qty=20.0),
        )
        assert dec.decision == PlaybookDecisionKind.adjust
        assert float(dec.adjustments.get("qty")) in {10.0, 10}


def test_exit_invalid_qty_is_blocked_when_enabled() -> None:
    with SessionLocal() as db:
        shadow = _mk_shadow(db, qty=5.0)
        pb = AiTmManagePlaybook(
            playbook_id="pb3",
            scope_type="POSITION",
            scope_key=shadow.shadow_id,
            enabled=True,
            mode="OBSERVE",
            horizon="SWING",
            review_cadence_min=60,
            exit_policy_json="{}",
            scale_policy_json="{}",
            execution_style="LIMIT_BBO",
            allow_strategy_exits=True,
            behavior_on_strategy_exit="ALLOW_AS_IS",
            notes=None,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(pb)
        db.commit()

        dec = evaluate_playbook_pretrade(
            db,
            shadow=shadow,
            intent=IntentContext(intent_type="REDUCE", source="MANUAL_UI", symbol="SBIN", product="CNC", qty=10.0),
        )
        assert dec.decision == PlaybookDecisionKind.block
        assert dec.adjustments.get("reason_code") == "INVALID_QTY"


def test_entry_warns_when_scalein_cap_reached() -> None:
    with SessionLocal() as db:
        shadow = _mk_shadow(db, qty=5.0)
        pb = AiTmManagePlaybook(
            playbook_id="pb4",
            scope_type="POSITION",
            scope_key=shadow.shadow_id,
            enabled=True,
            mode="OBSERVE",
            horizon="SWING",
            review_cadence_min=60,
            exit_policy_json="{}",
            scale_policy_json='{"max_adds_per_day":1}',
            execution_style="LIMIT_BBO",
            allow_strategy_exits=True,
            behavior_on_strategy_exit="ALLOW_AS_IS",
            notes=None,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(pb)

        db.add(
            AiTmJournalEvent(
                event_id="ev1",
                position_shadow_id=shadow.shadow_id,
                ts=datetime.now(UTC) - timedelta(hours=1),
                event_type="ADD",
                source="AI_ASSISTANT",
                intent_payload_json="{}",
                riskgate_result_json="{}",
                playbook_result_json="{}",
                broker_result_json="{}",
                notes=None,
            )
        )
        db.commit()

        dec = evaluate_playbook_pretrade(
            db,
            shadow=shadow,
            intent=IntentContext(intent_type="ADD", source="AI_ASSISTANT", symbol="SBIN", product="CNC", qty=1.0),
        )
        assert dec.decision == PlaybookDecisionKind.warn
        assert dec.adjustments.get("reason_code") == "SCALEIN_CAP_REACHED"
