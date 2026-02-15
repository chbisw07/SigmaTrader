from __future__ import annotations

import json
import hashlib
import logging
import re
from typing import Any, Dict
from urllib.parse import parse_qs

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.market_hours import is_market_open_now
from app.db.session import get_db
from app.models import Alert, Order, Strategy, User
from app.pydantic_compat import PYDANTIC_V2
from app.schemas.webhook import TradingViewWebhookPayload
from app.services import create_order_from_alert
from app.services.risk_unified_store import read_unified_risk_global
from app.services.system_events import record_system_event
from app.services.tradingview_webhook_config import (
    get_tradingview_webhook_config_with_source,
)
from app.services.tradingview_zerodha_adapter import (
    NormalizedAlert,
    normalize_tradingview_payload_for_zerodha,
)
from app.services.tradingview_sell_qty import resolve_tradingview_sell_qty
from app.services.webhook_secrets import get_tradingview_webhook_secret

# ruff: noqa: B008  # FastAPI dependency injection pattern

logger = logging.getLogger(__name__)

router = APIRouter()


_THOUSANDS_SEP_RE = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _maybe_autosize_waiting_order_qty(
    *,
    db: Session,
    settings: Settings,
    order: Order,
    user: User | None,
    product_hint: str | None,
    correlation_id: str | None,
) -> None:
    """Best-effort: size queued TradingView orders so Qty isn't displayed as 0.

    Execution still runs the full risk engine + broker margin checks; this is
    only to provide a reasonable default Qty in the Waiting Queue when the
    TradingView alert omitted qty.
    """

    try:
        if order.qty is not None and float(order.qty or 0.0) > 0:
            return
    except Exception:
        pass

    try:
        g = read_unified_risk_global(db)
        if not bool(getattr(g, "enabled", False)):
            return
    except Exception:
        return

    sized_qty: float | None = None

    # First attempt: ask the unified risk engine for its sized qty.
    try:
        from app.services.risk_engine import evaluate_order_risk

        baseline_equity = float(getattr(g, "baseline_equity_inr", 0.0) or 0.0)
        decision = evaluate_order_risk(
            db,
            settings,
            user=user,
            order=order,
            baseline_equity=baseline_equity,
            now_utc=datetime.now(UTC),
            product_hint=product_hint,
        )
        if decision.final_qty is not None and float(decision.final_qty) > 0:
            sized_qty = float(decision.final_qty)
    except Exception:
        sized_qty = None

    # Fallback: if risk engine can't size (e.g., missing symbol category),
    # size purely from capital_per_trade and price.
    if sized_qty is None:
        try:
            from math import floor

            from app.services.risk_engine import _price_for_sizing, pick_risk_profile
            from app.services.risk_unified_store import get_source_override

            price = _price_for_sizing(order)
            if price is None or float(price) <= 0:
                return

            prof = pick_risk_profile(db, product_hint=product_hint)
            if prof is None:
                return

            resolved_product = (getattr(prof, "product", None) or "").strip().upper()
            if not resolved_product:
                return

            source_override = get_source_override(
                db,
                source_bucket="TRADINGVIEW",
                product=resolved_product,  # type: ignore[arg-type]
            )
            cap = (
                float(source_override.capital_per_trade)
                if source_override is not None
                and getattr(source_override, "capital_per_trade", None) is not None
                else float(getattr(prof, "capital_per_trade", 0.0) or 0.0)
            )
            if cap <= 0:
                return

            qty = float(floor(cap / float(price)))
            if qty <= 0:
                return

            # Apply safe per-order clamps when configured (does not require symbol category).
            if source_override is not None:
                max_qty = getattr(source_override, "max_quantity_per_order", None)
                if max_qty is not None:
                    try:
                        max_qty_f = float(max_qty)
                        if max_qty_f > 0 and qty > max_qty_f:
                            qty = float(floor(max_qty_f))
                    except Exception:
                        pass

                max_abs = getattr(source_override, "max_order_value_abs", None)
                if max_abs is not None:
                    try:
                        max_abs_f = float(max_abs)
                        if max_abs_f > 0 and qty * float(price) > max_abs_f:
                            qty2 = float(floor(max_abs_f / float(price)))
                            if qty2 > 0:
                                qty = qty2
                    except Exception:
                        pass

                max_pct = getattr(source_override, "max_order_value_pct", None)
                if max_pct is not None:
                    try:
                        baseline = float(getattr(g, "baseline_equity_inr", 0.0) or 0.0)
                        pct_f = float(max_pct)
                        if baseline > 0 and pct_f > 0:
                            cap2 = baseline * pct_f / 100.0
                            if qty * float(price) > cap2:
                                qty2 = float(floor(cap2 / float(price)))
                                if qty2 > 0:
                                    qty = qty2
                    except Exception:
                        pass

            if qty > 0:
                sized_qty = float(qty)
        except Exception:
            sized_qty = None

    if sized_qty is None or sized_qty <= 0:
        return

    try:
        order.qty = float(sized_qty)
        note = "Auto-sized qty from risk profile (preview)."
        if not (order.error_message or "").strip():
            order.error_message = note
        db.add(order)
        db.commit()
        db.refresh(order)
        try:
            record_system_event(
                db,
                level="INFO",
                category="order",
                message="Queued order auto-sized",
                correlation_id=correlation_id,
                details={"order_id": int(order.id), "qty": float(sized_qty)},
            )
        except Exception:
            pass
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


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


