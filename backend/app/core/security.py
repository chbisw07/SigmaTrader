from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import Settings, get_settings

# ruff: noqa: B008  # FastAPI dependency injection pattern

security = HTTPBasic()


def require_admin(
    settings: Settings = Depends(get_settings),
    credentials: HTTPBasicCredentials = Depends(security),
) -> Optional[str]:
    """Simple optional HTTP Basic auth for admin APIs.

    If ST_ADMIN_USERNAME is not set, this is effectively a no-op so that
    local single-user development remains frictionless. When
    ST_ADMIN_USERNAME and ST_ADMIN_PASSWORD are defined, requests must
    provide matching HTTP Basic credentials.
    """

    if not settings.admin_username:
        return None

    correct_username = secrets.compare_digest(
        credentials.username, settings.admin_username
    )
    correct_password = secrets.compare_digest(
        credentials.password or "", settings.admin_password or ""
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator credentials.",
            headers={"WWW-Authenticate": 'Basic realm="SigmaTrader Admin"'},
        )

    return credentials.username


__all__ = ["require_admin"]
