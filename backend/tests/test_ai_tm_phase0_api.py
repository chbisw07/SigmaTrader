from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Position

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    # Keep monitoring off for Phase 0; endpoints exist but require the flag.
    os.environ["ST_MONITORING_ENABLED"] = "0"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_post_message_persists_thread_and_trace() -> None:
    resp = client.post("/api/ai/messages", json={"account_id": "default", "content": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("decision_id"), str) and data["decision_id"]
    thread = data["thread"]
    assert thread["account_id"] == "default"
    assert len(thread["messages"]) >= 2

    decision_id = data["decision_id"]
    trace_resp = client.get(f"/api/ai/decision-traces/{decision_id}")
    assert trace_resp.status_code == 200
    trace = trace_resp.json()
    assert trace["decision_id"] == decision_id
    assert trace["user_message"] == "hello"

    threads = client.get("/api/ai/threads?account_id=default&limit=50")
    assert threads.status_code == 200
    rows = threads.json()
    assert any(r.get("thread_id") == "default" for r in rows)
    default_row = next(r for r in rows if r.get("thread_id") == "default")
    assert default_row.get("message_count", 0) >= 2
    assert "hello" in str(default_row.get("title") or "").lower()

    created = client.post("/api/ai/threads?account_id=default")
    assert created.status_code == 200
    payload = created.json()
    assert payload.get("thread_id")


def test_reconcile_creates_exception_for_position_mismatch() -> None:
    # Seed an expected position in the ST ledger (DB) so stub broker snapshot (empty)
    # produces a deterministic mismatch.
    with SessionLocal() as db:
        db.add(
            Position(
                broker_name="zerodha",
                symbol="INFY",
                exchange="NSE",
                product="CNC",
                qty=10,
                avg_price=1500.0,
                pnl=0.0,
                last_updated=datetime.now(UTC),
            )
        )
        db.commit()

    resp = client.post("/api/ai/reconcile?account_id=default")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["run_id"]
    assert payload["decision_id"]
    deltas = payload["deltas"]
    assert any(d["delta_type"] in {"POSITION_MISSING_AT_BROKER", "POSITION_QTY_MISMATCH"} for d in deltas)

    ex_resp = client.get("/api/ai/exceptions?account_id=default&status_filter=OPEN&limit=50")
    assert ex_resp.status_code == 200
    ex_rows = ex_resp.json()
    assert len(ex_rows) >= 1
    assert any(r["exception_type"].startswith("POSITION_") for r in ex_rows)
