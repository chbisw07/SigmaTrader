from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from app.core.auth import hash_password
from app.core.config import get_settings
from app.core.crypto import decrypt_token, encrypt_token
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import BrokerSecret, Order, Position, User
from app.services.risk_policy_store import RISK_POLICY_BROKER_NAME, RISK_POLICY_KEY

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_CRYPTO_KEY", "test-risk-policy-selective-enforcement")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        user = User(
            username="rp-user",
            password_hash=hash_password("rp-password"),
            role="TRADER",
            display_name="RP User",
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


def _patch_zerodha(monkeypatch: Any) -> _AlwaysSuccessClient:
    from app.api import orders as orders_api

    fake = _AlwaysSuccessClient()

    def _fake_get_client(db: Any, settings: Any) -> _AlwaysSuccessClient:
        return fake

    monkeypatch.setattr(orders_api, "_get_zerodha_client", _fake_get_client)
    return fake


def _set_policy(overrides: Dict[str, Any]) -> None:
    defaults = client.get("/api/risk-policy/defaults").json()
    merged = {**defaults, **overrides}

    exec_safety = dict(merged.get("execution_safety") or {})
    exec_safety["allow_mis"] = True
    exec_safety["allow_cnc"] = True
    exec_safety.setdefault("allow_short_selling", True)
    exec_safety.setdefault("max_order_value_pct", 0)
    merged["execution_safety"] = exec_safety

    resp = client.put("/api/risk-policy", json=merged)
    assert resp.status_code == 200


def _enforcement(**overrides: Any) -> Dict[str, bool]:
    base: Dict[str, bool] = {
        "account_level": False,
        "per_trade": False,
        "position_sizing": False,
        "stop_rules": False,
        "trade_frequency": False,
        "loss_controls": False,
        "correlation_controls": False,
        "execution_safety": False,
        "emergency_controls": False,
        "overrides": False,
    }
    for k, v in overrides.items():
        base[str(k)] = bool(v)
    return base


def _create_waiting_order(*, side: str = "BUY", product: str = "MIS") -> int:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "rp-user").one()
        order = Order(
            user_id=int(user.id),
            broker_name="zerodha",
            alert_id=None,
            strategy_id=None,
            portfolio_group_id=None,
            deployment_id=None,
            deployment_action_id=None,
            symbol="NSE:TCS",
            exchange="NSE",
            side=side,
            qty=1.0,
            price=100.0,
            order_type="LIMIT",
            product=product,
            gtt=False,
            synthetic_gtt=False,
            status="WAITING",
            mode="MANUAL",
            execution_target="LIVE",
            simulated=False,
            error_message=None,
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return int(order.id)


def test_panic_stop_does_not_block_when_emergency_group_disabled(
    monkeypatch: Any,
) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "emergency_controls": {"panic_stop": True},
            "enforcement": _enforcement(
                execution_safety=True, emergency_controls=False
            ),
        }
    )

    oid = _create_waiting_order()
    res = client.post(f"/api/orders/{oid}/execute")
    assert res.status_code == 200
    assert res.json()["status"] == "SENT"


def test_overrides_ignored_when_overrides_group_disabled(monkeypatch: Any) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "enforcement": _enforcement(execution_safety=True, overrides=False),
            "overrides": {
                "TRADINGVIEW": {"MIS": {}, "CNC": {}},
                "SIGMATRADER": {"MIS": {"allow": False}, "CNC": {}},
            },
        }
    )

    oid = _create_waiting_order(product="MIS")
    res = client.post(f"/api/orders/{oid}/execute")
    assert res.status_code == 200
    assert res.json()["status"] == "SENT"


def test_execution_safety_group_toggle_controls_short_selling_gate(
    monkeypatch: Any,
) -> None:
    _patch_zerodha(monkeypatch)

    _set_policy(
        {
            "enabled": True,
            "enforcement": _enforcement(execution_safety=True),
            "execution_safety": {
                "allow_mis": True,
                "allow_cnc": True,
                "allow_short_selling": False,
                "max_order_value_pct": 0,
            },
        }
    )

    sell_short = _create_waiting_order(side="SELL", product="MIS")
    blocked = client.post(f"/api/orders/{sell_short}/execute")
    assert blocked.status_code == 400
    with SessionLocal() as session:
        o = session.get(Order, sell_short)
        assert o is not None
        assert o.status == "REJECTED_RISK"
        assert "execution_safety" in (o.error_message or "")

    _set_policy(
        {
            "enabled": True,
            "enforcement": _enforcement(execution_safety=False),
            "execution_safety": {
                "allow_mis": True,
                "allow_cnc": True,
                "allow_short_selling": False,
                "max_order_value_pct": 0,
            },
        }
    )

    sell_allowed = _create_waiting_order(side="SELL", product="MIS")
    allowed = client.post(f"/api/orders/{sell_allowed}/execute")
    assert allowed.status_code == 200


