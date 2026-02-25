from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Order, User
from app.services.risk_unified_store import upsert_unified_risk_global

client = TestClient(app)


def _hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "no-trade-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            User(
                username="no-trade-user",
                password_hash=hash_password("no-trade-password"),
                role="TRADER",
                display_name="No Trade User",
            )
        )
        session.commit()


def _create_waiting_order(*, side: str = "BUY") -> int:
    payload: Dict[str, Any] = {
        "secret": "no-trade-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "no-trade-user",
        "strategy_name": f"no-trade-test-{uuid4().hex}",
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": side, "quantity": 1, "price": 1500.0},
    }
    resp = client.post("/webhook/tradingview", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    return int(data["order_id"])


def test_auto_dispatch_is_deferred_during_no_trade_window(monkeypatch: Any) -> None:
    # Create a rule window that includes "now" in IST.
    now_utc = datetime.now(UTC)
    try:
        from zoneinfo import ZoneInfo

        now_ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now_ist = now_utc
    start = now_ist - timedelta(minutes=1)
    end = now_ist + timedelta(minutes=1)
    rules = f"{_hhmm(start)}-{_hhmm(end)} NO_TRADE CNC_BUY"

    with SessionLocal() as session:
        upsert_unified_risk_global(
            session,
            enabled=False,
            manual_override_enabled=False,
            baseline_equity_inr=1_000_000.0,
            no_trade_rules=rules,
        )

    order_id = _create_waiting_order(side="BUY")

    from app.api import orders as orders_api

    def _fail_get_client(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Broker client must not be created during NO_TRADE deferral.")

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fail_get_client)

    resp = client.post(f"/api/orders/{order_id}/execute?auto_dispatch=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "WAITING"
    assert data["mode"] == "MANUAL"
    assert "NO_TRADE" in (data.get("error_message") or "")

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "WAITING"
        assert order.mode == "MANUAL"
        assert "NO_TRADE" in (order.error_message or "")

