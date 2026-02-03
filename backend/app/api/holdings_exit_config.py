from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import BrokerSecret
from app.schemas.holdings_exit import HoldingsExitConfigRead, HoldingsExitConfigUpdate
from app.services.holdings_exit_config import (
    HOLDINGS_EXIT_BROKER_NAME,
    HOLDINGS_EXIT_CONFIG_KEY,
    HoldingsExitConfig,
    get_holdings_exit_config_with_source,
    set_holdings_exit_config,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


@router.get("/config", response_model=HoldingsExitConfigRead)
def read_holdings_exit_config(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HoldingsExitConfigRead:
    cfg, source = get_holdings_exit_config_with_source(db, settings)
    updated_at = None
    if source in ("db", "db_invalid"):
        row = (
            db.query(BrokerSecret)
            .filter(
                BrokerSecret.broker_name == HOLDINGS_EXIT_BROKER_NAME,
                BrokerSecret.key == HOLDINGS_EXIT_CONFIG_KEY,
                BrokerSecret.user_id.is_(None),
            )
            .one_or_none()
        )
        updated_at = row.updated_at if row is not None else None
    return HoldingsExitConfigRead(
        enabled=bool(cfg.enabled),
        allowlist_symbols=cfg.allowlist_symbols,
        source=source,
        updated_at=updated_at,
    )


@router.put("/config", response_model=HoldingsExitConfigRead)
def update_holdings_exit_config(
    payload: HoldingsExitConfigUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> HoldingsExitConfigRead:
    cfg = HoldingsExitConfig(
        enabled=bool(payload.enabled),
        allowlist_symbols=str(payload.allowlist_symbols).strip()
        if payload.allowlist_symbols is not None and str(payload.allowlist_symbols).strip() != ""
        else None,
    )
    row = set_holdings_exit_config(db, settings, cfg)
    cfg2, source = get_holdings_exit_config_with_source(db, settings)
    return HoldingsExitConfigRead(
        enabled=bool(cfg2.enabled),
        allowlist_symbols=cfg2.allowlist_symbols,
        source=source,
        updated_at=row.updated_at if row is not None else None,
    )


__all__ = ["router"]

