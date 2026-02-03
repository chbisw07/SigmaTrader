from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import AnalyticsTrade, DrawdownThreshold, Order, RiskProfile, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_CRYPTO_KEY", "test-risk-compiled-api-crypto-key")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            User(
                username="rc-user",
                password_hash=hash_password("rc-password"),
                role="TRADER",
                display_name="RC User",
            )
        )
        session.commit()


def _seed_profile_thresholds_and_trade() -> None:
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    opened = now - timedelta(hours=1)

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "rc-user").one()
        session.query(RiskProfile).delete()
        session.query(DrawdownThreshold).delete()
        session.query(AnalyticsTrade).delete()
        session.query(Order).delete()
        session.commit()

        session.add(
            RiskProfile(
                name="MIS_DEFAULT",
                product="MIS",
                capital_per_trade=10_000.0,
                max_positions=10,
                max_exposure_pct=100.0,
                risk_per_trade_pct=0.0,
                hard_risk_pct=0.0,
                daily_loss_pct=0.0,
                hard_daily_loss_pct=0.0,
                max_consecutive_losses=0,
                drawdown_mode="SETTINGS_BY_CATEGORY",
                enabled=True,
                is_default=True,
            )
        )
        session.add(
            DrawdownThreshold(
                user_id=None,
                product="MIS",
                category="LC",
                caution_pct=0.5,
                defense_pct=2.0,
                hard_stop_pct=5.0,
            )
        )

        entry = Order(
            user_id=int(user.id),
            symbol="TCS",
            exchange="NSE",
            side="BUY",
            qty=1,
            price=100.0,
            order_type="MARKET",
            product="MIS",
            status="EXECUTED",
            mode="AUTO",
            broker_name="zerodha",
        )
        exit_o = Order(
            user_id=int(user.id),
            symbol="TCS",
            exchange="NSE",
            side="SELL",
            qty=1,
            price=100.0,
            order_type="MARKET",
            product="MIS",
            status="EXECUTED",
            mode="AUTO",
            broker_name="zerodha",
        )
        session.add(entry)
        session.add(exit_o)
        session.commit()
        session.refresh(entry)
        session.refresh(exit_o)

        session.add(
            AnalyticsTrade(
                entry_order_id=entry.id,
                exit_order_id=exit_o.id,
                strategy_id=None,
                pnl=-10_000.0,
                r_multiple=None,
                opened_at=opened,
                closed_at=now,
            )
        )
        session.commit()


def test_compiled_endpoint_returns_expected_shape_and_supports_scenario_override() -> None:
    _seed_profile_thresholds_and_trade()

    r1 = client.get("/api/risk/compiled", params={"product": "MIS", "category": "LC"})
    assert r1.status_code == 200
    data1: Dict[str, Any] = r1.json()
    assert data1["context"]["product"] == "MIS"
    assert data1["context"]["category"] == "LC"
    assert data1["effective"]["risk_engine_v2"]["drawdown_state"] in {"CAUTION", "DEFENSE", "HARD_STOP", "NORMAL"}
    assert "risk_policy_by_source" in data1["effective"]

    r2 = client.get(
        "/api/risk/compiled",
        params={"product": "MIS", "category": "LC", "scenario": "NORMAL"},
    )
    assert r2.status_code == 200
    data2: Dict[str, Any] = r2.json()
    assert data2["effective"]["risk_engine_v2"]["drawdown_state"] == "NORMAL"


def test_compiled_endpoint_returns_blocking_reasons_when_thresholds_missing() -> None:
    _seed_profile_thresholds_and_trade()
    with SessionLocal() as session:
        session.query(DrawdownThreshold).delete()
        session.commit()

    r = client.get("/api/risk/compiled", params={"product": "MIS", "category": "LC"})
    assert r.status_code == 200
    data = r.json()
    assert data["effective"]["blocking_reasons"]
