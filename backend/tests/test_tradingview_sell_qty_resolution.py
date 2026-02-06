from __future__ import annotations

import os

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import User
from app.services.tradingview_sell_qty import resolve_tradingview_sell_qty


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-tv-sell-qty-resolution"
    get_settings.cache_clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_sell_qty_resolves_from_t1_holdings(monkeypatch) -> None:
    settings = get_settings()

    import app.api.orders as orders_api

    class _FakeClient:
        def list_holdings(self):
            return [
                {
                    "tradingsymbol": "INFY",
                    "quantity": 0,
                    "t1_quantity": 7,
                }
            ]

        def list_positions(self):
            return {"net": []}

    def _fake_get_broker_client(db, settings, broker_name, user_id=None):
        return _FakeClient()

    monkeypatch.setattr(orders_api, "_get_broker_client", _fake_get_broker_client)

    with SessionLocal() as db:
        user = User(
            id=1,  # type: ignore[arg-type]
            username="test",
            password_hash="x",
            role="TRADER",
            display_name="Test",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        res = resolve_tradingview_sell_qty(
            db,
            settings,
            user=user,
            broker_name="zerodha",
            exchange="NSE",
            symbol="INFY",
            desired_product="MIS",
            payload_qty=1.0,
        )

        assert res.reject is False
        assert res.checked_live is True
        assert res.source == "holdings"
        assert float(res.qty) == 7.0
        assert str(res.resolved_product).upper() == "CNC"


def test_sell_qty_can_match_holdings_when_exchange_differs(monkeypatch) -> None:
    settings = get_settings()

    import app.api.orders as orders_api

    class _FakeClient:
        def list_holdings(self):
            return [
                {
                    "tradingsymbol": "ACMESOLAR",
                    "exchange": "BSE",
                    "quantity": 5,
                    "t1_quantity": 2,
                }
            ]

        def list_positions(self):
            return {"net": []}

    def _fake_get_broker_client(db, settings, broker_name, user_id=None):
        return _FakeClient()

    monkeypatch.setattr(orders_api, "_get_broker_client", _fake_get_broker_client)

    with SessionLocal() as db:
        user = User(
            id=2,  # type: ignore[arg-type]
            username="test2",
            password_hash="x",
            role="TRADER",
            display_name="Test2",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        res = resolve_tradingview_sell_qty(
            db,
            settings,
            user=user,
            broker_name="zerodha",
            exchange="NSE",
            symbol="ACMESOLAR",
            desired_product="MIS",
            payload_qty=1.0,
        )

        assert res.reject is False
        assert res.checked_live is True
        assert res.source == "holdings"
        assert float(res.qty) == 7.0
        assert str(res.resolved_exchange).upper() == "BSE"
        assert "Matched holdings on BSE" in (res.note or "")

