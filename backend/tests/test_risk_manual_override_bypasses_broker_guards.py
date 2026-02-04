from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.crypto import encrypt_token
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import BrokerConnection, Order, User
from app.services.risk_unified_store import upsert_unified_risk_global

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-manual-override"
    get_settings.cache_clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_manual_override_skips_broker_aware_guards(monkeypatch) -> None:
    settings = get_settings()

    with SessionLocal() as db:
        user = User(username="u1", password_hash="x", role="ADMIN", display_name="u1")
        db.add(user)
        db.commit()
        db.refresh(user)

        # Enable enforcement + manual override (manual orders only).
        upsert_unified_risk_global(
            db,
            enabled=True,
            manual_override_enabled=True,
            baseline_equity_inr=1_000_000.0,
        )

        # Seed a zerodha broker connection so execute flow doesn't fail early on
        # "not connected" validations in other code paths.
        db.add(
            BrokerConnection(
                user_id=int(user.id),
                broker_name="zerodha",
                broker_user_id="FAKE",
                access_token_encrypted=encrypt_token(settings, "fake-token"),
            )
        )

        order = Order(
            user_id=int(user.id),
            broker_name="zerodha",
            symbol="NSE:INFY",
            exchange="NSE",
            side="BUY",
            qty=1.0,
            product="MIS",
            order_type="MARKET",
            status="WAITING",
            mode="MANUAL",
            simulated=False,
            gtt=False,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        order_id = int(order.id)

    class _Result:
        def __init__(self, order_id: str):
            self.order_id = order_id

    class _FakeBrokerClient:
        broker_user_id = "FAKE"

        def get_quote_bulk(self, *_a, **_k):
            raise AssertionError("broker-aware guards should be bypassed for manual override")

        def get_ltp(self, *_a, **_k):
            raise AssertionError("broker-aware guards should be bypassed for manual override")

        def place_order(self, *_a, **_k):
            return _Result("FAKE-ORDER-ID")

    import app.api.orders as orders_mod

    monkeypatch.setattr(orders_mod, "_get_broker_client", lambda *_a, **_k: _FakeBrokerClient())

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SENT"
    assert data["broker_order_id"] == "FAKE-ORDER-ID"

