from __future__ import annotations

import os

from app.core.auth import hash_password
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.api.risk_backup import export_risk_settings_bundle, import_risk_settings_bundle
from app.models import (
    DrawdownThreshold,
    RiskGlobalConfig,
    RiskProfile,
    RiskSourceOverride,
    SymbolRiskCategory,
    User,
)
from app.services.holdings_exit_config import (
    HoldingsExitConfig,
    get_holdings_exit_config_with_source,
    set_holdings_exit_config,
)


def setup_module() -> None:  # type: ignore[override]
    os.environ.setdefault("ST_CRYPTO_KEY", "test-risk-settings-backup-crypto-key")
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        session.add(
            User(
                username="backup-user",
                password_hash=hash_password("backup-password"),
                role="TRADER",
                display_name="Backup User",
            )
        )
        session.commit()


def _seed_settings() -> int:
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "backup-user").one()

        session.query(RiskSourceOverride).delete()
        session.query(DrawdownThreshold).delete()
        session.query(RiskProfile).delete()
        session.query(SymbolRiskCategory).delete()
        session.query(RiskGlobalConfig).delete()
        session.commit()

        session.add(
            RiskGlobalConfig(
                singleton_key="GLOBAL",
                enabled=True,
                manual_override_enabled=False,
                baseline_equity_inr=123_456.0,
            )
        )

        session.add(
            RiskProfile(
                name="CNC_PROFILE",
                product="CNC",
                capital_per_trade=50_000.0,
                max_positions=5,
                max_exposure_pct=25.0,
                enabled=True,
                is_default=True,
            )
        )
        session.add(
            RiskProfile(
                name="MIS_PROFILE",
                product="MIS",
                capital_per_trade=10_000.0,
                max_positions=10,
                max_exposure_pct=100.0,
                order_type_policy="MARKET,LIMIT",
                enabled=True,
                is_default=True,
            )
        )

        session.add(
            DrawdownThreshold(
                user_id=None,
                product="CNC",
                category="LC",
                caution_pct=1.0,
                defense_pct=2.0,
                hard_stop_pct=3.0,
            )
        )

        session.add(
            RiskSourceOverride(
                source_bucket="TRADINGVIEW",
                product="MIS",
                allow_product=True,
                max_order_value_pct=1.5,
                order_type_policy="MARKET",
            )
        )

        session.add(
            SymbolRiskCategory(
                user_id=None,
                broker_name="*",
                exchange="*",
                symbol="*",
                risk_category="LC",
            )
        )
        session.add(
            SymbolRiskCategory(
                user_id=int(user.id),
                broker_name="zerodha",
                exchange="NSE",
                symbol="TCS",
                risk_category="LC",
            )
        )
        session.commit()

        set_holdings_exit_config(
            session,
            get_settings(),
            HoldingsExitConfig(enabled=True, allowlist_symbols="NSE:TCS,NSE:INFY"),
        )

        return int(user.id)


def test_export_import_roundtrip() -> None:
    user_id = _seed_settings()

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "backup-user").one()
        exported = export_risk_settings_bundle(db=session, settings=get_settings(), user=user)
        data = exported.model_dump() if hasattr(exported, "model_dump") else exported.dict()

        assert data["schema_version"] == 1
        assert data["global_settings"]["baseline_equity_inr"] == 123_456.0
        assert len(data["risk_profiles"]) == 2
        assert len(data["drawdown_thresholds"]) == 1
        assert len(data["source_overrides"]) == 1
        assert len(data["symbol_categories_global"]) == 1
        assert len(data["symbol_categories_user"]) == 1
        assert data["holdings_exit_config"]["enabled"] is True

    with SessionLocal() as session:
        session.query(RiskSourceOverride).delete()
        session.query(DrawdownThreshold).delete()
        session.query(RiskProfile).delete()
        session.query(SymbolRiskCategory).delete()
        session.query(RiskGlobalConfig).delete()
        session.commit()

    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "backup-user").one()
        out = import_risk_settings_bundle(
            payload=exported,
            db=session,
            settings=get_settings(),
            user=user,
        )
        out_data = out.model_dump() if hasattr(out, "model_dump") else out.dict()
        assert out_data["ok"] is True
        assert out_data["counts"]["risk_profiles"] == 2
        assert out_data["counts"]["holdings_exit_config"] == 1

    with SessionLocal() as session:
        g = session.query(RiskGlobalConfig).filter(RiskGlobalConfig.singleton_key == "GLOBAL").one()
        assert float(g.baseline_equity_inr) == 123_456.0

        profs = session.query(RiskProfile).order_by(RiskProfile.product, RiskProfile.name).all()
        assert [p.name for p in profs] == ["CNC_PROFILE", "MIS_PROFILE"]

        dd = session.query(DrawdownThreshold).filter(DrawdownThreshold.user_id.is_(None)).all()
        assert len(dd) == 1

        ovs = session.query(RiskSourceOverride).all()
        assert len(ovs) == 1
        assert ovs[0].order_type_policy == "MARKET"

        globals_sym = session.query(SymbolRiskCategory).filter(SymbolRiskCategory.user_id.is_(None)).all()
        assert len(globals_sym) == 1
        user_sym = session.query(SymbolRiskCategory).filter(SymbolRiskCategory.user_id == user_id).all()
        assert len(user_sym) == 1

        cfg, source = get_holdings_exit_config_with_source(session, get_settings())
        assert source in ("db", "db_invalid", "env_default")
        assert cfg.enabled is True
        assert cfg.allowlist_symbols == "NSE:TCS,NSE:INFY"


def test_import_rejects_multiple_defaults_per_product() -> None:
    _seed_settings()
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == "backup-user").one()
        exported = export_risk_settings_bundle(db=session, settings=get_settings(), user=user)
        patch = exported.model_copy(deep=True) if hasattr(exported, "model_copy") else exported.copy(deep=True)
        data = patch.model_dump() if hasattr(patch, "model_dump") else patch.dict()

        cnc = [p for p in data["risk_profiles"] if p.get("product") == "CNC"]
        assert cnc
        data["risk_profiles"].append({**cnc[0], "name": "CNC_PROFILE_2", "is_default": True})

        from app.schemas.risk_backup import RiskSettingsBundleV1

        patched = RiskSettingsBundleV1(**data)
        try:
            import_risk_settings_bundle(payload=patched, db=session, settings=get_settings(), user=user)
            raise AssertionError("expected HTTPException")
        except Exception as exc:
            assert "Multiple default risk profiles" in str(exc)
