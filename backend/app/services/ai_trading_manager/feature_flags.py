from __future__ import annotations

from fastapi import HTTPException, status

from app.core.config import Settings


def require_ai_assistant_enabled(settings: Settings) -> None:
    if not settings.ai_assistant_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI assistant is not enabled.",
        )


def require_monitoring_enabled(settings: Settings) -> None:
    if not settings.monitoring_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitoring is not enabled.",
        )


def require_execution_enabled(settings: Settings) -> None:
    if not settings.ai_execution_enabled or settings.ai_execution_kill_switch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI execution is not enabled.",
        )