def test_account_level_group_toggle_controls_max_open_positions(
    monkeypatch: Any,
) -> None:
    _patch_zerodha(monkeypatch)

    with SessionLocal() as session:
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

    _set_policy(
        {
            "enabled": True,
            "enforcement": _enforcement(account_level=True, execution_safety=True),
            "account_risk": {
                "max_daily_loss_pct": 0,
                "max_daily_loss_abs": None,
                "max_open_positions": 1,
                "max_concurrent_symbols": 999,
                "max_exposure_pct": 0,
            },
        }
    )

    blocked_id = _create_waiting_order(side="BUY", product="MIS")
    blocked = client.post(f"/api/orders/{blocked_id}/execute")
    assert blocked.status_code == 400

    _set_policy(
        {
            "enabled": True,
            "enforcement": _enforcement(account_level=False, execution_safety=True),
            "account_risk": {
                "max_daily_loss_pct": 0,
                "max_daily_loss_abs": None,
                "max_open_positions": 1,
                "max_concurrent_symbols": 999,
                "max_exposure_pct": 0,
            },
        }
    )
    allowed_id = _create_waiting_order(side="BUY", product="MIS")
    allowed = client.post(f"/api/orders/{allowed_id}/execute")
    assert allowed.status_code == 200


def test_position_sizing_group_toggle_controls_capital_per_trade(
    monkeypatch: Any,
) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "enforcement": _enforcement(position_sizing=True, execution_safety=False),
            "position_sizing": {
                "sizing_mode": "FIXED_CAPITAL",
                "capital_per_trade": 50,
                "allow_scale_in": False,
                "pyramiding": 1,
            },
        }
    )
    blocked_id = _create_waiting_order(side="BUY", product="MIS")
    blocked = client.post(f"/api/orders/{blocked_id}/execute")
    assert blocked.status_code == 400

    _set_policy(
        {
            "enabled": True,
            "enforcement": _enforcement(position_sizing=False, execution_safety=False),
            "position_sizing": {
                "sizing_mode": "FIXED_CAPITAL",
                "capital_per_trade": 50,
                "allow_scale_in": False,
                "pyramiding": 1,
            },
        }
    )
    allowed_id = _create_waiting_order(side="BUY", product="MIS")
    allowed = client.post(f"/api/orders/{allowed_id}/execute")
    assert allowed.status_code == 200


def test_per_trade_group_toggle_controls_per_trade_risk_blocks(
    monkeypatch: Any,
) -> None:
    _patch_zerodha(monkeypatch)
    _set_policy(
        {
            "enabled": True,
            "enforcement": _enforcement(
                per_trade=True,
                stop_rules=True,
                execution_safety=False,
            ),
            "equity": {"equity_mode": "MANUAL", "manual_equity_inr": 1000},
            "trade_risk": {
                "max_risk_per_trade_pct": 0.5,
                "hard_max_risk_pct": 0.001,
                "stop_loss_mandatory": True,
                "stop_reference": "ATR",
            },
            "stop_rules": {
                "atr_period": 14,
                "initial_stop_atr": 2,
                "fallback_stop_pct": 1,
                "min_stop_distance_pct": 0.5,
                "max_stop_distance_pct": 3,
                "trailing_stop_enabled": True,
                "trail_activation_atr": 2.5,
                "trail_activation_pct": 3,
            },
        }
    )
    blocked_id = _create_waiting_order(side="BUY", product="MIS")
    blocked = client.post(f"/api/orders/{blocked_id}/execute")
    assert blocked.status_code == 400

    _set_policy(
        {
            "enabled": True,
            "enforcement": _enforcement(
                per_trade=False,
                stop_rules=True,
                execution_safety=False,
            ),
            "equity": {"equity_mode": "MANUAL", "manual_equity_inr": 1000},
            "trade_risk": {
                "max_risk_per_trade_pct": 0.5,
                "hard_max_risk_pct": 0.001,
                "stop_loss_mandatory": True,
                "stop_reference": "ATR",
            },
        }
    )
    allowed_id = _create_waiting_order(side="BUY", product="MIS")
    allowed = client.post(f"/api/orders/{allowed_id}/execute")
    assert allowed.status_code == 200


def test_risk_policy_lazy_backfills_missing_enforcement_flags() -> None:
    settings = get_settings()
    defaults = client.get("/api/risk-policy/defaults").json()
    defaults.pop("enforcement", None)
    defaults["enabled"] = True
    defaults["version"] = 1

    encrypted = encrypt_token(settings, json.dumps(defaults, ensure_ascii=False))
    with SessionLocal() as session:
        session.query(BrokerSecret).delete()
        session.add(
            BrokerSecret(
                user_id=None,
                broker_name=RISK_POLICY_BROKER_NAME,
                key=RISK_POLICY_KEY,
                value_encrypted=encrypted,
            )
        )
        session.commit()

    resp = client.get("/api/risk-policy")
    assert resp.status_code == 200
    policy = resp.json()["policy"]
    enf = policy.get("enforcement") or {}
    assert enf.get("account_level") is True
    assert enf.get("per_trade") is True
    assert enf.get("position_sizing") is True
    assert enf.get("stop_rules") is True
    assert enf.get("trade_frequency") is True
    assert enf.get("loss_controls") is True
    assert enf.get("correlation_controls") is True
    assert enf.get("execution_safety") is True
    assert enf.get("emergency_controls") is True
    assert enf.get("overrides") is True

    with SessionLocal() as session:
        row = (
            session.query(BrokerSecret)
            .filter(
                BrokerSecret.broker_name == RISK_POLICY_BROKER_NAME,
                BrokerSecret.key == RISK_POLICY_KEY,
                BrokerSecret.user_id.is_(None),
            )
            .one()
        )
        raw = decrypt_token(settings, row.value_encrypted)
        parsed = json.loads(raw)
        assert isinstance(parsed.get("enforcement"), dict)
        assert parsed["enforcement"].get("account_level") is True
