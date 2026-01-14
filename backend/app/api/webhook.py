from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.market_hours import is_market_open_now
from app.db.session import get_db
from app.models import Alert, Strategy, User
from app.pydantic_compat import PYDANTIC_V2
from app.schemas.webhook import TradingViewWebhookPayload
from app.services import create_order_from_alert
from app.services.system_events import record_system_event
from app.services.tradingview_webhook_config import (
    get_tradingview_webhook_config_with_source,
)
from app.services.tradingview_zerodha_adapter import (
    NormalizedAlert,
    normalize_tradingview_payload_for_zerodha,
)
from app.services.webhook_secrets import get_tradingview_webhook_secret

# ruff: noqa: B008  # FastAPI dependency injection pattern

logger = logging.getLogger(__name__)

router = APIRouter()


_THOUSANDS_SEP_RE = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _strip_thousands_separators(raw: str) -> str:
    # TradingView templates sometimes expand numbers with commas (e.g. 2,673.10),
    # which makes the JSON invalid if the value is not quoted. We only strip
    # commas that look like thousands separators between digits.
    return _THOUSANDS_SEP_RE.sub("", raw)


def _strip_trailing_commas(raw: str) -> str:
    """Remove trailing commas before closing braces/brackets.

    TradingView alert templates often end up with a trailing comma, which is
    invalid JSON but easy to recover from.
    """

    previous = None
    while previous != raw:
        previous = raw
        raw = _TRAILING_COMMA_RE.sub(r"\1", raw)
    return raw


def _redact_webhook_body_for_logging(raw: str) -> str:
    """Best-effort redaction for storing webhook debug snippets."""

    redacted = raw
    for key in ("secret", "st_user_id"):
        redacted = re.sub(
            rf'("{key}"\s*:\s*")[^"]*(")',
            r"\1***\2",
            redacted,
            flags=re.IGNORECASE,
        )
    return redacted


