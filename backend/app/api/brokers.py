from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config_files import load_app_config
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import User
from app.services.broker_secrets import (
    delete_broker_secret,
    list_broker_secrets,
    set_broker_secret,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class BrokerInfo(BaseModel):
    name: str
    label: str


class BrokerSecretRead(BaseModel):
    key: str
    value: str


class BrokerSecretUpdate(BaseModel):
    value: str


def _get_supported_brokers() -> List[BrokerInfo]:
    cfg = load_app_config()
    labels: Dict[str, str] = {
        "zerodha": "Zerodha (Kite)",
    }
    return [
        BrokerInfo(name=name, label=labels.get(name, name.title()))
        for name in cfg.brokers
    ]


@router.get("/", response_model=List[BrokerInfo])
def list_brokers() -> List[BrokerInfo]:
    """Return list of supported brokers/platforms."""

    return _get_supported_brokers()


def _ensure_broker_exists(broker_name: str) -> None:
    names = {b.name for b in _get_supported_brokers()}
    if broker_name not in names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown broker: {broker_name}",
        )


@router.get("/{broker_name}/secrets", response_model=List[BrokerSecretRead])
def get_broker_secrets(
    broker_name: str = Path(..., min_length=1),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> List[BrokerSecretRead]:
    """Return decrypted secrets for a broker (admin-only)."""

    _ensure_broker_exists(broker_name)
    secrets = list_broker_secrets(db, settings, broker_name, user_id=user.id)
    return [BrokerSecretRead(**s) for s in secrets]


@router.put(
    "/{broker_name}/secrets/{key}",
    response_model=BrokerSecretRead,
)
def update_broker_secret(
    broker_name: str = Path(..., min_length=1),
    key: str = Path(..., min_length=1),
    payload: BrokerSecretUpdate = ...,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> BrokerSecretRead:
    """Create or update a secret for a broker."""

    _ensure_broker_exists(broker_name)
    secret = set_broker_secret(
        db,
        settings,
        broker_name=broker_name,
        key=key,
        value=payload.value,
        user_id=user.id,
    )
    # Return decrypted value to the caller.
    return BrokerSecretRead(
        key=secret.key,
        value=payload.value,
    )


@router.delete(
    "/{broker_name}/secrets/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_broker_secret_endpoint(
    broker_name: str = Path(..., min_length=1),
    key: str = Path(..., min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a secret for a broker if it exists."""

    _ensure_broker_exists(broker_name)
    deleted = delete_broker_secret(
        db,
        broker_name=broker_name,
        key=key,
        user_id=user.id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Secret not found.",
        )


__all__ = ["router"]
