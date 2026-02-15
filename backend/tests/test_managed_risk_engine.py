from __future__ import annotations

import os
import json
from unittest.mock import patch

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Alert, ManagedRiskPosition, Order, RiskProfile, User
from app.schemas.managed_risk import DistanceSpec, RiskSpec
from app.services.managed_risk import (
    _update_stop_state,
    ensure_managed_risk_for_executed_order,
    process_managed_risk_once,
)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_TRADINGVIEW_WEBHOOK_SECRET"] = "risk-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        user = User(
            username="risk-user",
            password_hash=hash_password("risk-password"),
            role="TRADER",
            display_name="Risk User",
        )
        session.add(user)
        session.commit()


def test_buy_trailing_updates_and_exit_level() -> None:
    entry = 100.0
    stop_distance = 2.0
    trail_distance = 2.0

    best = entry
    trail: float | None = entry - stop_distance
    active = True

    ltp_seq = [101.0, 102.0, 101.0, 105.0, 103.0]
    trail_seq: list[float] = []
    triggered_at: float | None = None
    for ltp in ltp_seq:
        upd = _update_stop_state(
            side="BUY",
            entry_price=entry,
            stop_distance=stop_distance,
            trail_distance=trail_distance,
            activation_distance=None,
            best=best,
            trail=trail,
            is_trailing_active=active,
            ltp=ltp,
        )
        best = upd.best
        trail = upd.trail
        active = upd.is_trailing_active
        trail_seq.append(float(upd.current_stop))
        if upd.triggered and triggered_at is None:
            triggered_at = ltp

    assert trail_seq == [99.0, 100.0, 100.0, 103.0, 103.0]
    assert triggered_at == 103.0


def test_activation_behavior_for_buy() -> None:
    entry = 100.0
    stop_distance = 2.0
    trail_distance = 2.0
    activation_distance = 4.0

    best = entry
    trail: float | None = None
    active = False

    upd1 = _update_stop_state(
        side="BUY",
        entry_price=entry,
        stop_distance=stop_distance,
        trail_distance=trail_distance,
        activation_distance=activation_distance,
        best=best,
        trail=trail,
        is_trailing_active=active,
        ltp=101.0,
    )
    assert upd1.is_trailing_active is False
    assert upd1.current_stop == 98.0

    upd2 = _update_stop_state(
        side="BUY",
        entry_price=entry,
        stop_distance=stop_distance,
        trail_distance=trail_distance,
        activation_distance=activation_distance,
        best=upd1.best,
        trail=upd1.trail,
        is_trailing_active=upd1.is_trailing_active,
        ltp=103.0,
    )
    assert upd2.is_trailing_active is False
    assert upd2.current_stop == 98.0

    upd3 = _update_stop_state(
        side="BUY",
        entry_price=entry,
        stop_distance=stop_distance,
        trail_distance=trail_distance,
        activation_distance=activation_distance,
        best=upd2.best,
        trail=upd2.trail,
        is_trailing_active=upd2.is_trailing_active,
        ltp=104.0,
    )
    assert upd3.is_trailing_active is True
    # On activation, trail is computed from best-favorable and never worse than SL.
    assert upd3.current_stop == 102.0


def test_sell_trailing_symmetry() -> None:
    entry = 100.0
    stop_distance = 2.0
    trail_distance = 2.0

    best = entry
    trail: float | None = entry + stop_distance
    active = True

    ltp_seq = [99.0, 98.0, 99.0, 95.0, 97.0]
    stop_seq: list[float] = []
    triggered_at: float | None = None
    for ltp in ltp_seq:
        upd = _update_stop_state(
            side="SELL",
            entry_price=entry,
            stop_distance=stop_distance,
            trail_distance=trail_distance,
            activation_distance=None,
            best=best,
            trail=trail,
            is_trailing_active=active,
            ltp=ltp,
        )
        best = upd.best
        trail = upd.trail
        active = upd.is_trailing_active
        stop_seq.append(float(upd.current_stop))
        if upd.triggered and triggered_at is None:
            triggered_at = ltp

    # Mirrors BUY logic: as best falls, stop trails down (never increases).
    assert stop_seq == [101.0, 100.0, 100.0, 97.0, 97.0]
    assert triggered_at == 97.0


