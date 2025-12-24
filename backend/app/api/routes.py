from fastapi import APIRouter, Depends

from ..core.config import Settings, get_settings
from ..core.security import require_admin
from . import (
    alerts_v3,
    analytics,
    angelone,
    auth,
    brokers,
    groups,
    instruments,
    market_data,
    orders,
    paper,
    positions,
    risk_settings,
    screener_v3,
    signal_strategies,
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
    dependencies=[Depends(require_admin)],
    tags=["strategies"],
)

router.include_router(
    risk_settings.router,
    prefix="/api/risk-settings",
    dependencies=[Depends(require_admin)],
    tags=["risk-settings"],
)

router.include_router(
    orders.router,
    prefix="/api/orders",
    dependencies=[Depends(require_admin)],
    tags=["orders"],
)

router.include_router(
    positions.router,
    prefix="/api/positions",
    dependencies=[Depends(require_admin)],
    tags=["positions"],
)

router.include_router(
    analytics.router,
    prefix="/api/analytics",
    dependencies=[Depends(require_admin)],
    tags=["analytics"],
)

router.include_router(
    market_data.router,
    prefix="/api/market",
    dependencies=[Depends(require_admin)],
    tags=["market"],
)

router.include_router(
    angelone.router,
    prefix="/api/angelone",
    dependencies=[Depends(require_admin)],
    tags=["angelone"],
)

router.include_router(
    instruments.router,
    prefix="/api/instruments",
    dependencies=[Depends(require_admin)],
    tags=["instruments"],
)

if get_settings().enable_legacy_alerts:
    from . import indicator_alerts

    router.include_router(
        indicator_alerts.router,
        prefix="/api/indicator-alerts",
        dependencies=[Depends(require_admin)],
        tags=["indicator-alerts"],
    )

router.include_router(
    alerts_v3.router,
    prefix="/api/alerts-v3",
    dependencies=[Depends(require_admin)],
    tags=["alerts-v3"],
)

router.include_router(
    screener_v3.router,
    prefix="/api/screener-v3",
    dependencies=[Depends(require_admin)],
    tags=["screener-v3"],
)

router.include_router(
    signal_strategies.router,
    prefix="/api/signal-strategies",
    dependencies=[Depends(require_admin)],
    tags=["signal-strategies"],
)

router.include_router(
    groups.router,
    prefix="/api/groups",
    dependencies=[Depends(require_admin)],
    tags=["groups"],
)

router.include_router(
    system_events.router,
    prefix="/api/system-events",
    dependencies=[Depends(require_admin)],
    tags=["system-events"],
)

router.include_router(
    auth.router,
    prefix="/api/auth",
    tags=["auth"],
)

router.include_router(
    brokers.router,
    prefix="/api/brokers",
    dependencies=[Depends(require_admin)],
    tags=["brokers"],
)

router.include_router(
    zerodha.router,
    prefix="/api/zerodha",
    tags=["zerodha"],
)

router.include_router(
    paper.router,
    prefix="/api/paper",
    tags=["paper"],
)

router.include_router(
    webhook.router,
    prefix="/webhook",
    tags=["webhook"],
)


__all__ = ["router"]
