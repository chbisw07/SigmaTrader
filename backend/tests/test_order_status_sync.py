from __future__ import annotations

import os
from typing import Any, Dict, List

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Order
from app.services.order_sync import sync_order_statuses


class _FakeZerodhaClient:
    def __init__(self, orders: List[Dict[str, Any]]) -> None:
        self._orders = orders

    def list_orders(self) -> List[Dict[str, Any]]:
        return self._orders


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "sync-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _create_local_orders() -> None:
    with SessionLocal() as session:
        order_complete = Order(
            symbol="NSE:INFY",
            exchange="NSE",
            side="BUY",
            qty=10,
            price=1500.0,
            order_type="MARKET",
            product="MIS",
            gtt=False,
            status="SENT",
            mode="AUTO",
            simulated=False,
            zerodha_order_id="1001",
        )
        order_rejected = Order(
            symbol="NSE:TCS",
            exchange="NSE",
            side="SELL",
            qty=5,
            price=3200.0,
            order_type="MARKET",
            product="MIS",
            gtt=False,
            status="SENT",
            mode="AUTO",
            simulated=False,
            zerodha_order_id="1002",
        )
        session.add_all([order_complete, order_rejected])
        session.commit()


def test_sync_order_statuses_updates_local_orders() -> None:
    _create_local_orders()

    fake_client = _FakeZerodhaClient(
        [
            {
                "order_id": "1001",
                "status": "COMPLETE",
            },
            {
                "order_id": "1002",
                "status": "REJECTED",
                "status_message": "Insufficient funds",
            },
        ]
    )

    with SessionLocal() as session:
        updated_count = sync_order_statuses(session, fake_client)
        assert updated_count == 2

    with SessionLocal() as session:
        orders = {o.zerodha_order_id: o for o in session.query(Order).all()}
        assert orders["1001"].status == "EXECUTED"
        assert orders["1002"].status == "REJECTED"
        assert "Insufficient funds" in (orders["1002"].error_message or "")


def test_sync_reconciles_recent_waiting_orders_without_ids() -> None:
    with SessionLocal() as session:
        waiting = Order(
            symbol="NSE:CAPACITE",
            exchange="NSE",
            side="BUY",
            qty=53,
            price=None,
            order_type="MARKET",
            product="CNC",
            gtt=False,
            status="WAITING",
            mode="MANUAL",
            simulated=False,
            broker_name="zerodha",
            broker_order_id=None,
            zerodha_order_id=None,
            error_message="Requeued from order #266. Original: Max positions reached.",
        )
        session.add(waiting)
        session.commit()
        session.refresh(waiting)

        fake_client = _FakeZerodhaClient(
            [
                {
                    "order_id": "2001",
                    "status": "COMPLETE",
                    "exchange": "NSE",
                    "tradingsymbol": "CAPACITE",
                    "transaction_type": "BUY",
                    "quantity": 53,
                    "product": "CNC",
                    "order_type": "MARKET",
                    "price": 0,
                    "trigger_price": 0,
                    "order_timestamp": "2026-02-13 12:45:00",
                }
            ]
        )

        updated_count = sync_order_statuses(session, fake_client)
        assert updated_count == 1

        refreshed = session.get(Order, int(waiting.id))
        assert refreshed is not None
        assert refreshed.status == "EXECUTED"
        assert refreshed.broker_order_id == "2001"
        assert refreshed.zerodha_order_id == "2001"
        assert "Requeued from order #266" in (refreshed.error_message or "")
