from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app  # noqa: F401  # ensure routes are imported

client = TestClient(app)

def _set_env(**pairs: str) -> None:
    for k, v in pairs.items():
        os.environ[k] = v
    get_settings.cache_clear()


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    _set_env(ST_HOLDINGS_EXIT_ENABLED="1", ST_HOLDINGS_EXIT_ALLOWLIST_SYMBOLS="")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_create_list_pause_resume_and_events() -> None:
    payload = {
        "broker_name": "zerodha",
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "product": "CNC",
        "trigger_kind": "TARGET_ABS_PRICE",
        "trigger_value": 2000.0,
        "price_source": "LTP",
        "size_mode": "PCT_OF_POSITION",
        "size_value": 50.0,
        "min_qty": 1,
        "order_type": "MARKET",
        "dispatch_mode": "MANUAL",
        "execution_target": "LIVE",
        "cooldown_seconds": 300,
    }

    res = client.post("/api/holdings-exit-subscriptions", json=payload)
    assert res.status_code == 200, res.text
    sub = res.json()
    assert sub["symbol"] == "INFY"
    assert sub["exchange"] == "NSE"
    assert sub["status"] == "ACTIVE"

    sub_id = int(sub["id"])

    listed = client.get("/api/holdings-exit-subscriptions").json()
    assert any(int(x["id"]) == sub_id for x in listed)

    paused = client.post(f"/api/holdings-exit-subscriptions/{sub_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "PAUSED"

    resumed = client.post(f"/api/holdings-exit-subscriptions/{sub_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "ACTIVE"
    assert resumed.json()["pending_order_id"] is None

    events = client.get(f"/api/holdings-exit-subscriptions/{sub_id}/events")
    assert events.status_code == 200
    evs = events.json()
    kinds = [e["event_type"] for e in evs]
    # Most recent first, but assert presence regardless of order.
    assert "SUB_CREATED" in kinds
    assert "SUB_PAUSED" in kinds
    assert "SUB_RESUMED" in kinds


def test_create_rejects_unsupported_trigger_kind() -> None:
    payload = {
        "broker_name": "zerodha",
        "symbol": "INFY",
        "exchange": "NSE",
        "product": "CNC",
        "trigger_kind": "DRAWDOWN_ABS_PRICE",
        "trigger_value": 10.0,
        "size_mode": "ABS_QTY",
        "size_value": 1,
        "dispatch_mode": "MANUAL",
    }
    res = client.post("/api/holdings-exit-subscriptions", json=payload)
    assert res.status_code == 400


def test_create_rejects_auto_dispatch() -> None:
    payload = {
        "broker_name": "zerodha",
        "symbol": "INFY",
        "exchange": "NSE",
        "product": "CNC",
        "trigger_kind": "TARGET_ABS_PRICE",
        "trigger_value": 10.0,
        "size_mode": "ABS_QTY",
        "size_value": 1,
        "dispatch_mode": "AUTO",
    }
    res = client.post("/api/holdings-exit-subscriptions", json=payload)
    assert res.status_code == 400


def test_create_dedup_returns_existing_subscription() -> None:
    payload = {
        "broker_name": "zerodha",
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "product": "CNC",
        "trigger_kind": "TARGET_ABS_PRICE",
        "trigger_value": 1234.0,
        "price_source": "LTP",
        "size_mode": "ABS_QTY",
        "size_value": 1.0,
        "min_qty": 1,
        "order_type": "MARKET",
        "dispatch_mode": "MANUAL",
        "execution_target": "LIVE",
        "cooldown_seconds": 300,
    }
    a = client.post("/api/holdings-exit-subscriptions", json=payload)
    assert a.status_code == 200, a.text
    b = client.post("/api/holdings-exit-subscriptions", json=payload)
    assert b.status_code == 200, b.text
    assert int(a.json()["id"]) == int(b.json()["id"])


def test_allowlist_blocks_non_allowed_symbol() -> None:
    _set_env(ST_HOLDINGS_EXIT_ALLOWLIST_SYMBOLS="NSE:TCS")
    try:
        payload = {
            "broker_name": "zerodha",
            "symbol": "NSE:INFY",
            "exchange": "NSE",
            "product": "CNC",
            "trigger_kind": "TARGET_ABS_PRICE",
            "trigger_value": 10.0,
            "size_mode": "ABS_QTY",
            "size_value": 1,
            "dispatch_mode": "MANUAL",
        }
        res = client.post("/api/holdings-exit-subscriptions", json=payload)
        assert res.status_code == 403, res.text
    finally:
        _set_env(ST_HOLDINGS_EXIT_ALLOWLIST_SYMBOLS="")


def test_feature_flag_disabled_returns_400() -> None:
    _set_env(ST_HOLDINGS_EXIT_ENABLED="0")
    try:
        res = client.get("/api/holdings-exit-subscriptions")
        assert res.status_code == 400, res.text
    finally:
        _set_env(ST_HOLDINGS_EXIT_ENABLED="1")
