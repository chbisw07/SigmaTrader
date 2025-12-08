from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    # Reset DB and create tables.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Seed a default user so that strategy APIs requiring authentication can
    # be exercised via the auth endpoints.
    from app.core.auth import hash_password

    with SessionLocal() as session:
        user = User(
            username="strategy-user",
            password_hash=hash_password("password"),
            role="TRADER",
            display_name="Strategy User",
        )
        session.add(user)
        session.commit()


def test_create_and_list_strategies() -> None:
    unique_name = f"test-strategy-{uuid4().hex}"

    # Log in and obtain session cookie.
    response = client.post(
        "/api/auth/login",
        json={"username": "strategy-user", "password": "password"},
    )
    assert response.status_code == 200

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
