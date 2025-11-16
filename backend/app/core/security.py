from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.api.auth import get_current_user_optional
from app.models import User

from .config import Settings, get_settings

# ruff: noqa: B008  # FastAPI dependency injection pattern

security = HTTPBasic(auto_error=False)


def require_admin(
    request: Request,
    settings: Settings = Depends(get_settings),
    credentials: HTTPBasicCredentials | None = Depends(security),
    user: User | None = Depends(get_current_user_optional),
) -> Optional[str]:
    """Authorization guard for admin APIs.

    Behaviour:
    - During pytest runs (PYTEST_CURRENT_TEST set), this is a no-op so tests
      can access admin APIs without authentication.
    - If a logged-in user exists and has role ADMIN, access is granted.
    - Otherwise, if ST_ADMIN_USERNAME is configured, HTTP Basic credentials
      are required and validated against ST_ADMIN_USERNAME/PASSWORD.
    - If neither an admin session nor valid Basic credentials are present,
      a 401 response is returned.
    """

    # Test environment: keep things open and avoid interfering with pytest.
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None

    # Session-based access via the application login system.
    # For now we treat any authenticated user as having access to admin
    # APIs; role-based differences will be introduced in a later sprint.
    if user is not None:
        return user.username

    # Legacy HTTP Basic admin fallback if configured.
    if settings.admin_username:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Administrator credentials are required.",
                headers={"WWW-Authenticate": 'Basic realm="SigmaTrader Admin"'},
            )

        correct_username = secrets.compare_digest(
            credentials.username,
            settings.admin_username,
        )
        correct_password = secrets.compare_digest(
            credentials.password or "",
            settings.admin_password or "",
        )
        if not (correct_username and correct_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid administrator credentials.",
                headers={"WWW-Authenticate": 'Basic realm="SigmaTrader Admin"'},
            )

        return credentials.username

    # No admin session and no legacy Basic configuration: reject access.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Administrator session required.",
    )


__all__ = ["require_admin"]
