from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import AnalyticsTrade, DrawdownThreshold, Order, RiskProfile, RiskSourceOverride, User
from app.services.risk_compiler import compile_risk_policy
from app.services.risk_unified_store import upsert_unified_risk_global


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-risk-compiler-crypto-key"
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
        upsert_unified_risk_global(
            session,
            enabled=True,
            manual_override_enabled=False,
            baseline_equity_inr=1_000_000.0,
        )


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
        session.query(RiskSourceOverride).delete()
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
                daily_loss_pct=0.0,
                hard_daily_loss_pct=0.0,
                max_consecutive_losses=0,
                drawdown_mode="SETTINGS_BY_CATEGORY",
                enabled=True,
                is_default=True,
                leverage_mode="OFF",
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
            product="CNC",
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
            product="CNC",
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


def test_compiled_summary_drawdown_throttle_applies_to_cap_and_positions() -> None:
    _seed_profile_and_thresholds(product="CNC", category="LC", capital_per_trade=10_000.0, max_positions=10)
    with SessionLocal() as session:
        admin = session.query(User).filter(User.username == "admin").one()

    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    _create_trade(user_id=admin.id, pnl=-5_000.0, closed_at=now)  # 0.5% DD vs 0.5% caution

    with SessionLocal() as session:
        compiled = compile_risk_policy(
            session,
            get_settings(),
            user=admin,
            product="CNC",
            category="LC",
            source_bucket="TRADINGVIEW",
            order_type="MARKET",
            scenario=None,
            symbol=None,
            strategy_id=None,
        )

    assert compiled["effective"]["drawdown_state"] == "CAUTION"
    assert compiled["effective"]["throttle_multiplier"] == 0.7
    assert compiled["effective"]["capital_per_trade"] == 7000.0
    assert compiled["effective"]["max_positions"] == 7
    assert any(o["source"] == "computed" and o["field"] == "capital_per_trade" for o in compiled["overrides"])
    assert compiled["provenance"]["capital_per_trade"]["source"] in {"computed", "source_override", "profile"}


def test_compiled_summary_source_override_is_reflected_with_provenance() -> None:
    _seed_profile_and_thresholds(
        product="CNC",
        category="LC",
        capital_per_trade=10_000.0,
        max_positions=10,
        caution_pct=0.0,
    )
    with SessionLocal() as session:
        session.add(
            RiskSourceOverride(
                source_bucket="TRADINGVIEW",
                product="CNC",
                capital_per_trade=20_000.0,
            )
        )
        session.commit()

        compiled = compile_risk_policy(
            session,
            get_settings(),
            user=None,
            product="CNC",
            category="LC",
            source_bucket="TRADINGVIEW",
            order_type="MARKET",
            scenario=None,
            symbol=None,
            strategy_id=None,
        )

    assert compiled["effective"]["capital_per_trade"] == 20_000.0
    assert compiled["provenance"]["capital_per_trade"]["source"] == "source_override"
    assert any(o["source"] == "source_override" and o["field"] == "capital_per_trade" for o in compiled["overrides"])


def test_compiled_summary_scenario_override_blocks_entries() -> None:
    _seed_profile_and_thresholds(
        product="CNC",
        category="LC",
        capital_per_trade=10_000.0,
        max_positions=10,
        caution_pct=0.0,
    )
    with SessionLocal() as session:
        compiled = compile_risk_policy(
            session,
            get_settings(),
            user=None,
            product="CNC",
            category="LC",
            source_bucket="TRADINGVIEW",
            order_type="MARKET",
            scenario="HARD_STOP",
            symbol=None,
            strategy_id=None,
        )

    assert compiled["effective"]["drawdown_state"] == "HARD_STOP"
    assert compiled["effective"]["allow_new_entries"] is False
    assert any("HARD_STOP" in str(r) for r in compiled["effective"]["blocking_reasons"])
