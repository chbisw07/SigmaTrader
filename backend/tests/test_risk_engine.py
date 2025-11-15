from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Order, RiskSettings, Strategy

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "risk-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _create_strategy_and_global_risk() -> Strategy:
    with SessionLocal() as session:
        strategy = Strategy(
            name="risk-test-strategy",
            description="Risk test strategy",
            execution_mode="AUTO",
            enabled=True,
        )
        session.add(strategy)
        session.commit()

        settings = RiskSettings(
            scope="GLOBAL",
            strategy_id=None,
            max_order_value=100000.0,
            max_quantity_per_order=100.0,
            allow_short_selling=False,
            clamp_mode="CLAMP",
        )
        session.add(settings)
        session.commit()

        session.refresh(strategy)
        return strategy


def _create_order(strategy_id: int, side: str, qty: float, price: float) -> int:
    with SessionLocal() as session:
        order = Order(
            strategy_id=strategy_id,
            symbol="NSE:INFY",
            exchange="NSE",
            side=side,
            qty=qty,
            price=price,
            order_type="LIMIT",
            product="MIS",
            gtt=False,
            status="WAITING",
            mode="MANUAL",
            simulated=True,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order.id


def test_risk_clamps_quantity_when_over_max_qty() -> None:
    strategy = _create_strategy_and_global_risk()

    with SessionLocal() as session:
        rs = session.query(RiskSettings).filter(RiskSettings.scope == "GLOBAL").one()
        rs.max_quantity_per_order = 50.0
        session.commit()

    order_id = _create_order(
        strategy_id=strategy.id, side="BUY", qty=120.0, price=100.0
    )

    from app.services.risk import evaluate_order_risk

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        result = evaluate_order_risk(session, order)

    assert not result.blocked
    assert result.clamped
    assert result.original_qty == 120.0
    assert result.final_qty == 50.0
    assert "clamped" in (result.reason or "").lower()


def test_risk_blocks_short_selling_when_disabled() -> None:
    strategy = _create_strategy_and_global_risk()

    order_id = _create_order(
        strategy_id=strategy.id, side="SELL", qty=10.0, price=100.0
    )

    from app.services.risk import evaluate_order_risk

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        result = evaluate_order_risk(session, order)

    assert result.blocked
    assert not result.clamped
    assert "short selling is disabled" in (result.reason or "").lower()


def test_risk_clamps_max_order_value_to_integer_quantity() -> None:
    strategy = _create_strategy_and_global_risk()

    # Configure a max_order_value that will require clamping to a
    # non-fractional quantity (e.g., 10000 / 1068.8 ~= 9.36 -> 9).
    with SessionLocal() as session:
        rs = session.query(RiskSettings).filter(RiskSettings.scope == "GLOBAL").one()
        rs.max_order_value = 10000.0
        rs.max_quantity_per_order = None
        session.commit()

    order_id = _create_order(
        strategy_id=strategy.id,
        side="BUY",
        qty=150.0,
        price=1068.8,
    )

    from app.services.risk import evaluate_order_risk

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        result = evaluate_order_risk(session, order)

    assert not result.blocked
    assert result.clamped
    # Quantity should be an integer number of units.
    assert result.final_qty == int(result.final_qty)
