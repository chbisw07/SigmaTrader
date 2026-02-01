from __future__ import annotations

from uuid import uuid4

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import HoldingExitEvent, HoldingExitSubscription


def test_can_persist_holding_exit_subscription_and_event() -> None:
    Base.metadata.create_all(bind=engine)

    symbol = f"TEST{uuid4().hex[:10]}"

    with SessionLocal() as session:
        sub = HoldingExitSubscription(
            user_id=None,
            broker_name="zerodha",
            symbol=symbol,
            exchange="NSE",
            product="CNC",
            trigger_kind="TARGET_ABS_PRICE",
            trigger_value=123.45,
            price_source="LTP",
            size_mode="PCT_OF_POSITION",
            size_value=50.0,
            min_qty=1,
            order_type="MARKET",
            dispatch_mode="MANUAL",
            execution_target="LIVE",
            status="ACTIVE",
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)

        event = HoldingExitEvent(
            subscription_id=sub.id,
            event_type="SUB_CREATED",
            details_json="{\"source\":\"test\"}",
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        fetched = session.get(HoldingExitSubscription, sub.id)
        assert fetched is not None
        assert fetched.symbol == symbol

