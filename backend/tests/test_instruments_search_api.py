from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import BrokerInstrument, Listing, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_CRYPTO_KEY", "test-instruments-search-crypto-key")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Log in so endpoints guarded by get_current_user work.
    client.post(
        "/api/auth/register",
        json={"username": "inst-user", "password": "inst-pass", "email": None},
    )
    client.post("/api/auth/login", json={"username": "inst-user", "password": "inst-pass"})

    with SessionLocal() as session:
        u = session.query(User).filter(User.username == "inst-user").one_or_none()
        if u is None:
            session.add(User(username="inst-user", password_hash=hash_password("inst-pass"), role="TRADER"))
            session.commit()

        # Seed canonical listings + broker instruments.
        session.query(BrokerInstrument).delete()
        session.query(Listing).delete()
        session.commit()

        l1 = Listing(exchange="NSE", symbol="INFY", name="Infosys Ltd", active=True)
        l2 = Listing(exchange="BSE", symbol="BSE", name="BSE Ltd", active=True)
        l3 = Listing(exchange="NSE", symbol="NIFTYBEES", name="Nippon Nifty ETF", active=True)
        session.add_all([l1, l2, l3])
        session.commit()
        session.refresh(l1)
        session.refresh(l2)
        session.refresh(l3)

        session.add_all(
            [
                BrokerInstrument(
                    listing_id=l1.id,
                    broker_name="zerodha",
                    exchange="NSE",
                    broker_symbol="INFY",
                    instrument_token="1001",
                    active=True,
                ),
                BrokerInstrument(
                    listing_id=l2.id,
                    broker_name="zerodha",
                    exchange="BSE",
                    broker_symbol="BSE",
                    instrument_token="2002",
                    active=True,
                ),
                BrokerInstrument(
                    listing_id=l3.id,
                    broker_name="zerodha",
                    exchange="NSE",
                    broker_symbol="NIFTYBEES",
                    instrument_token="3003",
                    active=True,
                ),
            ]
        )
        session.commit()


def test_search_exact_match_case_insensitive() -> None:
    res = client.get("/api/instruments/search?q=infy&limit=20")
    assert res.status_code == 200
    rows = res.json()
    assert any(r["symbol"] == "INFY" and r["exchange"] == "NSE" for r in rows)


def test_search_prefix_match_ranks_first() -> None:
    res = client.get("/api/instruments/search?q=nif&limit=20")
    assert res.status_code == 200
    rows = res.json()
    assert rows
    assert rows[0]["symbol"] == "NIFTYBEES"


def test_search_partial_match_by_name() -> None:
    res = client.get("/api/instruments/search?q=infos&limit=20")
    assert res.status_code == 200
    rows = res.json()
    assert any(r["symbol"] == "INFY" for r in rows)


def test_search_exchange_filter() -> None:
    res = client.get("/api/instruments/search?q=bse&exchange=BSE&limit=20")
    assert res.status_code == 200
    rows = res.json()
    assert rows
    assert all(r["exchange"] == "BSE" for r in rows)

