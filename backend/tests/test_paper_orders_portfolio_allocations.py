from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Group, GroupMember, Order
from app.services import paper_trading

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_poll_paper_orders_updates_portfolio_allocations(monkeypatch) -> None:
    # Force market open for the simulation.
    monkeypatch.setattr(paper_trading, "is_market_open_now", lambda: True)

    class DummyClient:
        def get_ltp(self, *, exchange: str, tradingsymbol: str) -> float:
            _ = exchange, tradingsymbol
            return 123.0

    monkeypatch.setattr(paper_trading, "_get_price_client", lambda _db, _settings: DummyClient())

    settings = get_settings()
    with SessionLocal() as db:
        portfolio = Group(owner_id=None, name="p", kind="PORTFOLIO", description=None)
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)

        order = Order(
            user_id=None,
            alert_id=None,
            strategy_id=None,
            portfolio_group_id=portfolio.id,
            deployment_id=None,
            deployment_action_id=None,
            client_order_id=None,
            symbol="ABC",
            exchange="NSE",
            side="BUY",
            qty=10.0,
            price=None,
            order_type="MARKET",
            trigger_price=None,
            trigger_percent=None,
            product="CNC",
            gtt=False,
            synthetic_gtt=False,
            trigger_operator=None,
            status="SENT",
            mode="MANUAL",
            execution_target="PAPER",
            broker_name="zerodha",
            broker_order_id=None,
            zerodha_order_id=None,
            broker_account_id=None,
            error_message=None,
            simulated=True,
            risk_spec_json=None,
            is_exit=False,
        )
        db.add(order)
        db.commit()

        result = paper_trading.poll_paper_orders(db, settings)
        assert result.filled_orders == 1

        db.refresh(order)
        assert order.status == "EXECUTED"
        assert order.price == 123.0

        member = (
            db.query(GroupMember)
            .filter(GroupMember.group_id == portfolio.id, GroupMember.symbol == "ABC")
            .one_or_none()
        )
        assert member is not None
        assert int(member.reference_qty or 0) == 10
        assert float(member.reference_price or 0.0) == 123.0

