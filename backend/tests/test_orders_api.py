from __future__ import annotations

import os
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Order

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "queue-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _create_order_via_webhook() -> int:
    payload = {
        "secret": "queue-secret",
        "platform": "TRADINGVIEW",
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