def test_idempotent_exit_submission() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "risk-user").one()
        spec = RiskSpec(
            stop_loss=DistanceSpec(enabled=True, mode="ABS", value=2.0),
            trailing_stop=DistanceSpec(enabled=True, mode="ABS", value=2.0),
            trailing_activation=DistanceSpec(enabled=False, mode="ABS", value=0.0),
            exit_order_type="MARKET",
        )
        order = Order(
            user_id=user.id,
            broker_name="zerodha",
            symbol="TCS",
            exchange="NSE",
            side="BUY",
            qty=1,
            price=None,
            order_type="MARKET",
            product="CNC",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            execution_target="LIVE",
            simulated=False,
            risk_spec_json=spec.to_json(),
            is_exit=False,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        mrp = ensure_managed_risk_for_executed_order(
            db,
            settings,
            order=order,
            filled_qty=1,
            avg_price=100.0,
        )
        assert mrp is not None
        db.commit()

    def _fake_exec(order_id: int, *, db, settings, correlation_id=None):  # type: ignore[no-untyped-def]
        o = db.get(Order, order_id)
        assert o is not None
        if o.status == "WAITING":
            o.status = "SENT"
            db.add(o)
            db.commit()
            db.refresh(o)
        return o

    with (
        patch("app.services.managed_risk.is_market_open_now", return_value=True),
        patch("app.services.managed_risk._fetch_ltp", return_value=97.0),
        patch("app.api.orders.execute_order_internal", side_effect=_fake_exec),
    ):
        assert process_managed_risk_once() >= 1
        assert process_managed_risk_once() >= 1

    with SessionLocal() as db:
        exits = db.query(Order).filter(Order.is_exit.is_(True)).all()
        assert len(exits) == 1
        mrp_row = db.query(ManagedRiskPosition).one()
        assert mrp_row.status in {"EXITING", "EXITED"}
        assert mrp_row.exit_order_id == exits[0].id


def test_restart_persists_best_and_trail() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "risk-user").one()
        spec = RiskSpec(
            stop_loss=DistanceSpec(enabled=True, mode="ABS", value=2.0),
            trailing_stop=DistanceSpec(enabled=True, mode="ABS", value=2.0),
            trailing_activation=DistanceSpec(enabled=False, mode="ABS", value=0.0),
            exit_order_type="MARKET",
        )
        order = Order(
            user_id=user.id,
            broker_name="zerodha",
            symbol="INFY",
            exchange="NSE",
            side="BUY",
            qty=1,
            price=None,
            order_type="MARKET",
            product="CNC",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            execution_target="LIVE",
            simulated=False,
            risk_spec_json=spec.to_json(),
            is_exit=False,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        mrp = ensure_managed_risk_for_executed_order(
            db,
            settings,
            order=order,
            filled_qty=1,
            avg_price=100.0,
        )
        assert mrp is not None
        db.commit()

        # Tick 1: move favorable.
        trail_distance = float(mrp.trail_distance or 0) if mrp.trail_distance else None
        upd = _update_stop_state(
            side=mrp.side,
            entry_price=mrp.entry_price,
            stop_distance=float(mrp.stop_distance or 0),
            trail_distance=trail_distance,
            activation_distance=None,
            best=mrp.best_favorable_price,
            trail=mrp.trail_price,
            is_trailing_active=mrp.is_trailing_active,
            ltp=101.0,
        )
        mrp.best_favorable_price = upd.best
        mrp.trail_price = upd.trail
        mrp.is_trailing_active = upd.is_trailing_active
        mrp.last_ltp = 101.0
        db.add(mrp)
        db.commit()

    # "Restart": new session loads persisted state and continues.
    with SessionLocal() as db:
        mrp2 = (
            db.query(ManagedRiskPosition)
            .filter(ManagedRiskPosition.symbol == "INFY")
            .one()
        )
        upd2 = _update_stop_state(
            side=mrp2.side,
            entry_price=mrp2.entry_price,
            stop_distance=float(mrp2.stop_distance or 0),
            trail_distance=(
                float(mrp2.trail_distance or 0) if mrp2.trail_distance else None
            ),
            activation_distance=None,
            best=mrp2.best_favorable_price,
            trail=mrp2.trail_price,
            is_trailing_active=mrp2.is_trailing_active,
            ltp=102.0,
        )
        assert upd2.best == 102.0
        assert upd2.current_stop == 100.0


def test_policy_managed_risk_respects_stop_rules_group_toggle() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "risk-user").one()

        order1 = Order(
            user_id=user.id,
            broker_name="zerodha",
            symbol="TCS",
            exchange="NSE",
            side="BUY",
            qty=1,
            price=100.0,
            order_type="LIMIT",
            product="MIS",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            execution_target="LIVE",
            simulated=False,
            risk_spec_json=None,
            is_exit=False,
        )
        db.add(order1)
        db.commit()
        db.refresh(order1)

        prof = RiskProfile(
            name="Test MIS",
            product="MIS",
            enabled=True,
            is_default=False,
            managed_risk_enabled=True,
            stop_reference="FIXED_PCT",
            fallback_stop_pct=1.0,
            trail_activation_pct=3.0,
            trailing_stop_enabled=True,
            min_stop_distance_pct=0.5,
            max_stop_distance_pct=3.0,
        )

        mrp1 = ensure_managed_risk_for_executed_order(
            db,
            settings,
            order=order1,
            filled_qty=1,
            avg_price=100.0,
            risk_profile=prof,
        )
        assert mrp1 is not None

        order2 = Order(
            user_id=user.id,
            broker_name="zerodha",
            symbol="INFY",
            exchange="NSE",
            side="BUY",
            qty=1,
            price=100.0,
            order_type="LIMIT",
            product="MIS",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            execution_target="LIVE",
            simulated=False,
            risk_spec_json=None,
            is_exit=False,
        )
        db.add(order2)
        db.commit()
        db.refresh(order2)

        prof2 = RiskProfile(
            name="Test MIS (disabled)",
            product="MIS",
            enabled=True,
            is_default=False,
            managed_risk_enabled=False,
            stop_reference="FIXED_PCT",
            fallback_stop_pct=1.0,
            trail_activation_pct=3.0,
            trailing_stop_enabled=True,
            min_stop_distance_pct=0.5,
            max_stop_distance_pct=3.0,
        )
        mrp2 = ensure_managed_risk_for_executed_order(
            db,
            settings,
            order=order2,
            filled_qty=1,
            avg_price=100.0,
            risk_profile=prof2,
        )
        assert mrp2 is None


