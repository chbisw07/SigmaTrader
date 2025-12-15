from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import app

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_group_member_reference_fields_roundtrip() -> None:
    # Create a portfolio group (new kind supported for G04 groundwork).
    res = client.post(
        "/api/groups/",
        json={"name": "g04-portfolio", "kind": "PORTFOLIO", "description": "test"},
    )
    assert res.status_code == 200
    group = res.json()
    group_id = group["id"]

    # Add member with reference metadata.
    res = client.post(
        f"/api/groups/{group_id}/members",
        json={
            "symbol": "ABC",
            "exchange": "NSE",
            "reference_qty": 5,
            "reference_price": 123.45,
            "notes": "seed",
        },
    )
    assert res.status_code == 200
    member = res.json()
    assert member["symbol"] == "ABC"
    assert member["reference_qty"] == 5
    assert member["reference_price"] == 123.45
    assert member["notes"] == "seed"

    # Clear reference fields (explicit null) and notes (null) via PATCH.
    res = client.patch(
        f"/api/groups/{group_id}/members/{member['id']}",
        json={"reference_qty": None, "reference_price": None, "notes": None},
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["reference_qty"] is None
    assert updated["reference_price"] is None
    assert updated["notes"] is None

    # Ensure GET group returns the cleared fields.
    res = client.get(f"/api/groups/{group_id}")
    assert res.status_code == 200
    detail = res.json()
    members = detail["members"]
    assert len(members) == 1
    assert members[0]["reference_qty"] is None
    assert members[0]["reference_price"] is None
