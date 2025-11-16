from fastapi import FastAPI

from .api.routes import router as api_router
from .core.config import get_settings
from .core.logging import RequestContextMiddleware, configure_logging

settings = get_settings()

configure_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
)

app.add_middleware(RequestContextMiddleware)
app.include_router(api_router)


__all__ = ["app"]
