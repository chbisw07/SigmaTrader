from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import HoldingExitSubscription, Order, User
from app.services.holdings_exit_engine import process_holdings_exit_once


class _FakeZerodhaClient:
    def __init__(self, *, holdings: list[dict], ltp_map: dict[tuple[str, str], dict]):
        self._holdings = holdings
        self._ltp_map = ltp_map

    def list_holdings(self):  # noqa: D401 - external API shape
        return list(self._holdings)

    def get_ltp_bulk(self, instruments):  # noqa: D401 - external API shape
        out = {}
        for ex, sym in instruments:
            out[(ex, sym)] = dict(self._ltp_map.get((ex, sym), {}))
        return out


@pytest.fixture(autouse=True)
def _reset_db_and_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_HOLDINGS_EXIT_ENABLED"] = "1"
    os.environ.setdefault("ST_CRYPTO_KEY", "pytest-crypto-key")
    get_settings.cache_clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Create a default admin user.
    with SessionLocal() as db:
        db.add(User(username="admin", password_hash="x", role="ADMIN"))
        db.commit()


def test_engine_creates_waiting_order_when_trigger_met(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import holdings_exit_engine as eng

    fake = _FakeZerodhaClient(
        holdings=[
            {
                "tradingsymbol": "INFY",
                "exchange": "NSE",
                "quantity": 10,
                "average_price": 80.0,
            }
        ],
        ltp_map={
            ("NSE", "INFY"): {"last_price": 120.0, "prev_close": 110.0},
        },
    )
    monkeypatch.setattr(
        eng,
        "_get_zerodha_client",
        lambda db, settings, *, user_id: fake,
    )

    now = datetime.now(UTC)
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").one()
        sub = HoldingExitSubscription(
            user_id=admin.id,
            broker_name="zerodha",
            symbol="INFY",
            exchange="NSE",
            product="CNC",
            trigger_kind="TARGET_ABS_PRICE",
            trigger_value=100.0,
            price_source="LTP",
            size_mode="PCT_OF_POSITION",
            size_value=50.0,
            min_qty=1,
            order_type="MARKET",
            dispatch_mode="MANUAL",
            execution_target="LIVE",
            status="ACTIVE",
            pending_order_id=None,
            last_error=None,
            last_evaluated_at=None,
            last_triggered_at=None,
            next_eval_at=now - timedelta(seconds=1),
            cooldown_seconds=0,
            cooldown_until=None,
            trigger_key=None,
            created_at=now,
            updated_at=now,
        )
        db.add(sub)
        db.commit()

    processed = process_holdings_exit_once()
    assert processed >= 1

    with SessionLocal() as db:
        sub2 = db.query(HoldingExitSubscription).one()
        assert sub2.status == "ORDER_CREATED"
        assert sub2.pending_order_id is not None
        order = db.get(Order, int(sub2.pending_order_id))
        assert order is not None
        assert order.status == "WAITING"
        assert order.mode == "MANUAL"
        assert order.side == "SELL"
        assert order.product == "CNC"
        assert order.symbol == "INFY"
        assert order.exchange == "NSE"
        assert order.qty == 5.0  # 50% of 10
        assert order.is_exit is True


def test_engine_does_not_create_order_when_trigger_not_met(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import holdings_exit_engine as eng

    fake = _FakeZerodhaClient(
        holdings=[
            {
                "tradingsymbol": "INFY",
                "exchange": "NSE",
                "quantity": 10,
                "average_price": 80.0,
            }
        ],
        ltp_map={
            ("NSE", "INFY"): {"last_price": 90.0, "prev_close": 110.0},
        },
    )
    monkeypatch.setattr(
        eng,
        "_get_zerodha_client",
        lambda db, settings, *, user_id: fake,
    )

    now = datetime.now(UTC)
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").one()
        sub = HoldingExitSubscription(
            user_id=admin.id,
            broker_name="zerodha",
            symbol="INFY",
            exchange="NSE",
            product="CNC",
            trigger_kind="TARGET_ABS_PRICE",
            trigger_value=100.0,
            price_source="LTP",
            size_mode="ABS_QTY",
            size_value=1.0,
            min_qty=1,
            order_type="MARKET",
            dispatch_mode="MANUAL",
            execution_target="LIVE",
            status="ACTIVE",
            pending_order_id=None,
            last_error=None,
            last_evaluated_at=None,
            last_triggered_at=None,
            next_eval_at=now - timedelta(seconds=1),
            cooldown_seconds=0,
            cooldown_until=None,
            trigger_key=None,
            created_at=now,
            updated_at=now,
        )
        db.add(sub)
        db.commit()

    processed = process_holdings_exit_once()
    assert processed >= 1

    with SessionLocal() as db:
        sub2 = db.query(HoldingExitSubscription).one()
        assert sub2.status == "ACTIVE"
        assert sub2.pending_order_id is None
        assert db.query(Order).count() == 0


def test_engine_reconciles_success_and_marks_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reconciliation should not require broker access.
    from app.services import holdings_exit_engine as eng

    monkeypatch.setattr(
        eng,
        "_get_zerodha_client",
        lambda db, settings, *, user_id: None,
    )

    now = datetime.now(UTC)
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").one()
        order = Order(
            user_id=admin.id,
            alert_id=None,
            strategy_id=None,
            portfolio_group_id=None,
            client_order_id="HEXIT:test:1",
            symbol="INFY",
            exchange="NSE",
            side="SELL",
            qty=1.0,
            price=None,
            order_type="MARKET",
            product="CNC",
            gtt=False,
            synthetic_gtt=False,
            status="EXECUTED",
            mode="MANUAL",
            execution_target="LIVE",
            broker_name="zerodha",
            broker_order_id="x",
            zerodha_order_id=None,
            broker_account_id=None,
            error_message=None,
            simulated=False,
            risk_spec_json=None,
            is_exit=True,
            created_at=now,
            updated_at=now,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        sub = HoldingExitSubscription(
            user_id=admin.id,
            broker_name="zerodha",
            symbol="INFY",
            exchange="NSE",
            product="CNC",
            trigger_kind="TARGET_ABS_PRICE",
            trigger_value=100.0,
            price_source="LTP",
            size_mode="ABS_QTY",
            size_value=1.0,
            min_qty=1,
            order_type="MARKET",
            dispatch_mode="MANUAL",
            execution_target="LIVE",
            status="ORDER_CREATED",
            pending_order_id=order.id,
            last_error=None,
            last_evaluated_at=None,
            last_triggered_at=now,
            next_eval_at=now - timedelta(seconds=1),
            cooldown_seconds=0,
            cooldown_until=None,
            trigger_key=None,
            created_at=now,
            updated_at=now,
        )
        db.add(sub)
        db.commit()

    processed = process_holdings_exit_once()
    assert processed >= 1

    with SessionLocal() as db:
        sub2 = db.query(HoldingExitSubscription).one()
        assert sub2.status == "COMPLETED"
        assert sub2.pending_order_id is None
