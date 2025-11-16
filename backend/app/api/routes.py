from fastapi import APIRouter, Depends

from ..core.config import Settings, get_settings
from . import (
    analytics,
    orders,
    positions,
    risk_settings,
    strategies,
    system_events,
    webhook,
    zerodha,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern


router = APIRouter()


@router.get("/", tags=["system"])
def read_root(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """Root endpoint to verify that the API is running."""

    return {
        "message": f"{settings.app_name} is running",
        "environment": settings.environment,
    }


@router.get("/health", tags=["system"])
def health_check(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """Basic health endpoint used by the frontend and monitoring."""

    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


router.include_router(
    strategies.router,
    prefix="/api/strategies",
    tags=["strategies"],
)

router.include_router(
    risk_settings.router,
    prefix="/api/risk-settings",
    tags=["risk-settings"],
)

router.include_router(
    orders.router,
    prefix="/api/orders",
    tags=["orders"],
)

router.include_router(
    positions.router,
    prefix="/api/positions",
    tags=["positions"],
)

router.include_router(
    analytics.router,
    prefix="/api/analytics",
    tags=["analytics"],
)

router.include_router(
    system_events.router,
    prefix="/api/system-events",
    tags=["system-events"],
)

router.include_router(
    zerodha.router,
    prefix="/api/zerodha",
    tags=["zerodha"],
)

router.include_router(
    webhook.router,
    prefix="/webhook",
    tags=["webhook"],
)


__all__ = ["router"]
