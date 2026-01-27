from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import AnalyticsTrade, DrawdownThreshold, Order, RiskProfile, SymbolRiskCategory, User

client = TestClient(app)


class _DummyResult:
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id


class _SpyBroker:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def get_quote_bulk(self, instruments: list[tuple[str, str]]) -> Dict[tuple[str, str], Dict[str, float | None]]:
        out: Dict[tuple[str, str], Dict[str, float | None]] = {}
        for exch, sym in instruments:
            out[(exch, sym)] = {"last_price": 100.0, "prev_close": 100.0}
        return out

    def place_order(self, **params: Any) -> _DummyResult:
        self.calls.append(params)
        return _DummyResult(order_id="OK123")


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "compiled-secret"
    os.environ["ST_RISK_ENGINE_V2_ENABLED"] = "1"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            User(
                username="compiled-user",
                password_hash=hash_password("compiled-password"),
                role="TRADER",
                display_name="Compiled User",
            )
        )
        session.commit()


def _seed_base_v2_config(*, hard_stop_pct: float) -> None:
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    opened = now - timedelta(hours=1)

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "compiled-user").one()
        session.query(AnalyticsTrade).delete()
        session.query(Order).delete()
        session.query(RiskProfile).delete()
        session.query(DrawdownThreshold).delete()
        session.query(SymbolRiskCategory).delete()
        session.commit()

        # V2 profile (set leverage_mode=OFF to avoid broker margin enforcement).
        session.add(
            RiskProfile(
                name="MIS_Default",
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
                leverage_mode="OFF",
                slippage_guard_bps=0.0,
                gap_guard_pct=0.0,
            )
        )
        session.add(
            DrawdownThreshold(
                user_id=None,
                product="MIS",
                category="LC",
                caution_pct=0.0,
                defense_pct=0.0,
                hard_stop_pct=float(hard_stop_pct),
            )
        )
        session.add(
            SymbolRiskCategory(
                user_id=int(user.id),
                broker_name="zerodha",
                symbol="TCS",
                exchange="NSE",
                risk_category="LC",
            )
        )

        # A losing trade so drawdown_pct ~ 1% (baseline equity default is 1,000,000).
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


def _create_waiting_order_via_webhook() -> int:
    payload: Dict[str, Any] = {
        "secret": "compiled-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "compiled-user",
        "strategy_name": f"compiled-strategy-{uuid4().hex}",
        "symbol": "NSE:TCS",
        "exchange": "NSE",
        "interval": "1",
        "trade_details": {"order_action": "BUY", "quantity": None, "price": 100.0},
    }
    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    return int(response.json()["order_id"])


def test_execute_calls_compiler_and_hard_stop_blocks(monkeypatch: Any) -> None:
    _seed_base_v2_config(hard_stop_pct=0.5)  # 1% DD triggers HARD_STOP
    order_id = _create_waiting_order_via_webhook()

    from app.api import orders as orders_api
    from app.services import risk_compiler as risk_compiler_mod

    broker = _SpyBroker()

    def _fake_get_client(db: Any, settings: Any, user_id: int | None = None) -> _SpyBroker:
        return broker

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    called = {"n": 0}
    original = risk_compiler_mod.compile_risk_policy

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        called["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(risk_compiler_mod, "compile_risk_policy", _wrapped)

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 400
    assert called["n"] >= 1
    assert broker.calls == []


def test_execute_calls_compiler_on_success_path(monkeypatch: Any) -> None:
    _seed_base_v2_config(hard_stop_pct=50.0)  # NORMAL
    order_id = _create_waiting_order_via_webhook()

    from app.api import orders as orders_api
    from app.services import risk_compiler as risk_compiler_mod

    broker = _SpyBroker()

    def _fake_get_client(db: Any, settings: Any, user_id: int | None = None) -> _SpyBroker:
        return broker

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    called = {"n": 0}
    original = risk_compiler_mod.compile_risk_policy

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        called["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(risk_compiler_mod, "compile_risk_policy", _wrapped)

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 200
    assert called["n"] >= 1
    assert broker.calls, "Expected broker placement call"

