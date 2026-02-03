from __future__ import annotations

import os
from typing import Any, Dict, List
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Order, Position, RiskProfile, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "risk-unified-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        user = User(
            username="ru-user",
            password_hash=hash_password("ru-password"),
            role="TRADER",
            display_name="RU User",
        )
        session.add(user)
        session.commit()


class _DummyResult:
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id


class _AlwaysSuccessClient:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._n = 0

    def place_order(self, **params: Any) -> _DummyResult:
        self.calls.append(params)
        self._n += 1
        return _DummyResult(order_id=f"OK{self._n}")

    def get_ltp(self, **_kwargs: Any) -> float:
        # Used by broker-aware v2 guards in the execution path.
        return 100.0


def _patch_zerodha(monkeypatch: Any) -> _AlwaysSuccessClient:
    from app.api import orders as orders_api

    fake = _AlwaysSuccessClient()

    def _fake_get_client(db: Any, settings: Any) -> _AlwaysSuccessClient:
        return fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)
    return fake


def _ensure_default_profiles() -> None:
    with SessionLocal() as session:
        for prod in ("CNC", "MIS"):
            prof = (
                session.query(RiskProfile)
                .filter(RiskProfile.product == prod, RiskProfile.is_default.is_(True))
                .order_by(RiskProfile.id.asc())
                .first()
            )
            if prof is None:
                session.add(
                    RiskProfile(
                        name=f"Default {prod}",
                        product=prod,
                        enabled=True,
                        is_default=True,
                        capital_per_trade=20000.0,
                        max_positions=6,
                        max_exposure_pct=60.0,
                        leverage_mode="OFF",
                    )
                )
        session.commit()


def _create_tv_waiting_order(*, action: str, product: str, price: float) -> int:
    payload: Dict[str, Any] = {
        "secret": "risk-unified-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "ru-user",
        "strategy_name": f"ru-strategy-{uuid4().hex}",
        "symbol": "NSE:TCS",
        "exchange": "NSE",
        "interval": "5",
        "trade_details": {
            "order_action": action,
            "product": product,
            "quantity": 1,
            "price": float(price),
        },
    }
    res = client.post("/webhook/tradingview", json=payload)
    assert res.status_code == 201, res.text
    return int(res.json()["order_id"])


def test_unified_short_selling_gate_via_source_override(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _ensure_default_profiles()

    # Block shorts for TradingView MIS orders.
    upsert = client.put(
        "/api/risk/source-overrides",
        json={"source_bucket": "TRADINGVIEW", "product": "MIS", "allow_short_selling": False},
    )
    assert upsert.status_code == 200, upsert.text

    oid = _create_tv_waiting_order(action="SELL", product="MIS", price=100.0)
    resp = client.post(f"/api/orders/{oid}/execute")
    assert resp.status_code == 400

    with SessionLocal() as session:
        o = session.get(Order, oid)
        assert o is not None
        assert o.status == "REJECTED_RISK"
        assert "Short selling blocked" in (o.error_message or "")


def test_unified_max_positions_blocks_new_entry(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _ensure_default_profiles()

    with SessionLocal() as session:
        # Ensure MIS profile is strict.
        prof = (
            session.query(RiskProfile)
            .filter(RiskProfile.product == "MIS", RiskProfile.is_default.is_(True))
            .order_by(RiskProfile.id.asc())
            .first()
        )
        assert prof is not None
        prof.max_positions = 1
        session.add(prof)
        session.query(Position).delete()
        session.add(
            Position(
                broker_name="zerodha",
                symbol="TCS",
                exchange="NSE",
                product="MIS",
                qty=1.0,
                avg_price=100.0,
                pnl=0.0,
            )
        )
        session.commit()

    oid = _create_tv_waiting_order(action="BUY", product="MIS", price=100.0)
    resp = client.post(f"/api/orders/{oid}/execute")
    assert resp.status_code == 400
    with SessionLocal() as session:
        o = session.get(Order, oid)
        assert o is not None
        assert o.status == "REJECTED_RISK"
        assert "Max positions reached" in (o.error_message or "")


def test_unified_capital_per_trade_sizes_non_manual_orders(monkeypatch: Any) -> None:
    fake = _patch_zerodha(monkeypatch)
    _ensure_default_profiles()

    with SessionLocal() as session:
        prof = (
            session.query(RiskProfile)
            .filter(RiskProfile.product == "MIS", RiskProfile.is_default.is_(True))
            .order_by(RiskProfile.id.asc())
            .first()
        )
        assert prof is not None
        prof.capital_per_trade = 20000.0
        # Avoid test cross-talk (other tests may set strict caps).
        prof.max_positions = 999
        session.query(Position).delete()
        session.add(prof)
        session.commit()

    oid = _create_tv_waiting_order(action="BUY", product="MIS", price=100.0)
    resp = client.post(f"/api/orders/{oid}/execute")
    assert resp.status_code == 200, resp.text

    # v2 sizing: floor(20000/100) = 200
    assert len(fake.calls) >= 1
    assert float(fake.calls[-1].get("quantity") or 0.0) == 200.0

    with SessionLocal() as session:
        o = session.get(Order, oid)
        assert o is not None
        assert float(o.qty or 0.0) == 200.0
