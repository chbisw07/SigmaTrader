from __future__ import annotations

import os

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.ai_trading_manager.execution.idempotency_store import IdempotencyStore


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_idempotency_begin_dedupes_by_account_and_key() -> None:
    store = IdempotencyStore()
    with SessionLocal() as db:
        r1 = store.begin(db, user_id=None, account_id="default", key="k1", payload_hash="h1")
        r2 = store.begin(db, user_id=None, account_id="default", key="k1", payload_hash="h1")

        assert r1.created is True
        assert r2.created is False
        assert r1.record.id == r2.record.id

