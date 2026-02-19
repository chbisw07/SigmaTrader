from __future__ import annotations

import asyncio
import os

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.schemas.ai_trading_manager import BrokerOrder, TradeIntent, TradePlan
from app.services.ai_trading_manager.broker_adapter import BrokerOrderAck
from app.services.ai_trading_manager.execution.engine import ExecutionEngine


class FakeAsyncBroker:
    name = "fake_async"

    def __init__(self, *, final_status: str = "COMPLETE") -> None:
        self.placed = 0
        self._final_status = final_status
        self._polls = 0
        self._last_order_id: str | None = None

    async def place_order(self, *, account_id: str, intent):  # noqa: ANN001,ARG002
        self.placed += 1
        self._last_order_id = f"oid-{self.placed}"
        return BrokerOrderAck(broker_order_id=self._last_order_id, status="ACK")

    async def get_orders(self, *, account_id: str):  # noqa: ARG002
        self._polls += 1
        if not self._last_order_id:
            return []
        status = "OPEN" if self._polls < 2 else self._final_status
        return [
            BrokerOrder(
                broker_order_id=self._last_order_id,
                symbol="SBIN",
                side="BUY",
                product="MIS",
                qty=1,
                order_type="MARKET",
                status=status,
            )
        ]


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_execution_engine_async_is_idempotent() -> None:
    plan = TradePlan(
        plan_id="p1",
        intent=TradeIntent(symbols=["SBIN"], side="BUY", product="MIS", constraints={"qty": 1}, risk_budget_pct=0.5),
        order_skeleton={"order_type": "MARKET"},
    )
    broker = FakeAsyncBroker(final_status="COMPLETE")
    eng = ExecutionEngine()

    with SessionLocal() as db:
        r1 = asyncio.run(
            eng.execute_to_broker_async(
                db,
                user_id=None,
                account_id="default",
                correlation_id="c1",
                plan=plan,
                idempotency_key="idem-async-1",
                broker=broker,
            )
        )
        assert r1["mode"] == "execute"
        assert broker.placed == 1

        r2 = asyncio.run(
            eng.execute_to_broker_async(
                db,
                user_id=None,
                account_id="default",
                correlation_id="c1",
                plan=plan,
                idempotency_key="idem-async-1",
                broker=broker,
            )
        )
        assert r2["idempotency_record_id"] == r1["idempotency_record_id"]
        assert broker.placed == 1  # idempotent: no duplicate order


def test_execution_engine_async_handles_reject() -> None:
    plan = TradePlan(
        plan_id="p2",
        intent=TradeIntent(symbols=["SBIN"], side="BUY", product="MIS", constraints={"qty": 1}, risk_budget_pct=0.5),
        order_skeleton={"order_type": "MARKET"},
    )
    broker = FakeAsyncBroker(final_status="REJECTED")
    eng = ExecutionEngine()

    with SessionLocal() as db:
        r = asyncio.run(
            eng.execute_to_broker_async(
                db,
                user_id=None,
                account_id="default",
                correlation_id="c2",
                plan=plan,
                idempotency_key="idem-async-2",
                broker=broker,
            )
        )
        assert r["orders"] and r["orders"][0]["broker_order_id"]
        assert r["poll"]["status"] in {"converged", "timeout", "unavailable"}
