from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.auth import hash_password
from app.models import User


def ensure_default_admin(db: Session) -> None:
    """Ensure a default admin/admin user exists.

    This is a safety net for existing databases that were initialized
    before the Alembic migration seeded the admin user. It is safe to
    call repeatedly because it only inserts the user when missing.
    """

    existing = db.query(User).filter(User.username == "admin").one_or_none()
    if existing is not None:
        return

    admin = User(
        username="admin",
        password_hash=hash_password("admin"),
        role="ADMIN",
        display_name="Administrator",
    )
    db.add(admin)
    db.commit()


__all__ = ["ensure_default_admin"]
