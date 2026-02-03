from __future__ import annotations

import os
import threading
from datetime import UTC, datetime
from typing import Any, Dict, List
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Order, RiskProfile, User

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "risk-unified-tf-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        user = User(
            username="ru-tf-user",
            password_hash=hash_password("ru-tf-password"),
            role="TRADER",
            display_name="RU TF User",
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


def _create_tv_waiting_order(
    *, action: str, product: str, price: float, strategy: str, symbol: str
) -> int:
    payload: Dict[str, Any] = {
        "secret": "risk-unified-tf-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "ru-tf-user",
        "strategy_name": strategy,
        "symbol": symbol,
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


def test_max_trades_per_symbol_per_day_blocks_second(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _ensure_default_profiles()

    with SessionLocal() as session:
        prof = (
            session.query(RiskProfile)
            .filter(RiskProfile.product == "MIS", RiskProfile.is_default.is_(True))
            .order_by(RiskProfile.id.asc())
            .first()
        )
        assert prof is not None
        prof.max_trades_per_symbol_per_day = 1
        prof.entry_cutoff_time = None
        prof.force_squareoff_time = None
        session.add(prof)
        session.commit()

    strategy = f"ru-tf-{uuid4().hex}"
    sym = "NSE:TCS_TF1"
    o1 = _create_tv_waiting_order(action="BUY", product="MIS", price=100.0, strategy=strategy, symbol=sym)
    o2 = _create_tv_waiting_order(action="BUY", product="MIS", price=101.0, strategy=strategy, symbol=sym)

    ok = client.post(f"/api/orders/{o1}/execute")
    assert ok.status_code == 200, ok.text

    blocked = client.post(f"/api/orders/{o2}/execute")
    assert blocked.status_code == 400

    with SessionLocal() as session:
        o = session.get(Order, o2)
        assert o is not None
        assert o.status == "REJECTED_RISK"
        assert "Max trades/symbol/day reached" in (o.error_message or "")


def test_min_bars_between_trades_blocks_within_window(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _ensure_default_profiles()

    with SessionLocal() as session:
        prof = (
            session.query(RiskProfile)
            .filter(RiskProfile.product == "MIS", RiskProfile.is_default.is_(True))
            .order_by(RiskProfile.id.asc())
            .first()
        )
        assert prof is not None
        prof.max_trades_per_symbol_per_day = 0
        prof.min_bars_between_trades = 10
        session.add(prof)
        session.commit()

    strategy = f"ru-minbars-{uuid4().hex}"
    sym = "NSE:TCS_MB1"
    o1 = _create_tv_waiting_order(action="BUY", product="MIS", price=100.0, strategy=strategy, symbol=sym)
    o2 = _create_tv_waiting_order(action="BUY", product="MIS", price=101.0, strategy=strategy, symbol=sym)

    ok = client.post(f"/api/orders/{o1}/execute")
    assert ok.status_code == 200, ok.text

    blocked = client.post(f"/api/orders/{o2}/execute")
    assert blocked.status_code == 400
    with SessionLocal() as session:
        o = session.get(Order, o2)
        assert o is not None
        assert o.status == "REJECTED_RISK"
        assert "Min bars between trades not satisfied" in (o.error_message or "")


def test_concurrent_execs_do_not_race_past_max_trades(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _ensure_default_profiles()

    with SessionLocal() as session:
        prof = (
            session.query(RiskProfile)
            .filter(RiskProfile.product == "MIS", RiskProfile.is_default.is_(True))
            .order_by(RiskProfile.id.asc())
            .first()
        )
        assert prof is not None
        prof.max_trades_per_symbol_per_day = 1
        prof.min_bars_between_trades = 0
        session.add(prof)
        session.commit()

    from app.api import orders as orders_api

    # Keep time stable so both executions share the same day bounds.
    t0 = datetime(2026, 1, 20, 4, 0, tzinfo=UTC)
    monkeypatch.setattr(orders_api, "_now_utc", lambda: t0)

    strategy = f"ru-conc-{uuid4().hex}"
    sym = "NSE:TCS_CONC1"
    o1 = _create_tv_waiting_order(action="BUY", product="MIS", price=100.0, strategy=strategy, symbol=sym)
    o2 = _create_tv_waiting_order(action="BUY", product="MIS", price=101.0, strategy=strategy, symbol=sym)

    barrier = threading.Barrier(2)
    results: List[str] = []

    def _run(order_id: int) -> None:
        with SessionLocal() as session:
            barrier.wait()
            try:
                out = orders_api.execute_order_internal(order_id, db=session, settings=get_settings())
                results.append(str(getattr(out, "status", "")))
            except Exception:
                results.append("blocked")

    t1 = threading.Thread(target=_run, args=(o1,))
    t2 = threading.Thread(target=_run, args=(o2,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert results.count("SENT") == 1
    assert len(results) == 2
    assert any(r != "SENT" for r in results)
