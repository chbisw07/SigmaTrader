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
from app.models import (
    Alert,
    AnalyticsTrade,
    DrawdownThreshold,
    Order,
    Position,
    RiskProfile,
    SymbolRiskCategory,
    User,
)

client = TestClient(app)


class _DummyResult:
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id


class _FakeZerodhaClient:
    def __init__(self, *, last_price: float, prev_close: float | None = None) -> None:
        self.last_price = float(last_price)
        self.prev_close = float(prev_close) if prev_close is not None else None
        self.calls: List[Dict[str, Any]] = []

    def get_quote_bulk(
        self,
        instruments: list[tuple[str, str]],
    ) -> Dict[tuple[str, str], Dict[str, float | None]]:
        out: Dict[tuple[str, str], Dict[str, float | None]] = {}
        for exch, sym in instruments:
            out[(exch, sym)] = {"last_price": self.last_price, "prev_close": self.prev_close}
        return out

    def place_order(self, **params: Any) -> _DummyResult:
        self.calls.append(params)
        return _DummyResult(order_id="OK123")


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "v2-secret"
    os.environ.setdefault("ST_CRYPTO_KEY", "test-risk-engine-v2-exec-gateway-crypto-key")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        user = User(
            username="v2-user",
            password_hash=hash_password("v2-password"),
            role="TRADER",
            display_name="V2 User",
        )
        session.add(user)
        session.commit()


def _seed_v2_config(
    *,
    slippage_guard_bps: float = 0.0,
    gap_guard_pct: float = 0.0,
    leverage_mode: str | None = "OFF",
    max_effective_leverage: float | None = None,
    max_margin_used_pct: float | None = None,
    capital_per_trade: float = 10_000.0,
    max_positions: int = 50,
    max_exposure_pct: float = 100.0,
    daily_loss_pct: float = 0.0,
    hard_daily_loss_pct: float = 0.0,
    max_consecutive_losses: int = 0,
    caution_pct: float = 0.0,
    defense_pct: float = 0.0,
    hard_stop_pct: float = 0.0,
    entry_cutoff_time: str | None = None,
    force_squareoff_time: str | None = None,
    max_trades_per_day: int | None = None,
    max_trades_per_symbol_per_day: int | None = None,
    min_bars_between_trades: int | None = None,
    cooldown_after_loss_bars: int | None = None,
) -> None:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()

        # Clear any previous rows.
        session.query(AnalyticsTrade).delete()
        session.query(Position).delete()
        session.query(Order).delete()
        session.query(Alert).delete()
        session.query(RiskProfile).delete()
        session.query(DrawdownThreshold).delete()
        session.query(SymbolRiskCategory).delete()
        session.commit()

        profile = RiskProfile(
            name="MIS_Default",
            product="MIS",
            capital_per_trade=float(capital_per_trade),
            max_positions=int(max_positions),
            max_exposure_pct=float(max_exposure_pct),
            risk_per_trade_pct=0.0,
            hard_risk_pct=0.0,
            daily_loss_pct=float(daily_loss_pct),
            hard_daily_loss_pct=float(hard_daily_loss_pct),
            max_consecutive_losses=int(max_consecutive_losses),
            drawdown_mode="SETTINGS_BY_CATEGORY",
            enabled=True,
            is_default=True,
            slippage_guard_bps=float(slippage_guard_bps),
            gap_guard_pct=float(gap_guard_pct),
            order_type_policy=None,
            leverage_mode=leverage_mode,
            max_effective_leverage=max_effective_leverage,
            max_margin_used_pct=max_margin_used_pct,
            entry_cutoff_time=entry_cutoff_time,
            force_squareoff_time=force_squareoff_time,
            max_trades_per_day=max_trades_per_day,
            max_trades_per_symbol_per_day=max_trades_per_symbol_per_day,
            min_bars_between_trades=min_bars_between_trades,
            cooldown_after_loss_bars=cooldown_after_loss_bars,
        )
        session.add(profile)
        session.add(
            DrawdownThreshold(
                user_id=None,
                product="MIS",
                category="LC",
                caution_pct=float(caution_pct),
                defense_pct=float(defense_pct),
                hard_stop_pct=float(hard_stop_pct),
            )
        )
        session.add(
            SymbolRiskCategory(
                user_id=user.id,
                broker_name="zerodha",
                symbol="TCS",
                exchange="NSE",
                risk_category="LC",
            )
        )
        session.commit()


