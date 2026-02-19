from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.main import app
from app.schemas.ai_trading_manager import BrokerPosition, BrokerSnapshot
from app.services.ai_trading_manager import audit_store

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    os.environ["ST_CRYPTO_KEY"] = "test-ai-tm-coverage"
    os.environ["ST_HASH_SALT"] = "test-hash-salt"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_coverage_sync_creates_and_closes_shadows() -> None:
    now = datetime(2026, 2, 19, 12, 0, 0, tzinfo=UTC)
    with SessionLocal() as db:
        snap = BrokerSnapshot(
            as_of_ts=now,
            account_id="default",
            source="kite_mcp",
            holdings=[
                {
                    "tradingsymbol": "INFY",
                    "quantity": 10,
                    "average_price": 100.0,
                    "last_price": 110.0,
                    "pnl": 100.0,
                    "instrument_token": 123,
                }
            ],
            positions=[
                BrokerPosition(symbol="SBIN", product="MIS", qty=5, avg_price=500.0),
            ],
            orders=[],
            margins={},
            quotes_cache=[],
        )
        audit_store.persist_broker_snapshot(db, snap, user_id=None)

    res = client.post("/api/ai/coverage/sync?account_id=default")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["open_total"] == 2
    assert body["unmanaged_open"] == 2

    rows = client.get("/api/ai/coverage/shadows?account_id=default&status_filter=OPEN").json()
    assert len(rows) == 2
    syms = sorted([r["symbol"] for r in rows])
    assert syms == ["INFY", "SBIN"]

    # New snapshot missing SBIN should close that shadow.
    now2 = datetime(2026, 2, 19, 12, 5, 0, tzinfo=UTC)
    with SessionLocal() as db:
        snap2 = BrokerSnapshot(
            as_of_ts=now2,
            account_id="default",
            source="kite_mcp",
            holdings=[
                {
                    "tradingsymbol": "INFY",
                    "quantity": 10,
                    "average_price": 100.0,
                    "last_price": 110.0,
                    "pnl": 100.0,
                }
            ],
            positions=[],
            orders=[],
            margins={},
            quotes_cache=[],
        )
        audit_store.persist_broker_snapshot(db, snap2, user_id=None)

    res2 = client.post("/api/ai/coverage/sync?account_id=default")
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["open_total"] == 1

    open_rows = client.get("/api/ai/coverage/shadows?account_id=default&status_filter=OPEN").json()
    assert len(open_rows) == 1
    assert open_rows[0]["symbol"] == "INFY"

