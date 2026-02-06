from __future__ import annotations

import os

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Alert, RiskGlobalConfig, RiskProfile, User
from app.services.orders import create_order_from_alert


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_ENVIRONMENT", "test")
    os.environ["ST_CRYPTO_KEY"] = "test-tv-waiting-autosize-qty"
    get_settings.cache_clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_tradingview_waiting_order_gets_preview_qty_when_alert_qty_missing() -> None:
    settings = get_settings()

    with SessionLocal() as db:
        db.add(User(id=1, username="test", password_hash="x", role="ADMIN"))
        db.add(
            RiskGlobalConfig(
                singleton_key="GLOBAL",
                enabled=True,
                manual_override_enabled=False,
                baseline_equity_inr=1000000.0,
            )
        )
        db.add(
            RiskProfile(
                name="DEFAULT_MIS",
                product="MIS",
                enabled=True,
                is_default=True,
                capital_per_trade=50000.0,
            )
        )
        db.commit()

        alert = Alert(
            user_id=1,
            symbol="RAILTEL",
            exchange="NSE",
            interval="1m",
            action="SELL",
            qty=0.0,
            price=250.0,
            platform="TradingView",
            source="TRADINGVIEW",
            raw_payload="{}",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        order = create_order_from_alert(
            db,
            alert,
            mode="MANUAL",
            product="MIS",
            order_type="LIMIT",
            broker_name="zerodha",
            execution_target="LIVE",
            user_id=1,
            client_order_id="TV:test",
        )
        assert float(order.qty or 0.0) == 0.0

        from app.api import webhook as webhook_api

        webhook_api._maybe_autosize_waiting_order_qty(
            db=db,
            settings=settings,
            order=order,
            user=db.get(User, 1),
            product_hint="MIS",
            correlation_id=None,
        )

        db.refresh(order)
        assert float(order.qty or 0.0) > 0.0

