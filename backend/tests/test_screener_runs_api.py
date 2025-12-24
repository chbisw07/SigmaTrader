from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import ScreenerRun, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    from app.core.auth import hash_password

    with SessionLocal() as session:
        session.add_all(
            [
                User(
                    username="screener-user-a",
                    password_hash=hash_password("password"),
                    role="TRADER",
                    display_name="Screener A",
                ),
                User(
                    username="screener-user-b",
                    password_hash=hash_password("password"),
                    role="TRADER",
                    display_name="Screener B",
                ),
            ]
        )
        session.commit()


def _login(username: str) -> None:
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": "password"},
    )
    assert resp.status_code == 200


def _seed_run(
    *,
    session,
    user_id: int,
    created_at: datetime,
    status: str = "DONE",
    condition_dsl: str = "PRICE(1d) > 0",
) -> ScreenerRun:
    run = ScreenerRun(
        user_id=user_id,
        status=status,
        target_json=json.dumps({"include_holdings": True, "group_ids": []}),
        variables_json="[]",
        condition_dsl=condition_dsl,
        evaluation_cadence="1m",
        total_symbols=10,
        evaluated_symbols=10,
        matched_symbols=2,
        missing_symbols=0,
        results_json="[]",
        created_at=created_at,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def test_list_runs_user_scoped_and_sorted() -> None:
    with SessionLocal() as session:
        session.query(ScreenerRun).delete()
        session.commit()

        user_a = session.query(User).filter(User.username == "screener-user-a").one()
        user_b = session.query(User).filter(User.username == "screener-user-b").one()

        now = datetime.now(UTC)
        r1 = _seed_run(
            session=session,
            user_id=user_a.id,
            created_at=now - timedelta(hours=2),
        )
        r2 = _seed_run(
            session=session,
            user_id=user_a.id,
            created_at=now - timedelta(hours=1),
        )
        r3 = _seed_run(session=session, user_id=user_a.id, created_at=now)
        _seed_run(session=session, user_id=user_b.id, created_at=now)

    _login("screener-user-a")
    resp = client.get("/api/screener-v3/runs?limit=10&offset=0")
    assert resp.status_code == 200
    runs = resp.json()

    assert len(runs) == 3
    assert [r["id"] for r in runs] == [r3.id, r2.id, r1.id]


def test_delete_run() -> None:
    with SessionLocal() as session:
        session.query(ScreenerRun).delete()
        session.commit()

        user_a = session.query(User).filter(User.username == "screener-user-a").one()
        now = datetime.now(UTC)
        run = _seed_run(session=session, user_id=user_a.id, created_at=now)

    _login("screener-user-a")
    resp = client.delete(f"/api/screener-v3/runs/{run.id}")
    assert resp.status_code == 204

    resp2 = client.get("/api/screener-v3/runs?limit=10&offset=0")
    assert resp2.status_code == 200
    assert resp2.json() == []


def test_cleanup_runs_max_days_and_max_runs() -> None:
    with SessionLocal() as session:
        session.query(ScreenerRun).delete()
        session.commit()

        user_a = session.query(User).filter(User.username == "screener-user-a").one()
        now = datetime.now(UTC)

        old = _seed_run(
            session=session,
            user_id=user_a.id,
            created_at=now - timedelta(days=30),
        )
        keep1 = _seed_run(
            session=session,
            user_id=user_a.id,
            created_at=now - timedelta(days=1),
        )
        keep2 = _seed_run(
            session=session,
            user_id=user_a.id,
            created_at=now - timedelta(hours=1),
        )
        keep3 = _seed_run(session=session, user_id=user_a.id, created_at=now)

    _login("screener-user-a")

    dry = client.post(
        "/api/screener-v3/runs/cleanup",
        json={"max_days": 7, "dry_run": True},
    )
    assert dry.status_code == 200
    assert dry.json()["deleted"] >= 1

    after_dry = client.get("/api/screener-v3/runs?limit=50").json()
    assert {r["id"] for r in after_dry} == {old.id, keep1.id, keep2.id, keep3.id}

    apply_days = client.post(
        "/api/screener-v3/runs/cleanup", json={"max_days": 7, "dry_run": False}
    )
    assert apply_days.status_code == 200

    after_days = client.get("/api/screener-v3/runs?limit=50").json()
    assert {r["id"] for r in after_days} == {keep1.id, keep2.id, keep3.id}

    apply_runs = client.post(
        "/api/screener-v3/runs/cleanup", json={"max_runs": 2, "dry_run": False}
    )
    assert apply_runs.status_code == 200

    after_runs = client.get("/api/screener-v3/runs?limit=50").json()
    assert [r["id"] for r in after_runs] == [keep3.id, keep2.id]
