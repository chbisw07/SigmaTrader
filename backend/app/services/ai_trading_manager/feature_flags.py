from __future__ import annotations

from fastapi import HTTPException, status

from app.core.config import Settings
from sqlalchemy.orm import Session

from app.services.ai_trading_manager.ai_settings_config import (
    get_ai_settings_with_source,
    is_execution_hard_disabled,
)
from app.schemas.ai_settings import KiteMcpStatus


def require_ai_assistant_enabled(db: Session, settings: Settings) -> None:
    cfg, _src = get_ai_settings_with_source(db, settings)
    if not cfg.feature_flags.ai_assistant_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI assistant is not enabled.",
        )


def require_monitoring_enabled(db: Session, settings: Settings) -> None:
    cfg, _src = get_ai_settings_with_source(db, settings)
    if not cfg.feature_flags.monitoring_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitoring is not enabled.",
        )


def require_execution_enabled(db: Session, settings: Settings) -> None:
    cfg, _src = get_ai_settings_with_source(db, settings)
    if not cfg.feature_flags.ai_execution_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI execution is not enabled.",
        )
    if is_execution_hard_disabled(cfg):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI execution is not enabled.",
        )
    if not cfg.feature_flags.kite_mcp_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI execution is not enabled.",
        )
    if cfg.kite_mcp.last_status != KiteMcpStatus.connected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI execution is not enabled.",
        )
