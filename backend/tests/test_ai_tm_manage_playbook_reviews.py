from __future__ import annotations

import os
from datetime import UTC, datetime

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.ai_trading_manager import AiTmManagePlaybook, AiTmPositionShadow
from app.services.ai_trading_manager.manage_playbook_reviews import run_manage_playbook_reviews
from app.services.ai_trading_manager.journal import list_journal_events


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    os.environ["ST_CRYPTO_KEY"] = "test-ai-tm-playbook-reviews"
    os.environ["ST_HASH_SALT"] = "test-hash-salt"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_reviews_create_review_events_and_proposals() -> None:
    settings = get_settings()
    now = datetime(2026, 2, 19, 12, 0, 0, tzinfo=UTC)
    with SessionLocal() as db:
        s = AiTmPositionShadow(
            shadow_id="sh1",
            broker_account_id="default",
            symbol="SBIN",
            product="CNC",
            side="LONG",
            qty_current=100.0,
            avg_price=100.0,
            first_seen_at=now,
            last_seen_at=now,
            source="BROKER_DIRECT",
            status="OPEN",
            st_trade_id=None,
            broker_position_key_hash="k1",
            broker_instrument_id_hash=None,
            ltp=110.0,
            pnl_abs=1000.0,
            pnl_pct=10.0,
            created_at=now,
            updated_at=now,
        )
        db.add(s)
        db.add(
            AiTmManagePlaybook(
                playbook_id="pb1",
                scope_type="POSITION",
                scope_key="sh1",
                enabled=True,
                mode="PROPOSE",
                horizon="SWING",
                review_cadence_min=1,
                exit_policy_json='{"protective_stop":{"type":"FIXED_PCT","pct":2.0},"take_profit":{"type":"LADDER","steps":[{"pct":3.0,"exit_pct":33}]}}',
                scale_policy_json='{"strategy_exit_partial_pct":0.5}',
                execution_style="LIMIT_BBO",
                allow_strategy_exits=True,
                behavior_on_strategy_exit="ALLOW_AS_IS",
                notes=None,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        out = run_manage_playbook_reviews(db, settings, account_id="default")
        assert out["reviewed"] == 1
        assert out["proposals"] >= 1

        evs = list_journal_events(db, shadow_id="sh1", limit=20, offset=0)
        assert any(e.get("event_type") == "REVIEW" for e in evs)
        review = next(e for e in evs if e.get("event_type") == "REVIEW")
        pb_res = review.get("playbook_result") or {}
        assert pb_res.get("playbook_id") == "pb1"
        assert isinstance(pb_res.get("proposals"), list)

