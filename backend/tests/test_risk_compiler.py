from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import AnalyticsTrade, DrawdownThreshold, Order, RiskProfile, User
from app.schemas.risk_policy import RiskPolicy
from app.services.risk_compiler import compile_risk_policy
from app.services.risk_policy_store import set_risk_policy


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-risk-compiler-crypto-key"
    os.environ["ST_RISK_ENGINE_V2_ENABLED"] = "1"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            User(
                username="admin",
                password_hash=hash_password("admin-password"),
                role="ADMIN",
                display_name="Admin",
            )
        )
        session.commit()

    with SessionLocal() as session:
        settings = get_settings()
        policy = RiskPolicy(enabled=True)
        set_risk_policy(session, settings, policy)


def _seed_profile_and_thresholds(
    *,
    product: str,
    category: str,
    capital_per_trade: float = 10_000.0,
    max_positions: int = 10,
    caution_pct: float = 0.5,
    defense_pct: float = 2.0,
    hard_stop_pct: float = 3.0,
) -> None:
    with SessionLocal() as session:
        session.query(RiskProfile).delete()
        session.query(DrawdownThreshold).delete()
        session.query(AnalyticsTrade).delete()
        session.query(Order).delete()
        session.commit()

        session.add(
            RiskProfile(
                name=f"{product}_DEFAULT",
                product=product,
                capital_per_trade=float(capital_per_trade),
                max_positions=int(max_positions),
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
                product=product,
                category=category,
                caution_pct=float(caution_pct),
                defense_pct=float(defense_pct),
                hard_stop_pct=float(hard_stop_pct),
            )
        )
        session.commit()


def _create_trade(*, user_id: int, pnl: float, closed_at: datetime) -> None:
    opened = closed_at - timedelta(hours=1)
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
            status="EXECUTED",
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
                pnl=float(pnl),
                r_multiple=None,
                opened_at=opened,
                closed_at=closed_at,
            )
        )
        session.commit()


def test_compiler_resolves_state_and_throttles_caution() -> None:
    _seed_profile_and_thresholds(product="MIS", category="LC", caution_pct=0.5, defense_pct=2.0, hard_stop_pct=5.0)
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "admin").one()
        _create_trade(user_id=user.id, pnl=-10_000.0, closed_at=now)  # 1% DD

        settings = get_settings()
        compiled = compile_risk_policy(
            session,
            settings,
            user=user,
            product="MIS",
            category="LC",
        )

    v2 = compiled["effective"]["risk_engine_v2"]
    assert v2["drawdown_state"] == "CAUTION"
    assert float(v2["throttle_multiplier"]) == 0.7
    assert float(v2["capital_per_trade"]) == 7000.0
    assert int(v2["max_positions"]) == 7


def test_compiler_blocks_entries_in_defense_for_non_etf_lc() -> None:
    _seed_profile_and_thresholds(product="MIS", category="SC", caution_pct=0.0, defense_pct=0.5, hard_stop_pct=5.0)
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "admin").one()
        _create_trade(user_id=user.id, pnl=-10_000.0, closed_at=now)  # 1% DD => DEFENSE

        settings = get_settings()
        compiled = compile_risk_policy(
            session,
            settings,
            user=user,
            product="MIS",
            category="SC",
        )

    v2 = compiled["effective"]["risk_engine_v2"]
    assert v2["drawdown_state"] == "DEFENSE"
    assert v2["allow_new_entries"] is False
    assert compiled["effective"]["allow_new_entries"] is False
    assert compiled["effective"]["blocking_reasons"]


def test_compiler_hard_stop_blocks_entries() -> None:
    _seed_profile_and_thresholds(product="MIS", category="LC", caution_pct=0.0, defense_pct=0.0, hard_stop_pct=0.5)
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "admin").one()
        _create_trade(user_id=user.id, pnl=-10_000.0, closed_at=now)  # 1% DD => HARD_STOP

        settings = get_settings()
        compiled = compile_risk_policy(
            session,
            settings,
            user=user,
            product="MIS",
            category="LC",
        )

    v2 = compiled["effective"]["risk_engine_v2"]
    assert v2["drawdown_state"] == "HARD_STOP"
    assert v2["allow_new_entries"] is False
    assert compiled["effective"]["allow_new_entries"] is False


def test_compiler_supports_scenario_override() -> None:
    _seed_profile_and_thresholds(product="MIS", category="LC", caution_pct=0.5, defense_pct=2.0, hard_stop_pct=5.0)
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "admin").one()
        _create_trade(user_id=user.id, pnl=-10_000.0, closed_at=now)  # computed CAUTION

        settings = get_settings()
        compiled = compile_risk_policy(
            session,
            settings,
            user=user,
            product="MIS",
            category="LC",
            scenario="NORMAL",
        )

    v2 = compiled["effective"]["risk_engine_v2"]
    assert v2["drawdown_state"] == "NORMAL"
    assert compiled["context"]["scenario"] == "NORMAL"
    assert any(
        o.get("field") == "risk_engine_v2.drawdown_state" and o.get("source") == "STATE_OVERRIDE"
        for o in compiled.get("overrides") or []
    )


def test_compiler_includes_risk_policy_by_source() -> None:
    _seed_profile_and_thresholds(product="CNC", category="LC")
    with SessionLocal() as session:
        settings = get_settings()
        user = session.query(User).filter(User.username == "admin").one()
        compiled = compile_risk_policy(
            session,
            settings,
            user=user,
            product="CNC",
            category="LC",
        )

    rp = compiled["effective"]["risk_policy_by_source"]
    assert "TRADINGVIEW" in rp and "SIGMATRADER" in rp
    assert isinstance(rp["TRADINGVIEW"]["capital_per_trade"], (int, float))
