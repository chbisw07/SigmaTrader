from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_optional
from app.core.config import Settings, get_settings
from app.core.crypto import encrypt_token
from app.db.session import get_db
from app.models import (
    BrokerSecret,
    DrawdownThreshold,
    RiskGlobalConfig,
    RiskProfile,
    RiskSourceOverride,
    SymbolRiskCategory,
    User,
)
from app.schemas.holdings_exit import HoldingsExitConfigUpdate
from app.schemas.risk_backup import RiskSettingsBundleV1, RiskSettingsImportResult
from app.schemas.risk_engine import DrawdownThresholdUpsert, RiskProfileCreate, SymbolRiskCategoryUpsert
from app.schemas.risk_unified import RiskSourceOverrideUpsert, UnifiedRiskGlobalUpdate
from app.services.holdings_exit_config import (
    HOLDINGS_EXIT_BROKER_NAME,
    HOLDINGS_EXIT_CONFIG_KEY,
    get_holdings_exit_config_with_source,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


def _dump_model(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # type: ignore[no-any-return]
    return obj.dict()  # type: ignore[no-any-return, call-arg]


def _schema_keys(schema_cls: Any) -> set[str]:
    if hasattr(schema_cls, "model_fields"):
        return set(schema_cls.model_fields.keys())  # type: ignore[no-any-return]
    return set(schema_cls.__fields__.keys())  # type: ignore[no-any-return, attr-defined]


def _coerce_schema(schema_cls: Any, raw: dict[str, Any]) -> Any:
    keys = _schema_keys(schema_cls)
    filtered = {k: raw.get(k) for k in keys if k in raw}
    return schema_cls(**filtered)


def _orm_cols(obj: Any) -> dict[str, Any]:
    return {k: getattr(obj, k) for k in obj.__mapper__.columns.keys()}  # type: ignore[attr-defined]


def _ensure_singleton_risk_global(db: Session) -> RiskGlobalConfig:
    row = db.query(RiskGlobalConfig).filter(RiskGlobalConfig.singleton_key == "GLOBAL").one_or_none()
    if row is not None:
        return row
    row = RiskGlobalConfig(
        singleton_key="GLOBAL",
        enabled=True,
        manual_override_enabled=False,
        baseline_equity_inr=1_000_000.0,
    )
    db.add(row)
    db.flush()
    return row


def _upsert_holdings_exit_config(
    db: Session,
    *,
    settings: Settings,
    payload: HoldingsExitConfigUpdate,
) -> None:
    cfg = {
        "enabled": bool(payload.enabled),
        "allowlist_symbols": (str(payload.allowlist_symbols or "").strip() or None),
    }
    value = json.dumps(cfg, ensure_ascii=False)
    encrypted = encrypt_token(settings, value)

    row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == HOLDINGS_EXIT_BROKER_NAME,
            BrokerSecret.key == HOLDINGS_EXIT_CONFIG_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        row = BrokerSecret(
            user_id=None,
            broker_name=HOLDINGS_EXIT_BROKER_NAME,
            key=HOLDINGS_EXIT_CONFIG_KEY,
            value_encrypted=encrypted,
        )
    else:
        row.value_encrypted = encrypted
    db.add(row)


@router.get("/export", response_model=RiskSettingsBundleV1)
def export_risk_settings_bundle(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> RiskSettingsBundleV1:
    now = datetime.now(UTC)
    warnings: list[str] = []
    counts: dict[str, int] = {}

    g = db.query(RiskGlobalConfig).filter(RiskGlobalConfig.singleton_key == "GLOBAL").one_or_none()
    if g is None:
        warnings.append("Risk globals row missing; exporting built-in defaults.")
        global_settings = UnifiedRiskGlobalUpdate(
            enabled=True,
            manual_override_enabled=False,
            baseline_equity_inr=1_000_000.0,
        )
    else:
        global_settings = UnifiedRiskGlobalUpdate(
            enabled=bool(g.enabled),
            manual_override_enabled=bool(g.manual_override_enabled),
            baseline_equity_inr=float(g.baseline_equity_inr or 0.0),
        )

    profiles = db.query(RiskProfile).order_by(RiskProfile.product, RiskProfile.name).all()
    risk_profiles = [_coerce_schema(RiskProfileCreate, _orm_cols(p)) for p in profiles]
    counts["risk_profiles"] = len(risk_profiles)

    dd_rows = (
        db.query(DrawdownThreshold)
        .filter(DrawdownThreshold.user_id.is_(None))
        .order_by(DrawdownThreshold.product, DrawdownThreshold.category)
        .all()
    )
    drawdown_thresholds = [_coerce_schema(DrawdownThresholdUpsert, _orm_cols(r)) for r in dd_rows]
    counts["drawdown_thresholds"] = len(drawdown_thresholds)

    ov_rows = (
        db.query(RiskSourceOverride)
        .order_by(RiskSourceOverride.source_bucket.asc(), RiskSourceOverride.product.asc())
        .all()
    )
    source_overrides = [_coerce_schema(RiskSourceOverrideUpsert, _orm_cols(r)) for r in ov_rows]
    counts["source_overrides"] = len(source_overrides)

    sym_global_rows = (
        db.query(SymbolRiskCategory)
        .filter(SymbolRiskCategory.user_id.is_(None))
        .order_by(SymbolRiskCategory.broker_name, SymbolRiskCategory.exchange, SymbolRiskCategory.symbol)
        .all()
    )
    symbol_categories_global = [_coerce_schema(SymbolRiskCategoryUpsert, _orm_cols(r)) for r in sym_global_rows]
    counts["symbol_categories_global"] = len(symbol_categories_global)

    symbol_categories_user: list[SymbolRiskCategoryUpsert] = []
    if user is not None:
        sym_user_rows = (
            db.query(SymbolRiskCategory)
            .filter(SymbolRiskCategory.user_id == user.id)
            .order_by(SymbolRiskCategory.broker_name, SymbolRiskCategory.exchange, SymbolRiskCategory.symbol)
            .all()
        )
        symbol_categories_user = [_coerce_schema(SymbolRiskCategoryUpsert, _orm_cols(r)) for r in sym_user_rows]
        counts["symbol_categories_user"] = len(symbol_categories_user)
    else:
        warnings.append(
            "No authenticated user session detected; user-scoped symbol categories omitted (symbol_categories_user=0)."
        )
        counts["symbol_categories_user"] = 0

    he_cfg, he_source = get_holdings_exit_config_with_source(db, settings)
    if he_source != "db":
        warnings.append(f'Holdings exit config source is "{he_source}"; exporting current effective value.')
    holdings_exit_config = HoldingsExitConfigUpdate(**he_cfg.to_dict())
    counts["holdings_exit_config"] = 1

    return RiskSettingsBundleV1(
        schema_version=1,
        exported_at=now,
        exported_by=(user.username if user is not None else None),
        warnings=warnings,
        counts=counts,
        global_settings=global_settings,
        risk_profiles=risk_profiles,
        drawdown_thresholds=drawdown_thresholds,
        source_overrides=source_overrides,
        symbol_categories_global=symbol_categories_global,
        symbol_categories_user=symbol_categories_user,
        holdings_exit_config=holdings_exit_config,
    )


@router.post("/import", response_model=RiskSettingsImportResult)
def import_risk_settings_bundle(
    payload: RiskSettingsBundleV1,
    force: Annotated[bool, Query()] = False,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_current_user_optional),
) -> RiskSettingsImportResult:
    if int(payload.schema_version or 0) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported schema_version.",
        )

    # Validate risk profiles consistency (fail fast before mutating).
    names = [p.name.strip() for p in payload.risk_profiles]
    if any(not n for n in names):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RiskProfile.name cannot be empty.")
    if len(set(names)) != len(names):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate risk profile names.")

    defaults_by_product: dict[str, int] = {}
    for p in payload.risk_profiles:
        if bool(p.is_default):
            defaults_by_product[str(p.product)] = defaults_by_product.get(str(p.product), 0) + 1
    multi_defaults = {k: v for k, v in defaults_by_product.items() if v > 1}
    if multi_defaults:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Multiple default risk profiles for product(s): {sorted(multi_defaults.keys())}.",
        )

    if user is None and payload.symbol_categories_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot import user-scoped symbol categories without an authenticated session.",
        )

    if not force:
        if not payload.risk_profiles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Import bundle has 0 risk_profiles; refusing to wipe existing settings without force=1.",
            )
        if user is not None and not payload.symbol_categories_user:
            existing = (
                db.query(SymbolRiskCategory)
                .filter(SymbolRiskCategory.user_id == user.id)
                .count()
            )
            if existing > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Import bundle has 0 symbol_categories_user; refusing to wipe existing user mappings "
                        "without force=1."
                    ),
                )

    imported_at = datetime.now(UTC)
    counts: dict[str, int] = {}

    try:
        # Replace-all semantics: delete and re-create atomically.
        g = _ensure_singleton_risk_global(db)
        g.enabled = bool(payload.global_settings.enabled)
        g.manual_override_enabled = bool(payload.global_settings.manual_override_enabled)
        g.baseline_equity_inr = float(payload.global_settings.baseline_equity_inr or 0.0)
        db.add(g)

        db.query(RiskSourceOverride).delete()
        for o in payload.source_overrides:
            data = _dump_model(o)
            row = RiskSourceOverride(**data)  # type: ignore[arg-type]
            db.add(row)
        counts["source_overrides"] = len(payload.source_overrides)

        db.query(DrawdownThreshold).filter(DrawdownThreshold.user_id.is_(None)).delete()
        for t in payload.drawdown_thresholds:
            data = _dump_model(t)
            row = DrawdownThreshold(user_id=None, **data)  # type: ignore[arg-type]
            db.add(row)
        counts["drawdown_thresholds"] = len(payload.drawdown_thresholds)

        db.query(RiskProfile).delete()
        for p in payload.risk_profiles:
            data = _dump_model(p)
            row = RiskProfile(**data)  # type: ignore[arg-type]
            db.add(row)
        counts["risk_profiles"] = len(payload.risk_profiles)

        db.query(SymbolRiskCategory).filter(SymbolRiskCategory.user_id.is_(None)).delete()
        for c in payload.symbol_categories_global:
            data = _dump_model(c)
            row = SymbolRiskCategory(user_id=None, **data)  # type: ignore[arg-type]
            db.add(row)
        counts["symbol_categories_global"] = len(payload.symbol_categories_global)

        if user is not None:
            db.query(SymbolRiskCategory).filter(SymbolRiskCategory.user_id == user.id).delete()
            for c in payload.symbol_categories_user:
                data = _dump_model(c)
                row = SymbolRiskCategory(user_id=int(user.id), **data)  # type: ignore[arg-type]
                db.add(row)
            counts["symbol_categories_user"] = len(payload.symbol_categories_user)
        else:
            counts["symbol_categories_user"] = 0

        _upsert_holdings_exit_config(db, settings=settings, payload=payload.holdings_exit_config)
        counts["holdings_exit_config"] = 1

        db.commit()
        return RiskSettingsImportResult(ok=True, imported_at=imported_at, counts=counts)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Import failed: {exc}",
        ) from exc


__all__ = ["router"]