def _create_analytics_trade(*, user_id: int, pnl: float, closed_at: datetime | None = None) -> None:
    closed = closed_at or datetime.now(UTC)
    opened = closed - timedelta(hours=1)
    with SessionLocal() as session:
        entry = Order(
            user_id=user_id,
            symbol="TCS",
            exchange="NSE",
            side="BUY",
            qty=1,
            price=100.0,
            order_type="MARKET",
            product="MIS",
            status="SENT",
            mode="AUTO",
            broker_name="zerodha",
        )
        exit_o = Order(
            user_id=user_id,
            symbol="TCS",
            exchange="NSE",
            side="SELL",
            qty=1,
            price=100.0,
            order_type="MARKET",
            product="MIS",
            status="SENT",
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
                pnl=float(pnl),
                r_multiple=None,
                opened_at=opened,
                closed_at=closed,
            )
        )
        session.commit()


def _create_waiting_order_qty_missing() -> int:
    payload: Dict[str, Any] = {
        "secret": "v2-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "v2-user",
        "strategy_name": f"v2-test-strategy-{uuid4().hex}",
        "symbol": "NSE:TCS",
        "exchange": "NSE",
        "interval": "1",
        # Explicitly set product for this test module (it seeds MIS-only profiles).
        "trade_details": {"order_action": "BUY", "quantity": None, "price": 100.0, "product": "MIS"},
    }
    response = client.post("/webhook/tradingview", json=payload)
    assert response.status_code == 201
    data = response.json()
    return int(data["order_id"])


def _create_order_for_eval(
    *,
    user_id: int,
    side: str,
    qty: float,
    price: float,
    created_at: datetime | None = None,
    alert: Alert | None = None,
    symbol: str = "TCS",
    exchange: str = "NSE",
    product: str = "MIS",
    status: str = "WAITING",
) -> int:
    with SessionLocal() as session:
        order = Order(
            user_id=user_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            qty=float(qty),
            price=float(price),
            trigger_price=float(price),
            order_type="MARKET",
            product=product,
            status=status,
            mode="AUTO",
            broker_name="zerodha",
        )
        if created_at is not None:
            order.created_at = created_at
        # Force a non-manual bucket for these v2 unit tests so sizing/caps
        # run against the profile (explicit manual orders should behave
        # differently and are tested elsewhere).
        if alert is None:
            alert = Alert(
                user_id=user_id,
                strategy_id=None,
                symbol=symbol,
                exchange=exchange,
                interval="1",
                action=side,
                qty=float(qty),
                price=float(price),
                platform="SIGMATRADER",
                source="SIGMATRADER",
                raw_payload="{}",
                reason=None,
            )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        order.alert_id = alert.id
        session.add(order)
        session.commit()
        session.refresh(order)
        return int(order.id)


def test_v2_blocks_on_slippage_guard(monkeypatch: Any) -> None:
    _seed_v2_config(slippage_guard_bps=10.0, leverage_mode="OFF")
    order_id = _create_waiting_order_qty_missing()

    from app.api import orders as orders_api

    fake = _FakeZerodhaClient(last_price=105.0, prev_close=100.0)

    def _fake_get_client(db: Any, settings: Any, user_id: int | None = None) -> _FakeZerodhaClient:
        return fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 400
    assert "Slippage guard triggered" in str(resp.json().get("detail") or "")

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "REJECTED_RISK"


def test_v2_clamps_qty_by_margin_caps(monkeypatch: Any) -> None:
    _seed_v2_config(
        slippage_guard_bps=0.0,
        leverage_mode="STATIC",
        max_effective_leverage=5.0,
        max_margin_used_pct=0.5,  # 0.5% of default manual equity (1,000,000) => 5,000
        capital_per_trade=10_000.0,
    )
    order_id = _create_waiting_order_qty_missing()

    from app.api import orders as orders_api

    fake = _FakeZerodhaClient(last_price=100.0, prev_close=100.0)

    def _fake_get_client(db: Any, settings: Any, user_id: int | None = None) -> _FakeZerodhaClient:
        return fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 200

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.status == "SENT"
        # capital_per_trade=10k, price=100 => v2 sizes 100, then margin cap (5k) clamps to 50.
        assert int(order.qty) == 50

    assert fake.calls, "Expected a broker placement call"
    assert int(fake.calls[0].get("quantity") or 0) == 50


