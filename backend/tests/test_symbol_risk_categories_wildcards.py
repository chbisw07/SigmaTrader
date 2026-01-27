from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import SymbolRiskCategory, User
from app.services.risk_engine_v2 import resolve_symbol_category

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client.post(
        "/api/auth/register",
        json={"username": "cat-user", "password": "cat-pass", "display_name": "Cat User"},
    )
    client.post("/api/auth/login", json={"username": "cat-user", "password": "cat-pass"})


def test_symbol_category_wildcards_resolve_by_latest_update() -> None:
    now = datetime.now(UTC)

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "cat-user").one()
        db.query(SymbolRiskCategory).delete()
        db.commit()

        exact = SymbolRiskCategory(
            user_id=user.id,
            broker_name="zerodha",
            exchange="NSE",
            symbol="TCS",
            risk_category="MC",
        )
        exact.updated_at = now - timedelta(days=1)
        global_row = SymbolRiskCategory(
            user_id=user.id,
            broker_name="*",
            exchange="*",
            symbol="TCS",
            risk_category="LC",
        )
        global_row.updated_at = now
        db.add_all([exact, global_row])
        db.commit()

        resolved = resolve_symbol_category(
            db,
            user_id=user.id,
            broker_name="angelone",
            symbol="TCS",
            exchange="BSE",
        )
        assert resolved == "LC"

        # If the exact mapping is updated later, it should win.
        exact.updated_at = now + timedelta(seconds=1)
        db.add(exact)
        db.commit()

        resolved2 = resolve_symbol_category(
            db,
            user_id=user.id,
            broker_name="zerodha",
            symbol="TCS",
            exchange="NSE",
        )
        assert resolved2 == "MC"


def test_symbol_categories_api_bulk_and_list_include_global_rows() -> None:
    bulk = client.put(
        "/api/risk-engine/symbol-categories/bulk",
        json=[
            {
                "broker_name": "*",
                "exchange": "*",
                "symbol": "INFY",
                "risk_category": "SC",
            }
        ],
    )
    assert bulk.status_code == 200
    payload = bulk.json()
    assert len(payload) == 1
    assert payload[0]["symbol"] == "INFY"
    assert payload[0]["broker_name"] == "*"
    assert payload[0]["exchange"] == "*"
    assert payload[0]["risk_category"] == "SC"

    listed = client.get("/api/risk-engine/symbol-categories", params={"broker_name": "zerodha"})
    assert listed.status_code == 200
    items = listed.json()
    assert any(i["symbol"] == "INFY" and i["broker_name"] == "*" for i in items)

