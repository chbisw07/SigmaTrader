from __future__ import annotations

import os
import types

from app.core.config import get_settings
from app.core.crypto import encrypt_token
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import BrokerConnection, BrokerSecret, User


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-zerodha-holdings-t1"
    get_settings.cache_clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_zerodha_holdings_quantity_includes_t1_quantity(monkeypatch) -> None:
    settings = get_settings()

    with SessionLocal() as db:
        user = User(username="u1", password_hash="x", role="ADMIN", display_name="u1")
        db.add(user)
        db.commit()
        db.refresh(user)

        db.add(
            BrokerConnection(
                user_id=int(user.id),
                broker_name="zerodha",
                broker_user_id="FAKE",
                access_token_encrypted=encrypt_token(settings, "access-token"),
            )
        )
        db.add(
            BrokerSecret(
                user_id=int(user.id),
                broker_name="zerodha",
                key="api_key",
                value_encrypted=encrypt_token(settings, "api-key"),
            )
        )
        db.commit()

    class _FakeKite:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key
            self.access_token: str | None = None

        def set_access_token(self, access_token: str) -> None:
            self.access_token = access_token

        def holdings(self):
            return [
                {
                    "tradingsymbol": "AXISCADES",
                    "exchange": "NSE",
                    "quantity": 0,
                    "t1_quantity": 13,
                    "average_price": 1140.0,
                    "last_price": 1123.5,
                    "day_change_percentage": -1.45,
                }
            ]

        def ltp(self, instruments: list[str]):
            # KiteConnect.ltp returns a mapping keyed by instrument code.
            return {
                instruments[0]: {
                    "last_price": 1123.5,
                    "ohlc": {"close": 1140.0},
                }
            }

    import sys

    fake_mod = types.ModuleType("kiteconnect")
    fake_mod.KiteConnect = _FakeKite  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "kiteconnect", fake_mod)

    from app.api.positions import list_holdings

    with SessionLocal() as db:
        holdings = list_holdings(
            broker_name="zerodha",
            db=db,
            settings=get_settings(),
            user=db.query(User).filter(User.username == "u1").one(),
        )

    assert len(holdings) == 1
    assert holdings[0].symbol == "AXISCADES"
    assert holdings[0].quantity == 13.0