def test_v2_blocks_on_gap_guard(monkeypatch: Any) -> None:
    _seed_v2_config(gap_guard_pct=1.0, leverage_mode="OFF")
    order_id = _create_waiting_order_qty_missing()

    from app.api import orders as orders_api

    fake = _FakeZerodhaClient(last_price=105.0, prev_close=100.0)

    def _fake_get_client(db: Any, settings: Any, user_id: int | None = None) -> _FakeZerodhaClient:
        return fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 400
    assert "Gap guard triggered" in str(resp.json().get("detail") or "")


def test_v2_fails_closed_when_missing_risk_profile() -> None:
    _seed_v2_config(leverage_mode="OFF")
    order_id = _create_waiting_order_qty_missing()

    with SessionLocal() as session:
        session.query(RiskProfile).delete()
        session.commit()

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 400
    # v2 bootstraps safe defaults if the DB is missing required rows.
    assert "Zerodha is not connected" in str(resp.json().get("detail") or "")
    with SessionLocal() as session:
        assert session.query(RiskProfile).count() >= 1


def test_v2_fails_closed_when_missing_symbol_category() -> None:
    _seed_v2_config(leverage_mode="OFF")
    order_id = _create_waiting_order_qty_missing()

    with SessionLocal() as session:
        session.query(SymbolRiskCategory).delete()
        session.commit()

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 400
    assert "Zerodha is not connected" in str(resp.json().get("detail") or "")
    with SessionLocal() as session:
        assert session.query(SymbolRiskCategory).count() >= 1


def test_v2_fails_closed_when_missing_drawdown_thresholds() -> None:
    _seed_v2_config(leverage_mode="OFF")
    order_id = _create_waiting_order_qty_missing()

    with SessionLocal() as session:
        session.query(DrawdownThreshold).delete()
        session.commit()

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 400
    assert "Zerodha is not connected" in str(resp.json().get("detail") or "")
    with SessionLocal() as session:
        assert session.query(DrawdownThreshold).count() >= 1


def test_v2_caution_throttles_qty_from_drawdown(monkeypatch: Any) -> None:
    _seed_v2_config(
        leverage_mode="OFF",
        capital_per_trade=10_000.0,
        caution_pct=0.5,
        defense_pct=2.0,
        hard_stop_pct=5.0,
    )

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()
        _create_analytics_trade(user_id=user.id, pnl=-10_000.0)

    order_id = _create_waiting_order_qty_missing()

    from app.api import orders as orders_api

    fake = _FakeZerodhaClient(last_price=100.0, prev_close=100.0)

    def _fake_get_client(db: Any, settings: Any, user_id: int | None = None) -> _FakeZerodhaClient:
        return fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 200

    with SessionLocal() as session:
        order = session.get(Order, order_id)
        assert order is not None
        # capital_per_trade=10k, CAUTION throttles to 7k => qty=floor(7000/100)=70
        assert int(order.qty) == 70


def test_v2_fails_closed_on_auto_leverage_without_broker_support(monkeypatch: Any) -> None:
    _seed_v2_config(
        leverage_mode="AUTO",
        max_effective_leverage=5.0,
        max_margin_used_pct=1.0,
        capital_per_trade=10_000.0,
    )
    order_id = _create_waiting_order_qty_missing()

    from app.api import orders as orders_api

    fake = _FakeZerodhaClient(last_price=100.0, prev_close=100.0)

    def _fake_get_client(db: Any, settings: Any, user_id: int | None = None) -> _FakeZerodhaClient:
        return fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)

    resp = client.post(f"/api/orders/{order_id}/execute")
    assert resp.status_code == 400
    assert "AUTO leverage mode requires Zerodha order_margins support" in str(
        resp.json().get("detail") or ""
    )


