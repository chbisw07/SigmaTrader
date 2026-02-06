from __future__ import annotations

import json
import os

from app.core.auth import hash_password
from app.core.config import get_settings
from app.core.crypto import encrypt_token
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import BrokerConnection, SystemEvent, User


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-zerodha-status-postback-diagnostics"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_zerodha_status_includes_postback_diagnostics(monkeypatch) -> None:
    settings = get_settings()

    import app.api.zerodha as mod

    class _FakeKite:
        def profile(self):
            return {"user_id": "AB1234", "user_name": "Test User"}

    monkeypatch.setattr(mod, "_get_kite_for_user", lambda *_a, **_k: _FakeKite())

    with SessionLocal() as db:
        user = User(
            username="diag-user",
            password_hash=hash_password("pw"),
            role="TRADER",
            display_name="Diag User",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        db.add(
            BrokerConnection(
                user_id=int(user.id),
                broker_name="zerodha",
                access_token_encrypted=encrypt_token(settings, "access-token"),
                broker_user_id="AB1234",
            )
        )
        db.add(
            SystemEvent(
                level="INFO",
                category="zerodha_postback",
                message="Zerodha postback received",
                details=json.dumps({"updated_order": True}),
            )
        )
        db.add(
            SystemEvent(
                level="WARNING",
                category="zerodha_postback_error",
                message="Zerodha postback rejected",
                details=json.dumps({"status_code": 401, "detail": "Invalid postback signature."}),
            )
        )
        db.add(
            SystemEvent(
                level="INFO",
                category="zerodha_postback_noise",
                message="Zerodha postback ignored (missing signature)",
                details=json.dumps({"status_code": 401, "detail": "Missing postback signature header."}),
            )
        )
        db.commit()

        status = mod.zerodha_status(db=db, settings=settings, user=user)
        assert status["connected"] is True
        assert "last_postback_at" in status
        assert "last_postback_details" in status
        assert "last_postback_reject_at" in status
        assert "last_postback_reject_details" in status
        assert "last_postback_noise_at" in status
        assert "last_postback_noise_details" in status

