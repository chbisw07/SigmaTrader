from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.auth import hash_password
from app.core.config import get_settings
from app.core.crypto import encrypt_token
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import BrokerConnection, BrokerSecret, Order, User


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _seed_base() -> dict[str, Any]:
    os.environ.setdefault("ST_CRYPTO_KEY", "test-zerodha-postback-crypto-key")
    get_settings.cache_clear()
    Base.metadata.create_all(bind=engine, checkfirst=True)
    settings = get_settings()

    with SessionLocal() as db:
        # Keep tests isolated without DDL (faster + avoids sqlite locking issues).
        db.query(Order).delete()
        db.query(BrokerConnection).delete()
        db.query(BrokerSecret).delete()
        db.query(User).delete()
        db.commit()

        user = User(
            username=f"postback-user-{uuid4().hex[:8]}",
            password_hash=hash_password("pw"),
            role="TRADER",
            display_name="Postback User",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        api_key = "A" * 16
        api_secret = "secret123"

        db.add(
            BrokerSecret(
                user_id=int(user.id),
                broker_name="zerodha",
                key="api_key",
                value_encrypted=encrypt_token(settings, api_key),
            )
        )
        db.add(
            BrokerSecret(
                user_id=int(user.id),
                broker_name="zerodha",
                key="api_secret",
                value_encrypted=encrypt_token(settings, api_secret),
            )
        )
        db.add(
            BrokerConnection(
                user_id=int(user.id),
                broker_name="zerodha",
                access_token_encrypted=encrypt_token(settings, "access-token"),
                broker_user_id="AB1234",
            )
        )

        order = Order(
            user_id=int(user.id),
            broker_name="zerodha",
            broker_order_id="230101000001234",
            zerodha_order_id="230101000001234",
            symbol="TCS",
            exchange="NSE",
            side="BUY",
            qty=1,
            price=100.0,
            order_type="LIMIT",
            product="MIS",
            gtt=False,
            status="SENT",
            mode="AUTO",
            execution_target="LIVE",
            simulated=False,
            risk_spec_json=None,
            is_exit=False,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        return {
            "api_secret": api_secret,
            "order_id": str(order.broker_order_id),
        }


def test_zerodha_postback_rejects_invalid_signature(monkeypatch) -> None:
    _seed_base()
    settings = get_settings()

    import app.api.zerodha as mod

    # Ensure we never hit the broker from this test.
    monkeypatch.setattr(mod, "_sync_positions_after_postback", lambda *_a, **_k: False)

    body = b"order_id=230101000001234&status=COMPLETE"
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as excinfo:
            mod._handle_zerodha_postback(db, settings, body=body, signature="bad")
        assert excinfo.value.status_code == 401


def test_zerodha_postback_updates_order_and_triggers_positions_sync(monkeypatch) -> None:
    seed = _seed_base()
    settings = get_settings()

    import app.api.zerodha as mod

    calls = {"sync": 0}

    def _fake_sync(*_a, **_k) -> bool:
        calls["sync"] += 1
        return True

    monkeypatch.setattr(mod, "_sync_positions_after_postback", _fake_sync)

    body = b"order_id=230101000001234&status=COMPLETE&filled_quantity=1&average_price=100"
    sig = _sign(body, str(seed["api_secret"]))

    with SessionLocal() as db:
        res = mod._handle_zerodha_postback(db, settings, body=body, signature=sig)

    assert res["ok"] is True
    assert res["updated_order"] is True
    assert res["updated_positions"] is True
    assert calls["sync"] == 1

    with SessionLocal() as db:
        order = (
            db.query(Order)
            .filter(
                Order.broker_name == "zerodha",
                Order.broker_order_id == str(seed["order_id"]),
            )
            .one()
        )
        assert order.status == "EXECUTED"