def test_v2_blocks_on_daily_loss_limit() -> None:
    _seed_v2_config(leverage_mode="OFF", daily_loss_pct=0.5)
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()
        now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        _create_analytics_trade(
            user_id=user.id,
            pnl=-10_000.0,
            closed_at=now,
        )  # 1% daily loss vs 0.5% limit

        from app.services.risk_engine_v2 import evaluate_order_risk_v2

        order_id = _create_order_for_eval(user_id=user.id, side="BUY", qty=1, price=100.0)
        order = session.get(Order, order_id)
        assert order is not None
        decision = evaluate_order_risk_v2(
            session,
            get_settings(),
            user=user,
            order=order,
            baseline_equity=1_000_000.0,
            now_utc=now,
            product_hint=None,
        )
        assert decision.blocked
        assert any("Daily loss limit reached" in r for r in decision.reasons)


def test_v2_blocks_on_consecutive_losses_limit() -> None:
    _seed_v2_config(leverage_mode="OFF", max_consecutive_losses=2)
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()
        _create_analytics_trade(user_id=user.id, pnl=-100.0)
        _create_analytics_trade(user_id=user.id, pnl=-100.0)

        from app.services.risk_engine_v2 import evaluate_order_risk_v2

        order_id = _create_order_for_eval(user_id=user.id, side="BUY", qty=1, price=100.0)
        order = session.get(Order, order_id)
        assert order is not None
        decision = evaluate_order_risk_v2(
            session,
            get_settings(),
            user=user,
            order=order,
            baseline_equity=1_000_000.0,
            now_utc=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            product_hint=None,
        )
        assert decision.blocked
        assert any("Max consecutive losses reached" in r for r in decision.reasons)


def test_v2_blocks_on_entry_cutoff_time() -> None:
    _seed_v2_config(leverage_mode="OFF", entry_cutoff_time="15:00")
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()
        from app.services.risk_engine_v2 import evaluate_order_risk_v2

        # 12:00 UTC == 17:30 IST, after 15:00 cutoff
        order_id = _create_order_for_eval(user_id=user.id, side="BUY", qty=1, price=100.0)
        order = session.get(Order, order_id)
        assert order is not None
        decision = evaluate_order_risk_v2(
            session,
            get_settings(),
            user=user,
            order=order,
            baseline_equity=1_000_000.0,
            now_utc=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            product_hint=None,
        )
        assert decision.blocked
        assert any("MIS entry cutoff time reached" in r for r in decision.reasons)


def test_v2_blocks_on_force_squareoff_time() -> None:
    _seed_v2_config(leverage_mode="OFF", force_squareoff_time="15:20")
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()
        from app.services.risk_engine_v2 import evaluate_order_risk_v2

        # 12:00 UTC == 17:30 IST, after 15:20 square-off
        order_id = _create_order_for_eval(user_id=user.id, side="BUY", qty=1, price=100.0)
        order = session.get(Order, order_id)
        assert order is not None
        decision = evaluate_order_risk_v2(
            session,
            get_settings(),
            user=user,
            order=order,
            baseline_equity=1_000_000.0,
            now_utc=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            product_hint=None,
        )
        assert decision.blocked
        assert any("MIS force square-off time reached" in r for r in decision.reasons)


def test_v2_blocks_on_max_positions() -> None:
    _seed_v2_config(leverage_mode="OFF", max_positions=1)
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()
        session.add(
            Position(
                broker_name="zerodha",
                symbol="INFY",
                exchange="NSE",
                product="MIS",
                qty=10.0,
                avg_price=100.0,
            )
        )
        session.commit()

        from app.services.risk_engine_v2 import evaluate_order_risk_v2

        order_id = _create_order_for_eval(user_id=user.id, side="BUY", qty=1, price=100.0)
        order = session.get(Order, order_id)
        assert order is not None
        decision = evaluate_order_risk_v2(
            session,
            get_settings(),
            user=user,
            order=order,
            baseline_equity=1_000_000.0,
            now_utc=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            product_hint=None,
        )
        assert decision.blocked
        assert any("Max positions reached" in r for r in decision.reasons)


