from __future__ import annotations

import os
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
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "queue-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Create a dedicated user that webhook alerts can be routed to.
    with SessionLocal() as session:
        user = User(
            username="queue-user",
            password_hash=hash_password("queue-password"),
            role="TRADER",
            display_name="Queue User",
        )
        session.add(user)
        session.commit()


def _create_order_via_webhook() -> int:
    payload = {
        "secret": "queue-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "queue-user",
        "strategy_name": f"queue-test-strategy-{uuid4().hex}",
        "symbol": "NSE:TCS",
        "exchange": "NSE",
        "interval": "15",
        "trade_details": {"order_action": "BUY", "quantity": 3, "price": 3500.0},
    }
    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    data = response.json()
    return data["order_id"]


def test_queue_listing_and_cancel_flow() -> None:
    order_id = _create_order_via_webhook()

    # Queue should include the new WAITING order
    resp_queue = client.get("/api/orders/queue")
    assert resp_queue.status_code == 200
    queue_items = resp_queue.json()
    ids = [item["id"] for item in queue_items]
    assert order_id in ids
    item = next(x for x in queue_items if x["id"] == order_id)
    assert item.get("origin") == "TRADINGVIEW"

    # Cancel the order via status update
    resp_cancel = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "CANCELLED"},
    )
    assert resp_cancel.status_code == 200
    cancelled = resp_cancel.json()
    assert cancelled["id"] == order_id
    assert cancelled["status"] == "CANCELLED"

    # Queue listing should no longer include the cancelled order
    resp_queue_after = client.get("/api/orders/queue")
    assert resp_queue_after.status_code == 200
    queue_items_after = resp_queue_after.json()
    ids_after = [item["id"] for item in queue_items_after]
    assert order_id not in ids_after

    # Confirm in DB
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "CANCELLED"


def test_edit_order_in_waiting_queue() -> None:
    order_id = _create_order_via_webhook()

    # Edit qty, price, order_type, and product for the WAITING manual order
    resp_edit = client.patch(
        f"/api/orders/{order_id}",
        json={
            "qty": 5,
            "price": 3600.0,
            "order_type": "LIMIT",
            "product": "CNC",
        },
    )
    assert resp_edit.status_code == 200
    edited = resp_edit.json()
    assert edited["id"] == order_id
    assert edited.get("origin") == "TRADINGVIEW"
    assert edited["qty"] == 5
    assert edited["price"] == 3600.0
    assert edited["order_type"] == "LIMIT"
    assert edited["product"] == "CNC"
    assert edited["status"] == "WAITING"

    # Confirm in DB
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.qty == 5
        assert order.price == 3600.0
        assert order.order_type == "LIMIT"
        assert order.product == "CNC"


def test_edit_order_rounds_price_to_tick() -> None:
    order_id = _create_order_via_webhook()

    resp_edit = client.patch(
        f"/api/orders/{order_id}",
        json={
            "price": 320.29,
            "order_type": "LIMIT",
            "product": "CNC",
        },
    )
    assert resp_edit.status_code == 200
    edited = resp_edit.json()
    assert edited["id"] == order_id
    assert edited["price"] == 320.3

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.price == 320.3


def test_manual_order_cannot_execute_when_broker_not_connected() -> None:
    """Manual WAITING orders should remain in queue if Zerodha is not connected."""

    order_id = _create_order_via_webhook()

    # No BrokerConnection is created in this test. Executing should fail.
    resp_execute = client.post(f"/api/orders/{order_id}/execute")
    assert resp_execute.status_code == 400
    body = resp_execute.json()
    assert "Zerodha is not connected." in body.get("detail", "")

    # Order should still be in WAITING status.
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "WAITING"


def test_move_failed_order_to_waiting_queue_requires_auth_and_succeeds() -> None:
    # Create via webhook so it belongs to queue-user.
    order_id = _create_order_via_webhook()

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        order.status = "FAILED"
        order.mode = "AUTO"
        order.error_message = "Test failure"
        session.add(order)
        session.commit()

    # Authenticate as queue-user (session cookie stored on client).
    login = client.post(
        "/api/auth/login",
        json={"username": "queue-user", "password": "queue-password"},
    )
    assert login.status_code == 200

    moved = client.post(f"/api/orders/{order_id}/move-to-waiting")
    assert moved.status_code == 200
    data = moved.json()
    assert data["id"] != order_id
    assert data["status"] == "WAITING"
    assert data["mode"] == "MANUAL"

    with SessionLocal() as session:
        original = session.get(Order, order_id)
        assert original is not None
        assert original.status == "FAILED"
        assert original.mode == "AUTO"
