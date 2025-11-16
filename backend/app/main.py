from fastapi import FastAPI

from .api.routes import router as api_router
from .core.config import get_settings
from .core.logging import RequestContextMiddleware, configure_logging
from .db.session import SessionLocal
from .services.users import ensure_default_admin

settings = get_settings()

configure_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
)


def _bootstrap_admin_user() -> None:
    """Ensure the default admin user exists at startup."""

    with SessionLocal() as db:
        ensure_default_admin(db)


_bootstrap_admin_user()

app.add_middleware(RequestContextMiddleware)
app.include_router(api_router)


__all__ = ["app"]