def test_v2_blocks_on_max_exposure_pct() -> None:
    _seed_v2_config(leverage_mode="OFF", max_exposure_pct=0.5)
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()
        from app.services.risk_engine_v2 import evaluate_order_risk_v2

        # cap_per_trade=10k, price=100 => order value=10k; max_exposure=0.5% of 1m => 5k
        order_id = _create_order_for_eval(user_id=user.id, side="BUY", qty=1, price=100.0)
        order = session.get(Order, order_id)
        assert order is not None
        decision = evaluate_order_risk_v2(
            session,
            get_settings(),
            user=user,
            order=order,
            baseline_equity=1_000_000.0,
            now_utc=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            product_hint=None,
        )
        assert decision.blocked
        assert any("Max exposure exceeded" in r for r in decision.reasons)


def test_v2_blocks_on_max_trades_per_day() -> None:
    _seed_v2_config(leverage_mode="OFF", max_trades_per_day=1)
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()

        # One prior executed entry order (counts towards max_trades_per_day).
        _create_order_for_eval(
            user_id=user.id,
            side="BUY",
            qty=1,
            price=100.0,
            created_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            status="SENT",
        )

        from app.services.risk_engine_v2 import evaluate_order_risk_v2

        order_id = _create_order_for_eval(
            user_id=user.id,
            side="BUY",
            qty=1,
            price=100.0,
            created_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        )
        order = session.get(Order, order_id)
        assert order is not None
        decision = evaluate_order_risk_v2(
            session,
            get_settings(),
            user=user,
            order=order,
            baseline_equity=1_000_000.0,
            now_utc=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            product_hint=None,
        )
        assert decision.blocked
        assert any("Max trades/day reached" in r for r in decision.reasons)


def test_v2_blocks_on_max_trades_per_symbol_per_day() -> None:
    _seed_v2_config(leverage_mode="OFF", max_trades_per_symbol_per_day=1)
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()

        _create_order_for_eval(
            user_id=user.id,
            side="BUY",
            qty=1,
            price=100.0,
            created_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            status="SENT",
        )

        from app.services.risk_engine_v2 import evaluate_order_risk_v2

        order_id = _create_order_for_eval(
            user_id=user.id,
            side="BUY",
            qty=1,
            price=100.0,
            created_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        )
        order = session.get(Order, order_id)
        assert order is not None
        decision = evaluate_order_risk_v2(
            session,
            get_settings(),
            user=user,
            order=order,
            baseline_equity=1_000_000.0,
            now_utc=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            product_hint=None,
        )
        assert decision.blocked
        assert any("Max trades/symbol/day reached" in r for r in decision.reasons)


def test_v2_structural_exit_bypasses_missing_config() -> None:
    # Even with missing config: structural exit should still be allowed.
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "v2-user").one()
        session.query(RiskProfile).delete()
        session.query(DrawdownThreshold).delete()
        session.query(SymbolRiskCategory).delete()
        session.query(Position).delete()
        session.commit()

        session.add(
            Position(
                broker_name="zerodha",
                symbol="TCS",
                exchange="NSE",
                product="MIS",
                qty=10.0,
                avg_price=100.0,
            )
        )
        session.commit()

        from app.services.risk_engine_v2 import evaluate_order_risk_v2

        order_id = _create_order_for_eval(
            user_id=user.id,
            side="SELL",
            qty=1,
            price=100.0,
        )
        order = session.get(Order, order_id)
        assert order is not None
        decision = evaluate_order_risk_v2(
            session,
            get_settings(),
            user=user,
            order=order,
            baseline_equity=0.0,
            now_utc=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            product_hint=None,
        )
        assert not decision.blocked


def test_webhook_dedupes_on_order_id() -> None:
    payload: Dict[str, Any] = {
        "secret": "v2-secret",
        "platform": "TRADINGVIEW",
        "st_user_id": "v2-user",
        "strategy_name": f"v2-dedupe-strategy-{uuid4().hex}",
        "symbol": "NSE:TCS",
        "exchange": "NSE",
        "interval": "1",
        "order_id": "tv-order-123",
        "trade_details": {"order_action": "BUY", "quantity": 1, "price": 100.0},
    }
    r1 = client.post("/webhook/tradingview", json=payload)
    assert r1.status_code == 201
    o1 = r1.json()["order_id"]

    r2 = client.post("/webhook/tradingview", json=payload)
    assert r2.status_code == 201
    data2 = r2.json()
    assert data2["status"] == "deduped"
    assert data2["order_id"] == o1
