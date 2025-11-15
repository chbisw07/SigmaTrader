from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import app

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.create_all(bind=engine)


def test_create_and_list_strategies() -> None:
    unique_name = f"test-strategy-{uuid4().hex}"

    response = client.post(
        "/api/strategies/",
        json={
            "name": unique_name,
            "description": "Test strategy",
            "execution_mode": "MANUAL",
            "enabled": True,
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == unique_name
    assert created["execution_mode"] == "MANUAL"

    list_response = client.get("/api/strategies/")
    assert list_response.status_code == 200
    strategies = list_response.json()
    names = [s["name"] for s in strategies]
    assert unique_name in names
