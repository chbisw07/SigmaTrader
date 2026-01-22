from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import app

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_basket_config_and_freeze_roundtrip(monkeypatch) -> None:
    # Create basket group.
    res = client.post(
        "/api/groups/",
        json={"name": "basket-freeze", "kind": "MODEL_PORTFOLIO", "description": "t"},
    )
    assert res.status_code == 200
    group_id = res.json()["id"]

    # Add members.
    res = client.post(
        f"/api/groups/{group_id}/members",
        json={"symbol": "ABC", "exchange": "NSE", "target_weight": 0.6},
    )
    assert res.status_code == 200
    member_a = res.json()

    res = client.post(
        f"/api/groups/{group_id}/members",
        json={"symbol": "XYZ", "exchange": "NSE", "target_weight": 0.4},
    )
    assert res.status_code == 200
    _ = res.json()

    # Set lock flag on one member.
    res = client.patch(
        f"/api/groups/{group_id}/members/{member_a['id']}",
        json={"weight_locked": True},
    )
    assert res.status_code == 200
    assert res.json()["weight_locked"] is True

    # Update basket config.
    res = client.patch(
        f"/api/groups/{group_id}/basket/config",
        json={"funds": 100000, "allocation_mode": "WEIGHT"},
    )
    assert res.status_code == 200
    cfg = res.json()
    assert cfg["funds"] == 100000
    assert cfg["allocation_mode"] == "WEIGHT"

    # Freeze prices.
    def fake_get_bulk_quotes(_db, _settings, keys):
        _ = keys
        return {
            ("NSE", "ABC"): {"last_price": 101.0, "prev_close": 100.0},
            ("NSE", "XYZ"): {"last_price": 201.0, "prev_close": 200.0},
        }

    monkeypatch.setattr(
        "app.services.baskets.get_bulk_quotes",
        fake_get_bulk_quotes,
        raising=True,
    )

    res = client.post(f"/api/groups/{group_id}/basket/freeze")
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "MODEL_PORTFOLIO"
    assert data["frozen_at"] is not None

    by_symbol = {m["symbol"]: m for m in data["members"]}
    assert by_symbol["ABC"]["frozen_price"] == 101.0
    assert by_symbol["ABC"]["weight_locked"] is True
    assert by_symbol["XYZ"]["frozen_price"] == 201.0

    # Freeze again and verify overwrite.
    def fake_get_bulk_quotes2(_db, _settings, keys):
        _ = keys
        return {
            ("NSE", "ABC"): {"last_price": 111.0, "prev_close": 100.0},
            ("NSE", "XYZ"): {"last_price": 222.0, "prev_close": 200.0},
        }

    monkeypatch.setattr(
        "app.services.baskets.get_bulk_quotes",
        fake_get_bulk_quotes2,
        raising=True,
    )
    res = client.post(f"/api/groups/{group_id}/basket/freeze")
    assert res.status_code == 200
    data2 = res.json()
    by_symbol2 = {m["symbol"]: m for m in data2["members"]}
    assert by_symbol2["ABC"]["frozen_price"] == 111.0
    assert by_symbol2["XYZ"]["frozen_price"] == 222.0

    # GET group reflects persisted fields.
    res = client.get(f"/api/groups/{group_id}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["funds"] == 100000
    assert detail["allocation_mode"] == "WEIGHT"
    assert detail["frozen_at"] is not None
    by_symbol3 = {m["symbol"]: m for m in detail["members"]}
    assert by_symbol3["ABC"]["frozen_price"] == 111.0
    assert by_symbol3["ABC"]["weight_locked"] is True
