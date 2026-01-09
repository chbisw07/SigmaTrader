from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Group, GroupMember, MarketInstrument

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


def test_import_watchlist_imports_all_selected_columns_and_skips_unknown_symbols() -> (
    None
):
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
    assert data["imported_columns"] == 2
    assert len(data["skipped_columns"]) == 0
    assert len(data["skipped_symbols"]) == 1

    group_id = data["group_id"]

    # Dataset schema exists and includes the imported metadata column.
    res = client.get(f"/api/groups/{group_id}/dataset")
    assert res.status_code == 200
    ds = res.json()
    assert len(ds["columns"]) == 2
    assert [c["label"] for c in ds["columns"]] == ["Sector", "Close"]

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


def test_import_portfolio_maps_ref_fields_into_group_members() -> None:
    payload = {
        "group_name": "tv-portfolio",
        "group_kind": "PORTFOLIO",
        "symbol_column": "Symbol",
        "exchange_column": None,
        "default_exchange": "NSE",
        "reference_qty_column": "Shares",
        "reference_price_column": "Avg Buy Price (Rs.)",
        "target_weight_column": "Weightage",
        "target_weight_units": "AUTO",
        "selected_columns": ["Sector", "Shares", "Avg Buy Price (Rs.)", "Weightage"],
        "header_labels": {
            "Symbol": "Symbol",
            "Sector": "Sector",
            "Shares": "Shares",
            "Avg Buy Price (Rs.)": "Avg Buy Price (Rs.)",
            "Weightage": "Weightage",
        },
        "rows": [
            {
                "Symbol": "ACUTAAS",
                "Sector": "Pharma",
                "Shares": "10",
                "Avg Buy Price (Rs.)": "100.5",
                "Weightage": "25",
            },
            {
                "Symbol": "BHEL",
                "Sector": "Industrials",
                "Shares": "5",
                "Avg Buy Price (Rs.)": "200",
                "Weightage": "75",
            },
        ],
        "allow_kite_fallback": False,
        "conflict_mode": "ERROR",
        "replace_members": True,
    }
    res = client.post("/api/groups/import/watchlist", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["imported_members"] == 2
    assert data["imported_columns"] == 1

    group_id = data["group_id"]
    with SessionLocal() as db:
        group = db.query(Group).filter(Group.id == group_id).one()
        assert group.kind == "PORTFOLIO"
        members = (
            db.query(GroupMember)
            .filter(GroupMember.group_id == group_id)
            .order_by(GroupMember.symbol.asc())
            .all()
        )
        assert [(m.symbol, m.exchange) for m in members] == [
            ("ACUTAAS", "NSE"),
            ("BHEL", "NSE"),
        ]
        assert members[0].reference_qty == 10
        assert members[0].reference_price == 100.5
        assert members[0].target_weight == 0.25
        assert members[1].reference_qty == 5
        assert members[1].reference_price == 200.0
        assert members[1].target_weight == 0.75
