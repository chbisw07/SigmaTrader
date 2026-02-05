from __future__ import annotations

import os

from app.core.config import get_settings
from app.core.crypto import encrypt_token
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import BrokerSecret, User
from app.services.broker_secrets import get_broker_secret


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_CRYPTO_KEY", "test-broker-secrets-alias-crypto-key")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            User(
                username="bs-user",
                password_hash="x",
                role="TRADER",
                display_name="BS User",
            )
        )
        session.commit()


def test_get_broker_secret_zerodha_alias_matches_case_insensitively() -> None:
    settings = get_settings()
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "bs-user").one()
        session.add(
            BrokerSecret(
                user_id=int(user.id),
                broker_name="zerodha",
                key="zerodha_api_key",
                value_encrypted=encrypt_token(settings, "aaaaaaaaaaaaaaaa"),
            )
        )
        session.add(
            BrokerSecret(
                user_id=int(user.id),
                broker_name="zerodha",
                key="ZERODHA_API_SECRET",
                value_encrypted=encrypt_token(settings, "secret123"),
            )
        )
        session.commit()

        api_key = get_broker_secret(
            session,
            settings,
            broker_name="zerodha",
            key="api_key",
            user_id=int(user.id),
        )
        api_secret = get_broker_secret(
            session,
            settings,
            broker_name="zerodha",
            key="api_secret",
            user_id=int(user.id),
        )
        assert api_key == "aaaaaaaaaaaaaaaa"
        assert api_secret == "secret123"

