from __future__ import annotations

from uuid import uuid4

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Strategy


def test_can_persist_strategy() -> None:
    """Smoke test for ORM configuration and DB connectivity."""

    Base.metadata.create_all(bind=engine)

    strategy_name = f"test-strategy-{uuid4().hex}"

    with SessionLocal() as session:
        strategy = Strategy(name=strategy_name, execution_mode="MANUAL")
        session.add(strategy)
        session.commit()
        session.refresh(strategy)

        fetched = session.get(Strategy, strategy.id)

        assert fetched is not None
        assert fetched.name == strategy_name
