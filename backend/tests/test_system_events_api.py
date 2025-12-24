from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import SystemEvent
from app.services.system_events import record_system_event

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "events-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        record_system_event(
            session,
            level="INFO",
            category="alert",
            message="Test alert event",
            correlation_id="test-corr-id",
            details={"foo": "bar"},
        )


def test_list_system_events_returns_recent_entries() -> None:
    resp = client.get("/api/system-events/?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    first = data[0]
    assert first["category"] == "alert"
    assert first["message"] == "Test alert event"
    assert first["correlation_id"] == "test-corr-id"


def test_cleanup_system_events_removes_older_than_retention() -> None:
    with SessionLocal() as session:
        session.query(SystemEvent).delete()
        session.commit()
        session.add_all(
            [
                SystemEvent(
                    level="INFO",
                    category="test",
                    message="old",
                    created_at=datetime.now(UTC) - timedelta(days=30),
                ),
                SystemEvent(
                    level="INFO",
                    category="test",
                    message="new",
                    created_at=datetime.now(UTC) - timedelta(days=1),
                ),
            ]
        )
        session.commit()

    resp = client.post("/api/system-events/cleanup", json={"max_days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] >= 1

    remaining = client.get("/api/system-events/?limit=50").json()
    messages = [r["message"] for r in remaining]
    assert "old" not in messages
    assert "new" in messages
