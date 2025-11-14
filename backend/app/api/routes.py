from fastapi import APIRouter, Depends

from ..core.config import Settings, get_settings


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


__all__ = ["router"]

