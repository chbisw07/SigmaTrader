from __future__ import annotations

import os
from typing import Any, Dict, List
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Order, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "amo-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Create a dedicated user that webhook alerts can be routed to.
    with SessionLocal() as session:
        user = User(
            username="amo-user",
            password_hash=hash_password("amo-password"),
            role="TRADER",
            display_name="AMO User",
        )
        session.add(user)
        session.commit()


def _create_waiting_order() -> int:
    payload: Dict[str, Any] = {
        "secret": "amo-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "amo-user",
        "strategy_name": f"amo-test-strategy-{uuid4().hex}",
        "symbol": "NSE:INFY",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {"order_action": "BUY", "quantity": 1, "price": 1500.0},
    }
    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    data = response.json()
    return data["order_id"]


class _DummyResult:
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id


class _FailOnceThenSuccessClient:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._first = True

    def place_order(self, **params: Any) -> _DummyResult:
        self.calls.append(params)
        if self._first:
            self._first = False
            # Message mimics Zerodha off-market hours error.
            raise Exception(
                "MIS (intraday) are blocked as the markets are not open for "
                "trading today. Try placing an AMO order."
            )
        return _DummyResult(order_id="AMO123")


class _AlwaysFailClient:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def place_order(self, **params: Any) -> _DummyResult:
        self.calls.append(params)
        raise Exception("Some other Zerodha error")


def test_execute_order_retries_as_amo_on_off_hours_error(monkeypatch: Any) -> None:
    order_id = _create_waiting_order()

    from app.api import orders as orders_api

    client_fake = _FailOnceThenSuccessClient()

    def _fake_get_client(db: Any, settings: Any) -> _FailOnceThenSuccessClient:
        return client_fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    response = client.post(f"/api/orders/{order_id}/execute")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SENT"
    assert data["zerodha_order_id"] == "AMO123"

    # Ensure we tried regular first, then AMO.
    assert len(client_fake.calls) == 2
    assert client_fake.calls[0]["variety"] == "regular"
    assert client_fake.calls[1]["variety"] == "amo"

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "SENT"
        assert order.zerodha_order_id == "AMO123"
        assert order.error_message is None


def test_execute_order_does_not_retry_for_other_errors(monkeypatch: Any) -> None:
    order_id = _create_waiting_order()

    from app.api import orders as orders_api

    client_fake = _AlwaysFailClient()

    def _fake_get_client(db: Any, settings: Any) -> _AlwaysFailClient:
        return client_fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    response = client.post(f"/api/orders/{order_id}/execute")
    assert response.status_code == 502
    body = response.json()
    assert "Zerodha order placement failed" in body["detail"]

    assert len(client_fake.calls) == 1
    assert client_fake.calls[0]["variety"] == "regular"

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "FAILED"
        assert "Some other Zerodha error" in (order.error_message or "")
