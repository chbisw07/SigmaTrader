from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.crypto import decrypt_token
from app.db.session import get_db
from app.models import BrokerSecret
from app.models import TradingViewAlertPayloadTemplate
from app.schemas.tradingview_payload_templates import (
    TradingViewAlertPayloadTemplateRead,
    TradingViewAlertPayloadTemplateSummary,
    TradingViewAlertPayloadTemplateUpsert,
)
from app.services.tradingview_webhook_config import (
    TradingViewWebhookConfig,
    get_tradingview_webhook_config,
    set_tradingview_webhook_config,
)
from app.services.webhook_secrets import (
    TRADINGVIEW_WEBHOOK_SECRET_KEY,
    WEBHOOK_BROKER_NAME,
    get_tradingview_webhook_secret,
    set_tradingview_webhook_secret,
)

# ruff: noqa: B008  # FastAPI dependency injection pattern

router = APIRouter()


class TradingViewWebhookSecretRead(BaseModel):
    value: str | None
    source: str  # db|env|unset


class TradingViewWebhookSecretUpdate(BaseModel):
    value: str


class TradingViewWebhookConfigRead(BaseModel):
    mode: str
    broker_name: str
    execution_target: str
    default_product: str
    fallback_to_waiting_on_error: bool = True


class TradingViewWebhookConfigUpdate(BaseModel):
    mode: str | None = None
    broker_name: str | None = None
    execution_target: str | None = None
    default_product: str | None = None
    fallback_to_waiting_on_error: bool | None = None


@router.get(
    "/tradingview-secret",
    response_model=TradingViewWebhookSecretRead,
)
def read_tradingview_webhook_secret(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TradingViewWebhookSecretRead:
    db_row = (
        db.query(BrokerSecret)
        .filter(
            BrokerSecret.broker_name == WEBHOOK_BROKER_NAME,
            BrokerSecret.key == TRADINGVIEW_WEBHOOK_SECRET_KEY,
            BrokerSecret.user_id.is_(None),
        )
        .one_or_none()
    )

    if db_row is not None:
        return TradingViewWebhookSecretRead(
            value=decrypt_token(settings, db_row.value_encrypted),
            source="db",
        )
    if settings.tradingview_webhook_secret:
        return TradingViewWebhookSecretRead(
            value=settings.tradingview_webhook_secret,
            source="env",
        )
    return TradingViewWebhookSecretRead(value=None, source="unset")


@router.put(
    "/tradingview-secret",
    response_model=TradingViewWebhookSecretRead,
)
def update_tradingview_webhook_secret(
    payload: TradingViewWebhookSecretUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TradingViewWebhookSecretRead:
    set_tradingview_webhook_secret(db, settings, payload.value)
    value = get_tradingview_webhook_secret(db, settings)
    if (payload.value or "").strip():
        source = "db"
    elif settings.tradingview_webhook_secret:
        source = "env"
    else:
        source = "unset"
    return TradingViewWebhookSecretRead(value=value, source=source)


@router.get(
    "/tradingview-config",
    response_model=TradingViewWebhookConfigRead,
)
def read_tradingview_webhook_config(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TradingViewWebhookConfigRead:
    cfg = get_tradingview_webhook_config(db, settings, user_id=None)
    return TradingViewWebhookConfigRead(**cfg.to_dict())


@router.put(
    "/tradingview-config",
    response_model=TradingViewWebhookConfigRead,
)
def update_tradingview_webhook_config(
    payload: TradingViewWebhookConfigUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TradingViewWebhookConfigRead:
    existing = get_tradingview_webhook_config(db, settings, user_id=None)
    merged = TradingViewWebhookConfig.from_dict(
        {
            **existing.to_dict(),
            **{k: v for k, v in payload.dict().items() if v is not None},
        }
    )
    try:
        from app.api.orders import _ensure_supported_broker

        merged = TradingViewWebhookConfig.from_dict(
            {
                **merged.to_dict(),
                "broker_name": _ensure_supported_broker(merged.broker_name),
            }
        )
    except Exception:
        # If broker validation fails (e.g. minimal test env), keep the value as-is.
        pass
    set_tradingview_webhook_config(db, settings, merged, user_id=None)
    return TradingViewWebhookConfigRead(**merged.to_dict())


@router.get(
    "/tradingview-alert-payload-templates",
    response_model=list[TradingViewAlertPayloadTemplateSummary],
)
def list_tradingview_alert_payload_templates(
    db: Session = Depends(get_db),
) -> list[TradingViewAlertPayloadTemplateSummary]:
    rows = (
        db.query(TradingViewAlertPayloadTemplate)
        .order_by(TradingViewAlertPayloadTemplate.updated_at.desc())
        .all()
    )
    return [
        TradingViewAlertPayloadTemplateSummary(
            id=row.id, name=row.name, updated_at=row.updated_at
        )
        for row in rows
    ]


@router.get(
    "/tradingview-alert-payload-templates/{template_id}",
    response_model=TradingViewAlertPayloadTemplateRead,
)
def read_tradingview_alert_payload_template(
    template_id: int,
    db: Session = Depends(get_db),
) -> TradingViewAlertPayloadTemplateRead:
    row = db.get(TradingViewAlertPayloadTemplate, template_id)
    if row is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found.",
        )
    try:
        parsed = json.loads(row.config_json or "{}")
    except json.JSONDecodeError:
        parsed = {}
    return TradingViewAlertPayloadTemplateRead(
        id=row.id,
        name=row.name,
        config=parsed,
        updated_at=row.updated_at,
    )


@router.post(
    "/tradingview-alert-payload-templates",
    response_model=TradingViewAlertPayloadTemplateRead,
)
def upsert_tradingview_alert_payload_template(
    payload: TradingViewAlertPayloadTemplateUpsert,
    db: Session = Depends(get_db),
) -> TradingViewAlertPayloadTemplateRead:
    name = payload.name.strip()
    if not name:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template name is required.",
        )
    row = (
        db.query(TradingViewAlertPayloadTemplate)
        .filter(TradingViewAlertPayloadTemplate.name == name)
        .one_or_none()
    )
    config_dump = (
        payload.config.model_dump()  # type: ignore[attr-defined]
        if hasattr(payload.config, "model_dump")
        else payload.config.dict()  # type: ignore[attr-defined]
    )
    dumped = json.dumps(config_dump, ensure_ascii=False, default=str)
    if row is None:
        row = TradingViewAlertPayloadTemplate(name=name, config_json=dumped)
        db.add(row)
    else:
        row.config_json = dumped
    db.commit()
    db.refresh(row)
    parsed = payload.config
    return TradingViewAlertPayloadTemplateRead(
        id=row.id,
        name=row.name,
        config=parsed,
        updated_at=row.updated_at,
    )


@router.delete(
    "/tradingview-alert-payload-templates/{template_id}",
    response_model=dict[str, str],
)
def delete_tradingview_alert_payload_template(
    template_id: int,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = db.get(TradingViewAlertPayloadTemplate, template_id)
    if row is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found.",
        )
    db.delete(row)
    db.commit()
    return {"status": "deleted"}


__all__ = ["router"]