def _pick_default_webhook_user(
    db: Session,
    settings: Settings,
) -> User | None:
    # Prefer an explicitly configured admin username when it exists as a user.
    if settings.admin_username:
        user = (
            db.query(User).filter(User.username == settings.admin_username).one_or_none()
        )
        if user is not None:
            return user

    # Common single-user deployments use "admin".
    user = db.query(User).filter(User.username == "admin").one_or_none()
    if user is not None:
        return user

    # Otherwise prefer any ADMIN user, then fall back to the first user.
    user = db.query(User).filter(User.role == "ADMIN").order_by(User.id.asc()).first()
    if user is not None:
        return user

    return db.query(User).order_by(User.id.asc()).first()


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
                # Some send a JSON-encoded string containing JSON.
                raw_body[1:-1]
                if raw_body.startswith('"') and raw_body.endswith('"')
                else raw_body,
                _strip_trailing_commas(raw_body),
                _strip_thousands_separators(raw_body),
                _strip_trailing_commas(_strip_thousands_separators(raw_body)),
                _strip_thousands_separators(_strip_trailing_commas(raw_body)),
            ]
            parsed_json: dict[str, Any] | None = None
            for candidate in dict.fromkeys(candidates):
                try:
                    parsed = json.loads(candidate)
                    # If this decoded into a string, try decoding once more.
                    if isinstance(parsed, str):
                        try:
                            parsed2 = json.loads(parsed)
                            parsed = parsed2
                        except Exception:
                            pass
                    if isinstance(parsed, dict):
                        parsed_json = parsed
                        break
                except json.JSONDecodeError:
                    continue

            if parsed_json is None:
                # Best-effort: extract embedded JSON object from noisy/plain text bodies.
                try:
                    start = raw_body.find("{")
                    end = raw_body.rfind("}")
                    if start >= 0 and end > start:
                        embedded = raw_body[start : end + 1]
                        parsed = json.loads(embedded)
                        if isinstance(parsed, dict):
                            parsed_json = parsed
                except Exception:
                    parsed_json = None

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
            meta = payload.get("meta")
            provided_secret = str(
                payload.get("secret")
                or ((meta or {}).get("secret") if isinstance(meta, dict) else None)
                or ""
            )
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
                    (payload.strategy_id or payload.strategy_name)
                    if isinstance(payload, TradingViewWebhookPayload)
                    else (
                        ((payload.get("signal") or {}).get("strategy_id"))
                        if isinstance(payload.get("signal"), dict)
                        else None
                    )
                    or (
                        ((payload.get("signal") or {}).get("strategy_name"))
                        if isinstance(payload.get("signal"), dict)
                        else None
                    )
                    or payload.get("strategy_name")
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
                        or bool(
                            ((payload.get("meta") or {}).get("secret"))
                            if isinstance(payload.get("meta"), dict)
                            else None
                        )
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
                        (payload.strategy_id or payload.strategy_name)
                        if isinstance(payload, TradingViewWebhookPayload)
                        else (
                            ((payload.get("signal") or {}).get("strategy_id"))
                            if isinstance(payload.get("signal"), dict)
                            else None
                        )
                        or (
                            ((payload.get("signal") or {}).get("strategy_name"))
                            if isinstance(payload.get("signal"), dict)
                            else None
                        )
                        or payload.get("strategy_name")
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

        # Explicit meta.platform guard for the {meta, signal, hints} schema.
        meta_raw = payload.get("meta")
        if isinstance(meta_raw, dict) and meta_raw.get("platform") is not None:
            p = str(meta_raw.get("platform") or "").strip().upper()
            if p and p != "TRADINGVIEW":
                record_system_event(
                    db,
                    level="WARNING",
                    category="webhook",
                    message="TradingView webhook rejected: meta.platform must be TRADINGVIEW",
                    correlation_id=correlation_id,
                    details={"meta_platform": p},
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid TradingView payload: meta.platform must be TRADINGVIEW.",
                )

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
            error_detail: str | None = None
            if isinstance(exc, ValidationError):
                errors = exc.errors()
                details["validation_errors"] = [
                    {
                        "loc": list(err.get("loc") or []),
                        "msg": err.get("msg"),
                        "type": err.get("type"),
                    }
                    for err in errors
                ]

                signal = payload_with_secret.get("signal")
                side = signal.get("side") if isinstance(signal, dict) else None
                order_action = (
                    signal.get("order_action") if isinstance(signal, dict) else None
                )
                if any(
                    list(err.get("loc") or []) == ["trade_details", "order_action"]
                    and "BUY or SELL" in str(err.get("msg") or "")
                    for err in errors
                ):
                    if isinstance(order_action, str) and order_action.strip().startswith(
                        "{{"
                    ):
                        error_detail = (
                            "Invalid TradingView payload: signal.order_action must resolve to BUY or SELL. "
                            "Your alert is sending a placeholder token (e.g. {{strategy.order.action}}) "
                            "that is not being expanded by TradingView. Use a Strategy 'Order fills' alert "
                            "and set Alert Message = {{strategy.order.alert_message}}."
                        )
                    elif isinstance(side, str) and side.strip().startswith("{{"):
                        error_detail = (
                            "Invalid TradingView payload: signal.side must resolve to BUY or SELL. "
                            "Your alert is sending a placeholder token (e.g. {{strategy.order.action}}) "
                            "that is not being expanded by TradingView. Use a Strategy 'Order fills' alert "
                            "and set Alert Message = {{strategy.order.alert_message}}."
                        )
                    else:
                        error_detail = (
                            "Invalid TradingView payload: missing/invalid BUY/SELL action. "
                            "Expected signal.order_action (preferred) or signal.side to be BUY or SELL."
                        )
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
                detail=(error_detail or "Invalid TradingView payload. Missing required fields or invalid schema."),
            ) from exc

    # For now we only process alerts targeting Zerodha / generic TradingView.
    platform_normalized = (payload.platform or "").lower()
    if platform_normalized and platform_normalized not in {"zerodha", "tradingview"}:
        logger.info(
            "Ignoring webhook for unsupported platform",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": (payload.strategy_id or payload.strategy_name),
                    "platform": payload.platform,
                }
            },
        )
        return {"status": "ignored", "platform": payload.platform}

    if payload.payload_format:
        logger.info(
            "Received TradingView webhook payload",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "payload_format": payload.payload_format,
                    "strategy_id": payload.strategy_id,
                    "strategy_name": payload.strategy_name,
                }
            },
        )

    # Route alert to a specific SigmaTrader user. For multi-user safety we
    # require TradingView payloads to carry an explicit st_user_id that
    # matches an existing username; otherwise we ignore the alert.
    st_user = (payload.st_user_id or "").strip()

    user: User | None = None
    if st_user:
        user = db.query(User).filter(User.username == st_user).one_or_none()
    elif payload.payload_format in {
        "TRADINGVIEW_META_SIGNAL_HINTS_V1",
        "TRADINGVIEW_META_SIGNAL_HINTS_V6",
    }:
        user = _pick_default_webhook_user(db, settings)
        if user is not None:
            st_user = user.username
            try:
                payload.st_user_id = st_user
            except Exception:
                pass
            record_system_event(
                db,
                level="INFO",
                category="alert",
                message="Alert routed to default user (missing st_user_id)",
                correlation_id=correlation_id,
                details={
                    "strategy_id": payload.strategy_id,
                    "strategy_name": payload.strategy_name,
                    "platform": payload.platform,
                    "default_user": st_user,
                },
            )
    else:
        logger.info(
            "Ignoring webhook without st_user_id",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": (payload.strategy_id or payload.strategy_name),
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
                "strategy": (payload.strategy_id or payload.strategy_name),
                "platform": payload.platform,
            },
        )
        return {"status": "ignored", "reason": "missing_st_user_id"}

    if user is None:
        logger.warning(
            "Ignoring webhook for unknown st_user_id",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "strategy": (payload.strategy_id or payload.strategy_name),
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
                "strategy": (payload.strategy_id or payload.strategy_name),
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
    strategy_key = (payload.strategy_id or payload.strategy_name or "").strip()
    strategy: Strategy | None = (
        db.query(Strategy).filter(Strategy.name == strategy_key).one_or_none()
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
        default_product=str(getattr(cfg, "default_product", "CNC") or "CNC"),
    )

    sell_resolution = None
    if str(normalized.side).strip().upper() == "SELL":
        try:
            sell_resolution = resolve_tradingview_sell_qty(
                db,
                settings,
                user=user,
                broker_name=broker_name,
                exchange=normalized.broker_exchange,
                symbol=normalized.broker_symbol,
                desired_product=normalized.product,
                payload_qty=float(normalized.qty or 0.0),
            )
        except Exception:
            sell_resolution = None

        if sell_resolution is not None and not bool(getattr(sell_resolution, "reject", False)):
            # Best-effort: override qty/product when we found a sellable quantity.
            try:
                normalized.qty = float(
                    getattr(sell_resolution, "qty", normalized.qty) or 0.0
                )
            except Exception:
                pass
            resolved_product = getattr(sell_resolution, "resolved_product", None)
            if resolved_product:
                normalized.product = str(resolved_product).strip().upper()
            resolved_exchange = getattr(sell_resolution, "resolved_exchange", None)
            if resolved_exchange:
                normalized.broker_exchange = str(resolved_exchange).strip().upper()
            resolved_symbol = getattr(sell_resolution, "resolved_symbol", None)
            if resolved_symbol:
                normalized.broker_symbol = str(resolved_symbol).strip().upper()

    client_order_id: str | None = None
    try:
        raw_order_id = str(getattr(payload, "order_id", "") or "").strip()
        bt = getattr(payload, "bar_time", None)
        symbol_key = f"{normalized.broker_exchange}:{normalized.broker_symbol}"
        if raw_order_id and "{{" not in raw_order_id and bt is not None:
            # Some TradingView setups reuse order_id values across symbols (e.g. "Buy").
            # Include symbol + timestamp to prevent cross-symbol deduping for group alerts,
            # while still deduping retries for the same bar/event.
            client_order_id = f"TV:{symbol_key}:{raw_order_id}:{bt.isoformat()}"
        else:
            # Fallback idempotency key: hash of normalized payload + bar time (if any).
            raw_basis = normalized.raw_payload
            if bt is not None:
                raw_basis = f"{raw_basis}|{bt.isoformat()}"
            digest = hashlib.sha1(raw_basis.encode("utf-8")).hexdigest()[:20]
            client_order_id = f"TVA:{digest}"
        if client_order_id and len(client_order_id) > 128:
            client_order_id = client_order_id[:128]
    except Exception:
        client_order_id = None

    if client_order_id:
        existing = db.query(Order).filter(Order.client_order_id == client_order_id).one_or_none()
        if existing is not None:
            record_system_event(
                db,
                level="INFO",
                category="alert",
                message="TradingView webhook deduped (client_order_id already exists)",
                correlation_id=correlation_id,
                details={
                    "client_order_id": client_order_id,
                    "existing_order_id": existing.id,
                    "existing_alert_id": existing.alert_id,
                },
            )
            return {
                "status": "deduped",
                "order_id": existing.id,
                "alert_id": existing.alert_id,
            }

    alert_reason = normalized.reason
    if sell_resolution is not None and str(normalized.side).strip().upper() == "SELL":
        src = str(getattr(sell_resolution, "source", "") or "").strip().lower()
        qty_note = None
        try:
            qty_note = float(getattr(sell_resolution, "qty", 0.0) or 0.0)
        except Exception:
            qty_note = None
        if src in {"holdings", "positions"} and qty_note is not None and qty_note > 0:
            suffix = f"ST: SELL qty resolved from {src} ({qty_note})."
            alert_reason = f"{(alert_reason or '').strip()} | {suffix}".strip(" |")
        elif bool(getattr(sell_resolution, "reject", False)) and bool(
            getattr(sell_resolution, "checked_live", False)
        ):
            note = str(getattr(sell_resolution, "note", "") or "").strip()
            suffix = (
                "ST: SELL could not be matched to holdings/positions; "
                "created as WAITING for review."
            )
            if note:
                suffix = f"{suffix} ({note})"
            alert_reason = f"{(alert_reason or '').strip()} | {suffix}".strip(" |")

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
        reason=alert_reason,
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    # Safety: when we can confirm this SELL does not map to an existing
    # holding/position, do not auto-dispatch. Create a WAITING order so the
    # user can correct qty/product or intentionally proceed.
    if sell_resolution is not None and str(alert.action).strip().upper() == "SELL":
        if bool(getattr(sell_resolution, "reject", False)) and bool(
            getattr(sell_resolution, "checked_live", False)
        ):
            mode = "MANUAL"
            auto_execute = False

    # Strategy v6 order-fills payloads can encode entry/exit semantics in signal.side
    # (e.g., ENTRY_LONG / EXIT_SHORT). Preserve exit classification for both BUY and SELL.
    tv_is_exit = False
    try:
        sside = str((payload.hints or {}).get("signal_side") or "").strip().upper()
        if sside.startswith(("EXIT_", "CLOSE_")):
            tv_is_exit = True
    except Exception:
        tv_is_exit = False

    risk_is_exit = (
        bool(getattr(sell_resolution, "is_exit", False))
        if sell_resolution is not None and str(alert.action).strip().upper() == "SELL"
        else False
    )

    order = create_order_from_alert(
        db=db,
        alert=alert,
        mode=mode,
        product=normalized.product,
        order_type=normalized.order_type,
        broker_name=broker_name,
        execution_target=exec_target,
        user_id=alert.user_id,
        client_order_id=client_order_id,
        is_exit=bool(tv_is_exit or risk_is_exit),
    )

    # If TradingView omitted qty (or templates didn't expand it), auto-size the
    # queued order so the Waiting Queue isn't filled with qty=0 rows.
    #
    # Exception: Builder-v1 payloads intentionally default to qty=0 so the user
    # can review/override sizing in the UI before dispatching.
    if payload.payload_format != "TRADINGVIEW_META_SIGNAL_HINTS_V1":
        try:
            user_obj = db.get(User, alert.user_id) if alert.user_id is not None else None
            _maybe_autosize_waiting_order_qty(
                db=db,
                settings=settings,
                order=order,
                user=user_obj,
                product_hint=str(normalized.product or "").strip().upper() or None,
                correlation_id=correlation_id,
            )
        except Exception:
            pass

    if sell_resolution is not None and str(order.side).strip().upper() == "SELL":
        if bool(getattr(sell_resolution, "reject", False)) and bool(
            getattr(sell_resolution, "checked_live", False)
        ):
            # Make the issue obvious in the Waiting Queue without preventing edits.
            note = getattr(sell_resolution, "note", None) or "no holdings/positions found"
            msg = (
                "TV SELL needs review: SigmaTrader could not find holdings/positions "
                f"for this symbol ({note}). Edit qty/product or execute intentionally."
            )
            if not (order.error_message or "").strip():
                order.error_message = msg
                db.add(order)
                db.commit()
                db.refresh(order)

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
                    strategy_key,
                )
                raise

            # New-config AUTO behavior: optionally fall back to Waiting Queue so
            # the user can retry after fixing settings or editing the order.
            db.refresh(order)
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            queue_order = None
            moved_to_waiting = False
            if cfg.fallback_to_waiting_on_error:
                # Only move when the broker was definitely not contacted.
                broker_order_id = (
                    getattr(order, "broker_order_id", None)
                    or getattr(order, "zerodha_order_id", None)
                )
                already_sent = str(getattr(order, "status", "") or "").strip().upper() in {
                    "SENT",
                    "OPEN",
                    "EXECUTED",
                }
                if (
                    not getattr(order, "simulated", False)
                    and not already_sent
                    and not broker_order_id
                ):
                    # Keep the original order as history. If the execute path did
                    # not transition it out of WAITING, mark it FAILED so it is
                    # visible as an AUTO failure.
                    if str(getattr(order, "status", "") or "").strip().upper() == "WAITING":
                        order.status = "FAILED"
                        order.error_message = detail
                        db.add(order)
                        db.commit()
                        db.refresh(order)

                    from app.services.orders import requeue_order_to_waiting

                    queue_order = requeue_order_to_waiting(
                        db,
                        source=order,
                        reason="AUTO dispatch failed. Moved to Waiting Queue.",
                    )

                    # Mark source order as requeued for UX clarity.
                    suffix = f"Requeued to Waiting Queue as order #{int(queue_order.id)}."
                    if suffix not in (order.error_message or ""):
                        base = (order.error_message or "").strip()
                        order.error_message = f"{base} {suffix}".strip() if base else suffix
                        db.add(order)
                        db.commit()
                        db.refresh(order)

                    moved_to_waiting = True
                    record_system_event(
                        db,
                        level="WARNING",
                        category="order",
                        message="AUTO order moved to waiting queue",
                        correlation_id=correlation_id,
                        details={
                            "source_order_id": order.id,
                            "queue_order_id": queue_order.id,
                            "symbol": queue_order.symbol,
                            "reason": detail,
                            "broker_name": broker_name,
                        },
                    )
            if moved_to_waiting:
                logger.info(
                    "AUTO dispatch failed; moved to waiting queue",
                    extra={
                        "extra": {
                            "correlation_id": correlation_id,
                            "alert_id": alert.id,
                            "order_id": queue_order.id if queue_order is not None else order.id,
                            "strategy": strategy_key,
                            "reason": detail,
                        }
                    },
                )
                return {
                    "id": alert.id,
                    "alert_id": alert.id,
                    "order_id": queue_order.id if queue_order is not None else order.id,
                    "original_order_id": order.id,
                    "status": "accepted",
                    "dispatch": "WAITING",
                }
            logger.exception(
                "AUTO execution failed for alert id=%s order id=%s strategy=%s",
                alert.id,
                order.id,
                strategy_key,
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
                "strategy": strategy_key,
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
            "strategy": strategy_key,
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
