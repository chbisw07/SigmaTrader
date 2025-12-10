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


def test_create_strategy_with_invalid_dsl_rejected() -> None:
    unique_name = f"test-strategy-invalid-dsl-{uuid4().hex}"

    response = client.post(
        "/api/auth/login",
        json={"username": "strategy-user", "password": "password"},
    )
    assert response.status_code == 200

    response = client.post(
        "/api/strategies/",
        json={
            "name": unique_name,
            "description": "Bad DSL strategy",
            "execution_mode": "MANUAL",
            "enabled": True,
            "dsl_expression": "UNKNOWN_INDICATOR(1d) > 0",
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert "Invalid DSL expression" in body.get("detail", "")


def test_create_strategy_with_valid_dsl_compiles_expression() -> None:
    unique_name = f"test-strategy-valid-dsl-{uuid4().hex}"

    response = client.post(
        "/api/auth/login",
        json={"username": "strategy-user", "password": "password"},
    )
    assert response.status_code == 200

    response = client.post(
        "/api/strategies/",
        json={
            "name": unique_name,
            "description": "Good DSL strategy",
            "execution_mode": "MANUAL",
            "enabled": True,
            "dsl_expression": "PRICE(1d) > 0",
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == unique_name

    # Verify that expression_json was stored.
    from app.models import Strategy  # local import to avoid cycles

    with SessionLocal() as session:
        db_strategy = session.query(Strategy).filter(Strategy.name == unique_name).one()
        assert db_strategy.dsl_expression is not None
        assert db_strategy.expression_json is not None


def test_delete_own_strategy() -> None:
    unique_name = f"test-strategy-delete-{uuid4().hex}"

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
            "description": "Deletable strategy",
            "execution_mode": "MANUAL",
            "enabled": True,
        },
    )
    assert response.status_code == 201
    created = response.json()
    strategy_id = created["id"]

    delete_response = client.delete(f"/api/strategies/{strategy_id}")
    assert delete_response.status_code == 204

    list_response = client.get("/api/strategies/")
    assert list_response.status_code == 200
    strategies = list_response.json()
    ids = [s["id"] for s in strategies]
    assert strategy_id not in ids


def test_update_strategy_invalid_dsl_rejected() -> None:
    unique_name = f"test-strategy-update-invalid-{uuid4().hex}"

    response = client.post(
        "/api/auth/login",
        json={"username": "strategy-user", "password": "password"},
    )
    assert response.status_code == 200

    create_response = client.post(
        "/api/strategies/",
        json={
            "name": unique_name,
            "description": "Updatable strategy",
            "execution_mode": "MANUAL",
            "enabled": True,
        },
    )
    assert create_response.status_code == 201
    strategy_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/strategies/{strategy_id}",
        json={"dsl_expression": "FOO(1d) > 0"},
    )
    assert update_response.status_code == 400
    body = update_response.json()
    assert "Invalid DSL expression" in body.get("detail", "")


def test_update_strategy_valid_dsl_updates_expression() -> None:
    unique_name = f"test-strategy-update-valid-{uuid4().hex}"

    response = client.post(
        "/api/auth/login",
        json={"username": "strategy-user", "password": "password"},
    )
    assert response.status_code == 200

    create_response = client.post(
        "/api/strategies/",
        json={
            "name": unique_name,
            "description": "Updatable strategy",
            "execution_mode": "MANUAL",
            "enabled": True,
        },
    )
    assert create_response.status_code == 201
    strategy_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/strategies/{strategy_id}",
        json={"dsl_expression": "PRICE(1d) > 0"},
    )
    assert update_response.status_code == 200

    from app.models import Strategy  # local import to avoid cycles

    with SessionLocal() as session:
        db_strategy = session.query(Strategy).filter(Strategy.id == strategy_id).one()
        assert db_strategy.dsl_expression == "PRICE(1d) > 0"
        assert db_strategy.expression_json is not None
