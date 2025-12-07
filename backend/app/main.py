import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from .api.routes import router as api_router
from .core.config import get_settings
from .core.logging import RequestContextMiddleware, configure_logging
from .db.session import SessionLocal
from .services.market_data import schedule_market_data_sync
from .services.users import ensure_default_admin

settings = get_settings()

configure_logging()


def _bootstrap_admin_user() -> None:
    """Ensure the default admin user exists at startup."""

    with SessionLocal() as db:
        try:
            inspector = inspect(db.get_bind())
            if "users" not in inspector.get_table_names():
                # Database has not been migrated/created yet; skip bootstrapping.
                return
            ensure_default_admin(db)
        except OperationalError:
            # If the users table is not yet available (e.g., during early test
            # setup or before migrations), silently skip bootstrapping.
            return


_bootstrap_admin_user()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """FastAPI lifespan handler for startup/shutdown tasks."""

    # Startup: begin background market data sync when not under pytest.
    if "pytest" not in sys.modules and not os.getenv("PYTEST_CURRENT_TEST"):
        schedule_market_data_sync()
    yield
    # Shutdown: nothing special yet (thread is daemonised).


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    debug=settings.debug,
    lifespan=_lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.include_router(api_router)


__all__ = ["app"]
