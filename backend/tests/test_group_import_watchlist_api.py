from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import MarketInstrument

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.add_all(
            [
                MarketInstrument(
                    symbol="ACUTAAS",
                    exchange="NSE",
                    instrument_token="111",
                    name="ACUTAAS",
                    active=True,
                ),
                MarketInstrument(
                    symbol="BHEL",
                    exchange="NSE",
                    instrument_token="222",
                    name="BHEL",
                    active=True,
                ),
            ]
        )
        db.commit()


def test_import_watchlist_skips_disallowed_columns_and_unknown_symbols() -> None:
    payload = {
        "group_name": "tv-watchlist",
        "symbol_column": "Symbol",
        "exchange_column": None,
        "default_exchange": "NSE",
        "selected_columns": ["Sector", "Close"],
        "header_labels": {"Symbol": "Symbol", "Sector": "Sector", "Close": "Close"},
        "rows": [
            {"Symbol": "ACUTAAS", "Sector": "Pharma", "Close": "123.45"},
            {"Symbol": "BHEL", "Sector": "Industrials", "Close": "999"},
            {"Symbol": "MISSING", "Sector": "Unknown", "Close": "1"},
        ],
        "allow_kite_fallback": False,
        "conflict_mode": "ERROR",
    }
    res = client.post("/api/groups/import/watchlist", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["imported_members"] == 2
    assert data["imported_columns"] == 1
    assert len(data["skipped_columns"]) == 1
    assert len(data["skipped_symbols"]) == 1

    group_id = data["group_id"]

    # Dataset schema exists and includes the imported metadata column.
    res = client.get(f"/api/groups/{group_id}/dataset")
    assert res.status_code == 200
    ds = res.json()
    assert len(ds["columns"]) == 1
    assert ds["columns"][0]["label"] == "Sector"

    # Values exist for the resolved symbols only.
    res = client.get(f"/api/groups/{group_id}/dataset/values")
    assert res.status_code == 200
    vals = res.json()["items"]
    assert len(vals) == 2
    symbols = sorted((v["symbol"], v["exchange"]) for v in vals)
    assert symbols == [("ACUTAAS", "NSE"), ("BHEL", "NSE")]


def test_import_watchlist_conflict_mode_replace_dataset() -> None:
    # First import.
    res = client.post(
        "/api/groups/import/watchlist",
        json={
            "group_name": "tv-watchlist-2",
            "symbol_column": "Symbol",
            "default_exchange": "NSE",
            "selected_columns": ["Sector"],
            "header_labels": {"Symbol": "Symbol", "Sector": "Sector"},
            "rows": [{"Symbol": "ACUTAAS", "Sector": "One"}],
            "allow_kite_fallback": False,
            "conflict_mode": "ERROR",
        },
    )
    assert res.status_code == 200
    group_id = res.json()["group_id"]

    # Conflict without replace -> 400.
    res = client.post(
        "/api/groups/import/watchlist",
        json={
            "group_name": "tv-watchlist-2",
            "symbol_column": "Symbol",
            "default_exchange": "NSE",
            "selected_columns": ["Sector"],
            "header_labels": {"Symbol": "Symbol", "Sector": "Sector"},
            "rows": [{"Symbol": "ACUTAAS", "Sector": "Two"}],
            "allow_kite_fallback": False,
            "conflict_mode": "ERROR",
        },
    )
    assert res.status_code == 400

    # Replace dataset -> ok and values updated.
    res = client.post(
        "/api/groups/import/watchlist",
        json={
            "group_name": "tv-watchlist-2",
            "symbol_column": "Symbol",
            "default_exchange": "NSE",
            "selected_columns": ["Sector"],
            "header_labels": {"Symbol": "Symbol", "Sector": "Sector"},
            "rows": [{"Symbol": "ACUTAAS", "Sector": "Two"}],
            "allow_kite_fallback": False,
            "conflict_mode": "REPLACE_DATASET",
            "replace_members": True,
        },
    )
    assert res.status_code == 200
    assert res.json()["group_id"] == group_id

    res = client.get(f"/api/groups/{group_id}/dataset/values")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    values = items[0]["values"]
    # Column key is slugified from label ("sector").
    assert values.get("sector") == "Two"
