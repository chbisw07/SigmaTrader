from __future__ import annotations

import os
import sys

from sqlalchemy.orm import Session

from app.core.auth import hash_password
from app.core.config import Settings
from app.models import User


def _truthy_env(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def ensure_default_admin(db: Session, settings: Settings) -> None:
    """Ensure a default admin user exists.

    This is a safety net for existing databases that were initialized
    before the Alembic migration seeded the admin user. It is safe to
    call repeatedly because it only inserts the user when missing.

    The default credentials are sourced from ST_ADMIN_USERNAME/PASSWORD
    when provided (falls back to admin/admin). To intentionally reset the
    password for an existing admin user, set ST_ADMIN_RESET_PASSWORD=1
    for a single restart.
    """

    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        return

    username = settings.admin_username or "admin"
    password = settings.admin_password or "admin"
    force_reset = _truthy_env("ST_ADMIN_RESET_PASSWORD")

    existing = db.query(User).filter(User.username == username).one_or_none()
    if existing is not None:
        if force_reset:
            existing.password_hash = hash_password(password)
            existing.role = "ADMIN"
            db.add(existing)
            db.commit()
        return

    admin = User(
        username=username,
        password_hash=hash_password(password),
        role="ADMIN",
        display_name="Administrator",
    )
    db.add(admin)
    db.commit()


__all__ = ["ensure_default_admin"]