@router.get(
    "",
    summary="Webhook root (compat)",
)
def webhook_root() -> Dict[str, str]:
    return {
        "message": "SigmaTrader webhook endpoint",
        "tradingview": "POST /webhook/tradingview",
        "compat": "POST /webhook",
    }


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def tradingview_webhook_compat(
    payload: TradingViewWebhookPayload | Dict[str, Any] | str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Backward-compatible alias for TradingView webhook.

    Some TradingView alert setups point to `/webhook` instead of
    `/webhook/tradingview`. Accept both.
    """

    return tradingview_webhook(
        payload=payload,
        request=request,
        db=db,
        settings=settings,
    )


@router.post(
    "/tradingview",
    status_code=status.HTTP_201_CREATED,
    summary="Receive TradingView webhook alerts",
)
def tradingview_webhook(
    payload: TradingViewWebhookPayload | Dict[str, Any] | str,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Ingest a TradingView webhook alert and persist it as an Alert row.

    The secret must match the configured TradingView webhook secret
    when one is set; otherwise a 401 response is returned.
    """

    correlation_id = getattr(request.state, "correlation_id", None)

    expected_secret = get_tradingview_webhook_secret(db, settings)
    expected_secret = (expected_secret or "").strip() or None

    # TradingView sends webhooks as text/plain, even when the body is JSON.
    # Accept both application/json and text/plain payloads.
    if isinstance(payload, str):
        raw_body = payload.strip()
        if not raw_body:
            payload = {}
        else:
            candidates = [
                raw_body,
                _strip_trailing_commas(raw_body),
                _strip_thousands_separators(raw_body),
                _strip_trailing_commas(_strip_thousands_separators(raw_body)),
                _strip_thousands_separators(_strip_trailing_commas(raw_body)),
            ]
            parsed_json: dict[str, Any] | None = None
            for candidate in dict.fromkeys(candidates):
                try:
                    parsed_json = json.loads(candidate)
                    break
                except json.JSONDecodeError:
                    continue

            if parsed_json is not None:
                payload = parsed_json
            else:
                # Some setups send key=value pairs (rare); support minimal parsing.
                parsed_kv = {k: v[-1] for k, v in parse_qs(raw_body).items() if v}
                if parsed_kv:
                    payload = parsed_kv
                else:
                    preview = _redact_webhook_body_for_logging(raw_body[:500])
                    record_system_event(
                        db,
                        level="WARNING",
                        category="webhook",
                        message="TradingView webhook rejected: invalid JSON body",
                        correlation_id=correlation_id,
                        details={
                            "content_type": request.headers.get("content-type"),
                            "body_len": len(raw_body),
                            "body_preview": preview,
                        },
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid TradingView payload. Body must be valid JSON.",
                    )

    provided_secret = request.headers.get("X-SIGMATRADER-SECRET")
    if not provided_secret:
        if isinstance(payload, TradingViewWebhookPayload):
            provided_secret = payload.secret
        else:
            provided_secret = str(payload.get("secret") or "")
    provided_secret = (provided_secret or "").strip()

    if expected_secret and provided_secret != expected_secret:
        record_system_event(
            db,
            level="WARNING",
            category="webhook",
            message="TradingView webhook rejected: invalid secret",
            correlation_id=correlation_id,
            details={
                "platform": (
                    payload.platform
                    if isinstance(payload, TradingViewWebhookPayload)
                    else payload.get("platform")
                ),
                "strategy": (
                    payload.strategy_name
                    if isinstance(payload, TradingViewWebhookPayload)
                    else payload.get("strategy_name")
                ),
                "st_user_id": (
                    payload.st_user_id
                    if isinstance(payload, TradingViewWebhookPayload)
                    else payload.get("st_user_id")
                ),
                "auth": {
                    "header_present": bool(request.headers.get("X-SIGMATRADER-SECRET")),
                    "body_present": (
                        bool(getattr(payload, "secret", None))
                        if isinstance(payload, TradingViewWebhookPayload)
                        else bool(payload.get("secret"))
                    ),
                },
            },
        )
        logger.warning(
            "Received webhook with invalid secret",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": (
                        payload.strategy_name
                        if isinstance(payload, TradingViewWebhookPayload)
                        else payload.get("strategy_name")
                    ),
                    "platform": (
                        payload.platform
                        if isinstance(payload, TradingViewWebhookPayload)
                        else payload.get("platform")
                    ),
                }
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret.",
        )

    # Lightweight health check / tunnel validation.
    if not isinstance(payload, TradingViewWebhookPayload):
        if payload.get("test") == "tradingview":
            return {"status": "ok"}

        # Allow header-only auth by injecting a placeholder secret into the
        # payload before parsing, so callers can omit "secret" from the JSON.
        payload_with_secret = dict(payload)
        payload_with_secret.setdefault("secret", provided_secret or "")
        try:
            if PYDANTIC_V2 and hasattr(TradingViewWebhookPayload, "model_validate"):
                payload = TradingViewWebhookPayload.model_validate(payload_with_secret)
            else:
                payload = TradingViewWebhookPayload.parse_obj(payload_with_secret)
        except Exception as exc:
            details: dict[str, Any] = {
                "content_type": request.headers.get("content-type"),
                "payload_keys": sorted(list(payload_with_secret.keys())),
            }
            if isinstance(exc, ValidationError):
                details["validation_errors"] = [
                    {
                        "loc": list(err.get("loc") or []),
                        "msg": err.get("msg"),
                        "type": err.get("type"),
                    }
                    for err in exc.errors()
                ]
            record_system_event(
                db,
                level="WARNING",
                category="webhook",
                message="TradingView webhook rejected: invalid payload schema",
                correlation_id=correlation_id,
                details=details,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Invalid TradingView payload. Missing required fields "
                    "or invalid schema."
                ),
            ) from exc

    # For now we only process alerts targeting Zerodha / generic TradingView.
    platform_normalized = (payload.platform or "").lower()
    if platform_normalized and platform_normalized not in {"zerodha", "tradingview"}:
        logger.info(
            "Ignoring webhook for unsupported platform",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": payload.strategy_name,
                    "platform": payload.platform,
                }
            },
        )
        return {"status": "ignored", "platform": payload.platform}

    # Route alert to a specific SigmaTrader user. For multi-user safety we
    # require TradingView payloads to carry an explicit st_user_id that
    # matches an existing username; otherwise we ignore the alert.
    st_user = (payload.st_user_id or "").strip()
    if not st_user:
        logger.info(
            "Ignoring webhook without st_user_id",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": payload.strategy_name,
                    "platform": payload.platform,
                }
            },
        )
        record_system_event(
            db,
            level="INFO",
            category="alert",
            message="Alert ignored: missing st_user_id",
            correlation_id=correlation_id,
            details={
                "strategy": payload.strategy_name,
                "platform": payload.platform,
            },
        )
        return {"status": "ignored", "reason": "missing_st_user_id"}

    user: User | None = db.query(User).filter(User.username == st_user).one_or_none()
    if user is None:
        logger.warning(
            "Ignoring webhook for unknown st_user_id",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": payload.strategy_name,
                    "platform": payload.platform,
                    "st_user_id": st_user,
                }
            },
        )
        record_system_event(
            db,
            level="WARNING",
            category="alert",
            message="Alert ignored: unknown st_user_id",
            correlation_id=correlation_id,
            details={
                "strategy": payload.strategy_name,
                "platform": payload.platform,
                "st_user_id": st_user,
            },
        )
        return {
            "status": "ignored",
            "reason": "unknown_st_user_id",
            "st_user_id": st_user,
        }

    # NOTE: Backward compatibility
    # If webhook routing config is not explicitly set, fall back to the
    # historical strategy-based AUTO/MANUAL behavior (tests and existing setups).
    cfg, cfg_source = get_tradingview_webhook_config_with_source(
        db,
        settings,
        user_id=user.id,
    )
    strategy: Strategy | None = (
        db.query(Strategy).filter(Strategy.name == payload.strategy_name).one_or_none()
    )
    use_strategy_mode = (
        cfg_source == "default" and strategy is not None and strategy.enabled
    )

    mode = (
        (
            getattr(strategy, "execution_mode", "MANUAL")
            if use_strategy_mode
            else cfg.mode
        )
        .strip()
        .upper()
    )
    if mode not in {"MANUAL", "AUTO"}:
        mode = "MANUAL"
    auto_execute = mode == "AUTO"

    exec_target = (
        (
            getattr(strategy, "execution_target", "LIVE")
            if use_strategy_mode
            else cfg.execution_target
        )
        .strip()
        .upper()
    )
    if exec_target not in {"LIVE", "PAPER"}:
        exec_target = "LIVE"

    # Broker selection is config-driven (strategies are broker-agnostic).
    broker_name = (cfg.broker_name or "zerodha").strip().lower()

    try:
        from app.api.orders import _ensure_supported_broker

        broker_name = _ensure_supported_broker(broker_name)
    except Exception:
        broker_name = "zerodha"

    normalized: NormalizedAlert = normalize_tradingview_payload_for_zerodha(
        payload=payload,
        user=user,
    )

    alert = Alert(
        user_id=normalized.user_id,
        # Keep legacy strategy linkage only when operating in legacy
        # strategy-driven mode. When the new webhook config is set, avoid linking
        # so TradingView orders are governed by GLOBAL risk settings only.
        strategy_id=(
            strategy.id if use_strategy_mode and strategy is not None else None
        ),
        symbol=normalized.symbol_display,
        exchange=normalized.broker_exchange,
        interval=normalized.timeframe,
        action=normalized.side,
        qty=normalized.qty,
        price=normalized.price,
        platform=payload.platform,
        source="TRADINGVIEW",
        raw_payload=normalized.raw_payload,
        bar_time=normalized.bar_time,
        reason=normalized.reason,
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    order = create_order_from_alert(
        db=db,
        alert=alert,
        mode=mode,
        product=normalized.product,
        order_type=normalized.order_type,
        broker_name=broker_name,
        execution_target=exec_target,
        user_id=alert.user_id,
    )

    # For AUTO webhooks we immediately execute the order via the same execution
    # path used by the manual queue endpoint. When configured for PAPER
    # execution we respect market hours and (when closed) fall back to the
    # manual waiting queue so the user can execute later.
    if auto_execute:
        try:
            # New-config AUTO(PAPER) prefers to fall back to Waiting Queue if
            # market is closed; legacy strategy AUTO uses the existing paper
            # execution behavior (which fails fast).
            if (
                not use_strategy_mode
                and exec_target == "PAPER"
                and not is_market_open_now()
            ):
                order.mode = "MANUAL"
                order.status = "WAITING"
                order.error_message = (
                    "AUTO(PAPER) dispatch skipped: market is closed. "
                    "Moved to Waiting Queue."
                )
                db.add(order)
                db.commit()
                db.refresh(order)
            else:
                from app.api.orders import execute_order as execute_order_api

                execute_order_api(
                    order_id=order.id,
                    request=request,
                    db=db,
                    settings=settings,
                )
        except HTTPException as exc:
            # Legacy strategy-driven AUTO behavior: surface the broker error and
            # mark the order as FAILED (so history shows what happened).
            if use_strategy_mode:
                db.refresh(order)
                detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                if exc.status_code == status.HTTP_400_BAD_REQUEST and isinstance(
                    detail,
                    str,
                ):
                    if "is not connected" in detail.lower():
                        order.status = "FAILED"
                        if broker_name.lower() == "zerodha":
                            order.error_message = (
                                "Zerodha is not connected for AUTO mode."
                            )
                        else:
                            order.error_message = (
                                f"{broker_name} is not connected for AUTO mode."
                            )
                        db.add(order)
                        db.commit()
                        db.refresh(order)
                logger.exception(
                    "AUTO execution failed for alert id=%s order id=%s strategy=%s",
                    alert.id,
                    order.id,
                    payload.strategy_name,
                )
                raise

            # New-config AUTO behavior: optionally fall back to Waiting Queue so
            # the user can retry after fixing broker connectivity or market-hours.
            db.refresh(order)
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            transient = any(
                s in detail.lower()
                for s in (
                    "is not connected",
                    "market is closed",
                    "paper order rejected",
                )
            )
            if (
                cfg.fallback_to_waiting_on_error
                and order.status == "WAITING"
                and transient
            ):
                order.mode = "MANUAL"
                order.error_message = (
                    f"AUTO dispatch failed: {detail}. Moved to Waiting Queue."
                )
                db.add(order)
                db.commit()
                db.refresh(order)
                record_system_event(
                    db,
                    level="WARNING",
                    category="order",
                    message="AUTO order moved to waiting queue",
                    correlation_id=correlation_id,
                    details={
                        "order_id": order.id,
                        "symbol": order.symbol,
                        "reason": detail,
                        "broker_name": broker_name,
                    },
                )
            logger.exception(
                "AUTO execution failed for alert id=%s order id=%s strategy=%s",
                alert.id,
                order.id,
                payload.strategy_name,
            )
            raise

    logger.info(
        "Stored alert and created order",
        extra={
            "extra": {
                "correlation_id": correlation_id,
                "alert_id": alert.id,
                "order_id": order.id,
                "symbol": alert.symbol,
                "action": alert.action,
                "strategy": payload.strategy_name,
                "mode": mode,
            }
        },
    )

    # Persist a structured system event for observability.
    record_system_event(
        db,
        level="INFO",
        category="alert",
        message="Alert ingested and order created",
        correlation_id=correlation_id,
        details={
            "alert_id": alert.id,
            "order_id": order.id,
            "symbol": alert.symbol,
            "action": alert.action,
            "strategy": payload.strategy_name,
            "mode": mode,
        },
    )

    return {
        "id": alert.id,
        "alert_id": alert.id,
        "order_id": order.id,
        "status": "accepted",
    }


__all__ = ["router"]