def test_tradingview_hint_exits_resolve_distances_from_fill_price() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == "risk-user").one()

        tv_payload = {
            "hints": {
                "stop_type": "SL-M",
                "stop_price": 90.0,
                "tp_enabled": "true",
                "take_profit": 110.0,
                "trail_enabled": "true",
                "trail_dist": 2.0,
            }
        }
        alert = Alert(
            user_id=user.id,
            symbol="INFY",
            exchange="NSE",
            interval="1m",
            action="BUY",
            qty=1,
            price=100.0,
            platform="TRADINGVIEW",
            source="TRADINGVIEW",
            raw_payload=json.dumps(tv_payload),
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        spec = RiskSpec(
            stop_loss=DistanceSpec(enabled=True, mode="PCT", value=1.0),
            take_profit=DistanceSpec(enabled=False, mode="PCT", value=0.0),
            trailing_stop=DistanceSpec(enabled=False, mode="PCT", value=0.0),
            trailing_activation=DistanceSpec(enabled=False, mode="PCT", value=0.0),
            exit_order_type="MARKET",
        )
        order = Order(
            user_id=user.id,
            alert_id=int(alert.id),
            broker_name="zerodha",
            symbol="INFY",
            exchange="NSE",
            side="BUY",
            qty=1,
            price=None,
            order_type="MARKET",
            product="MIS",
            gtt=False,
            status="EXECUTED",
            mode="AUTO",
            execution_target="LIVE",
            simulated=False,
            risk_spec_json=spec.to_json(),
            is_exit=False,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        mrp = ensure_managed_risk_for_executed_order(
            db,
            settings,
            order=order,
            filled_qty=1,
            avg_price=100.0,
        )
        assert mrp is not None
        db.commit()
        db.refresh(mrp)

        assert float(mrp.stop_distance or 0.0) == 10.0
        assert float(getattr(mrp, "take_profit_distance") or 0.0) == 10.0
        assert float(mrp.trail_distance or 0.0) == 2.0
