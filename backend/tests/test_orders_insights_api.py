from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Alert, AlertDecisionLog, Order, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "orders-insights-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            User(
                username="insights-user",
                password_hash=hash_password("insights-password"),
                role="TRADER",
                display_name="Insights User",
            )
        )
        session.commit()


def test_orders_insights_summarizes_alerts_decisions_orders() -> None:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "insights-user").one()

        tv_alert_1 = Alert(
            user_id=user.id,
            strategy_id=None,
            symbol="INFY",
            exchange="NSE",
            interval="15",
            action="BUY",
            qty=1.0,
            price=100.0,
            platform="TRADINGVIEW",
            source="TRADINGVIEW",
            raw_payload="{}",
            received_at=datetime(2026, 2, 12, 6, 30, tzinfo=UTC),  # 12:00 IST
        )
        tv_alert_2 = Alert(
            user_id=user.id,
            strategy_id=None,
            symbol="SBIN",
            exchange="NSE",
            interval="15",
            action="SELL",
            qty=1.0,
            price=200.0,
            platform="TRADINGVIEW",
            source="TRADINGVIEW",
            raw_payload="{}",
            received_at=datetime(2026, 2, 13, 6, 30, tzinfo=UTC),  # 12:00 IST
        )
        non_tv_alert = Alert(
            user_id=user.id,
            strategy_id=None,
            symbol="TCS",
            exchange="NSE",
            interval="15",
            action="SELL",
            qty=1.0,
            price=300.0,
            platform="SIGMATRADER",
            source="ALERT",
            raw_payload="{}",
            received_at=datetime(2026, 2, 12, 7, 0, tzinfo=UTC),
        )
        session.add_all([tv_alert_1, tv_alert_2, non_tv_alert])
        session.flush()

        session.add_all(
            [
                AlertDecisionLog(
                    user_id=user.id,
                    alert_id=tv_alert_1.id,
                    source="TRADINGVIEW",
                    strategy_ref="SUPERTREND",
                    symbol="INFY",
                    exchange="NSE",
                    side="BUY",
                    product_hint="CNC",
                    resolved_product="CNC",
                    decision="PLACED",
                    reasons_json="[]",
                    details_json="{}",
                    created_at=datetime(2026, 2, 12, 6, 31, tzinfo=UTC),
                ),
                AlertDecisionLog(
                    user_id=user.id,
                    alert_id=tv_alert_1.id,
                    source="TRADINGVIEW",
                    strategy_ref="SUPERTREND",
                    symbol="SBIN",
                    exchange="NSE",
                    side="SELL",
                    product_hint="CNC",
                    resolved_product="CNC",
                    decision="BLOCKED",
                    reasons_json='["Max positions reached"]',
                    details_json="{}",
                    created_at=datetime(2026, 2, 12, 6, 32, tzinfo=UTC),
                ),
                AlertDecisionLog(
                    user_id=user.id,
                    alert_id=None,
                    source="ALERT",
                    strategy_ref="MANUAL",
                    symbol="INFY",
                    exchange="NSE",
                    side="SELL",
                    product_hint="MIS",
                    resolved_product="MIS",
                    decision="BLOCKED",
                    reasons_json='["Max consecutive losses reached","Cooldown active"]',
                    details_json="{}",
                    created_at=datetime(2026, 2, 13, 6, 45, tzinfo=UTC),
                ),
            ]
        )

        session.add_all(
            [
                # Day 1: executed TV order.
                Order(
                    user_id=user.id,
                    alert_id=tv_alert_1.id,
                    strategy_id=None,
                    symbol="INFY",
                    exchange="NSE",
                    side="BUY",
                    qty=1.0,
                    price=100.0,
                    product="CNC",
                    status="EXECUTED",
                    mode="AUTO",
                    execution_target="LIVE",
                    broker_name="zerodha",
                    created_at=datetime(2026, 2, 12, 6, 35, tzinfo=UTC),
                    updated_at=datetime(2026, 2, 12, 6, 35, tzinfo=UTC),
                ),
                # Day 1: manual failed order.
                Order(
                    user_id=user.id,
                    alert_id=None,
                    strategy_id=None,
                    symbol="TCS",
                    exchange="NSE",
                    side="SELL",
                    qty=1.0,
                    price=300.0,
                    product="MIS",
                    status="FAILED",
                    mode="MANUAL",
                    execution_target="LIVE",
                    broker_name="zerodha",
                    created_at=datetime(2026, 2, 12, 6, 40, tzinfo=UTC),
                    updated_at=datetime(2026, 2, 12, 6, 40, tzinfo=UTC),
                ),
                # Day 1: non-TV alert waiting order.
                Order(
                    user_id=user.id,
                    alert_id=non_tv_alert.id,
                    strategy_id=None,
                    symbol="SBIN",
                    exchange="NSE",
                    side="SELL",
                    qty=1.0,
                    price=None,
                    product="CNC",
                    status="WAITING",
                    mode="MANUAL",
                    execution_target="LIVE",
                    broker_name="zerodha",
                    created_at=datetime(2026, 2, 12, 6, 50, tzinfo=UTC),
                    updated_at=datetime(2026, 2, 12, 6, 50, tzinfo=UTC),
                ),
                # Day 2: risk rejected TV order.
                Order(
                    user_id=user.id,
                    alert_id=tv_alert_2.id,
                    strategy_id=None,
                    symbol="SBIN",
                    exchange="NSE",
                    side="BUY",
                    qty=1.0,
                    price=200.0,
                    product="CNC",
                    status="REJECTED_RISK",
                    mode="AUTO",
                    execution_target="LIVE",
                    broker_name="zerodha",
                    created_at=datetime(2026, 2, 13, 6, 55, tzinfo=UTC),
                    updated_at=datetime(2026, 2, 13, 6, 55, tzinfo=UTC),
                ),
                # Day 2: simulated order should be excluded by default.
                Order(
                    user_id=user.id,
                    alert_id=tv_alert_2.id,
                    strategy_id=None,
                    symbol="SBIN",
                    exchange="NSE",
                    side="SELL",
                    qty=1.0,
                    price=200.0,
                    product="MIS",
                    status="EXECUTED",
                    mode="AUTO",
                    execution_target="PAPER",
                    broker_name="zerodha",
                    simulated=True,
                    created_at=datetime(2026, 2, 13, 7, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 2, 13, 7, 0, tzinfo=UTC),
                ),
            ]
        )
        session.commit()

    resp = client.get(
        "/api/orders/insights",
        params={"start_date": "2026-02-12", "end_date": "2026-02-13", "top_n": 10},
    )
    assert resp.status_code == 200
    data = resp.json()

    summary = data["summary"]
    assert summary["tv_alerts"] == 2
    assert summary["decisions_total"] == 3
    assert summary["decisions_placed"] == 1
    assert summary["decisions_blocked"] == 2
    assert summary["decisions_from_tv"] == 2

    # Simulated order excluded by default.
    assert summary["orders_total"] == 4
    assert summary["orders_executed"] == 1
    assert summary["orders_failed"] == 1
    assert summary["orders_waiting"] == 1
    assert summary["orders_rejected_risk"] == 1

    assert summary["order_products"]["CNC"] == 3
    assert summary["order_products"]["MIS"] == 1
    assert summary["order_sides"]["BUY"] == 2
    assert summary["order_sides"]["SELL"] == 2

    assert summary["origins"]["TRADINGVIEW"] == 2
    assert summary["origins"]["ALERT"] == 1
    assert summary["origins"]["MANUAL"] == 1

    days = {row["day"] for row in data["daily"]}
    assert "2026-02-12" in days
    assert "2026-02-13" in days

    reasons = {row["reason"]: row["count"] for row in data["top_block_reasons"]}
    assert reasons.get("Max positions reached") == 1
    assert reasons.get("Max consecutive losses reached") == 1
    assert reasons.get("Cooldown active") == 1


def test_orders_insights_enforces_date_range_limit() -> None:
    resp = client.get(
        "/api/orders/insights",
        params={"start_date": "2026-01-01", "end_date": "2026-02-01"},
    )
    assert resp.status_code == 400
    assert "max allowed is 15 days" in resp.json().get("detail", "")

