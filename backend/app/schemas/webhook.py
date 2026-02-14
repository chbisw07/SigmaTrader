from __future__ import annotations

from datetime import UTC, datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.pydantic_compat import field_validator, model_validator


class TradeDetails(BaseModel):
    order_action: str = Field(..., alias="order_action")
    quantity: Optional[float] = None
    price: Optional[float] = None
    product: Optional[str] = None
    trade_type: Optional[str] = None
    comment: Optional[str] = None
    alert_message: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _map_alternate_field_names(cls, values: dict[str, Any]) -> dict[str, Any]:
        def _coerce_float(value: Any) -> Any:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                cleaned = value.strip().replace(",", "")
                if not cleaned:
                    return None
                try:
                    return float(cleaned)
                except ValueError:
                    return value
            return value

        # Support TradingView payloads that use order_contracts / order_price
        if "quantity" not in values and "order_contracts" in values:
            values["quantity"] = values.get("order_contracts")
        if "price" not in values and "order_price" in values:
            values["price"] = values.get("order_price")

        if "quantity" in values:
            values["quantity"] = _coerce_float(values.get("quantity"))
        if "price" in values:
            values["price"] = _coerce_float(values.get("price"))

        # Derive product from trade_type when product is not explicitly set.
        product = values.get("product")
        trade_type = values.get("trade_type")
        if product is None and trade_type is not None:
            t_norm = str(trade_type).strip().lower()
            if t_norm in {"cash_and_carry", "cnc", "delivery"}:
                values["product"] = "CNC"
            elif t_norm in {"intraday", "mis"}:
                values["product"] = "MIS"
        # Map optional descriptive fields that some TV templates use.
        if "comment" not in values and "order_comment" in values:
            values["comment"] = values.get("order_comment")
        if "alert_message" not in values and "order_alert_message" in values:
            values["alert_message"] = values.get("order_alert_message")
        return values

    @field_validator("order_action")
    @classmethod
    def _normalize_order_action(cls, v: str) -> str:
        normalized = v.upper()
        if normalized not in {"BUY", "SELL"}:
            raise ValueError("order_action must be BUY or SELL")
        return normalized


class TradingViewWebhookPayload(BaseModel):
    """Pydantic model for TradingView webhook payloads.

    This is intentionally minimal for Sprint S03 / G01 and will be
    extended as we refine the alert schema.
    """

    secret: str
    platform: str = "TRADINGVIEW"
    payload_format: Optional[str] = None
    strategy_id: Optional[str] = None
    product_hint: Optional[str] = None
    order_id: Optional[str] = None
    strategy_name: str
    st_user_id: Optional[str] = None
    symbol: str
    exchange: Optional[str] = None
    interval: Optional[str] = None
    trade_details: TradeDetails
    bar_time: Optional[datetime] = None
    timestamp: Optional[datetime] = None
    hints: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_platform(cls, values: dict[str, Any]) -> dict[str, Any]:
        def _coerce_datetime(value: Any) -> Any:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, (int, float)):
                ts = float(value)
                if ts > 1_000_000_000_000:
                    ts = ts / 1000.0
                try:
                    return datetime.fromtimestamp(ts, tz=timezone.utc)
                except Exception:
                    return value
            if isinstance(value, str):
                s = value.strip()
                if not s:
                    return None
                if s.isdigit():
                    try:
                        ts = float(s)
                        if ts > 1_000_000_000_000:
                            ts = ts / 1000.0
                        return datetime.fromtimestamp(ts, tz=timezone.utc)
                    except Exception:
                        return value
            return value

        def _pick_order_action(signal: dict[str, Any]) -> str | None:
            # Prefer explicit BUY/SELL from order-fills alerts.
            for k in ("order_action", "orderAction", "action", "side"):
                raw = signal.get(k)
                if raw is None:
                    continue
                s = str(raw).strip().upper()
                if s in {"BUY", "SELL"}:
                    return s
            # Some strategies send semantic sides like ENTRY_LONG/EXIT_SHORT; infer when possible.
            raw = str(signal.get("side") or "").strip().upper()
            if raw.startswith("ENTRY_"):
                if "SHORT" in raw:
                    return "SELL"
                if "LONG" in raw:
                    return "BUY"
            if raw.startswith("EXIT_") or raw.startswith("CLOSE_"):
                if "SHORT" in raw:
                    return "BUY"
                if "LONG" in raw:
                    return "SELL"
            return None

        if not isinstance(values, dict):
            return values

        # v1 canonical payload schema: { meta, signal, hints }
        if "meta" in values and "signal" in values:
            meta = values.get("meta")
            signal = values.get("signal")
            hints = values.get("hints")
            if not isinstance(meta, dict):
                meta = {}
            if not isinstance(signal, dict):
                signal = {}
            if not isinstance(hints, dict):
                hints = {}

            meta_version = meta.get("version")
            # Strategy v6 order-fills payloads often keep meta.version="1.0"; detect via signal keys too.
            looks_v6 = any(
                signal.get(k) is not None
                for k in ("order_action", "order_tag", "market_position", "position_size")
            )
            if meta_version is not None and str(meta_version).strip():
                values.setdefault(
                    "payload_format",
                    "TRADINGVIEW_META_SIGNAL_HINTS_V6"
                    if looks_v6 or str(meta_version).strip().startswith("6")
                    else "TRADINGVIEW_META_SIGNAL_HINTS_V1",
                )
            else:
                values.setdefault(
                    "payload_format",
                    "TRADINGVIEW_META_SIGNAL_HINTS_V6" if looks_v6 else "TRADINGVIEW_META_SIGNAL_HINTS_V1",
                )

            # Map meta
            if "secret" not in values and meta.get("secret") is not None:
                values["secret"] = meta.get("secret")
            if "platform" not in values and meta.get("platform") is not None:
                values["platform"] = meta.get("platform")

            # Map signal
            if "strategy_id" not in values and signal.get("strategy_id") is not None:
                values["strategy_id"] = signal.get("strategy_id")

            if "strategy_name" not in values:
                values["strategy_name"] = (
                    signal.get("strategy_name")
                    or signal.get("strategy")
                    or signal.get("strategy_id")
                    or values.get("strategy_name")
                )

            if "symbol" not in values and signal.get("symbol") is not None:
                values["symbol"] = signal.get("symbol")
            if "exchange" not in values and signal.get("exchange") is not None:
                values["exchange"] = signal.get("exchange")
            if "interval" not in values and signal.get("timeframe") is not None:
                values["interval"] = signal.get("timeframe")

            if "trade_details" not in values:
                action = _pick_order_action(signal)
                values["trade_details"] = {
                    # Order-Fills schema uses order_action for BUY/SELL; keep legacy side support.
                    "order_action": action or signal.get("side"),
                    "price": (
                        signal.get("ref_price")
                        if signal.get("ref_price") is not None
                        else signal.get("price")
                    ),
                    "quantity": (
                        signal.get("qty")
                        if signal.get("qty") is not None
                        else signal.get("quantity")
                    ),
                    "product": signal.get("product"),
                }

            if "order_id" not in values and signal.get("order_id") is not None:
                values["order_id"] = signal.get("order_id")

            # Map v1 timestamp into bar_time for idempotency + audit.
            if "bar_time" not in values and signal.get("timestamp") is not None:
                values["bar_time"] = signal.get("timestamp")

            if "hints" not in values and hints:
                values["hints"] = hints

            # Enrich hints with signal context (kept optional and forward-compatible).
            try:
                merged_hints = dict(values.get("hints") or {})
                for key in (
                    "order_tag",
                    "market_position",
                    "position_size",
                    "position_size_prev",
                    "amount",
                    "product",
                    "ref_price",
                    "timeframe",
                    "timestamp",
                ):
                    if signal.get(key) is not None:
                        merged_hints.setdefault(key, signal.get(key))
                # Preserve semantic signal side even when order_action drives execution.
                if signal.get("side") is not None:
                    merged_hints.setdefault("signal_side", signal.get("side"))
                values["hints"] = merged_hints
            except Exception:
                pass

            if "product_hint" not in values:
                ph = signal.get("product_hint")
                if ph is None and isinstance(hints, dict):
                    ph = hints.get("product_hint")
                if ph is None and signal.get("product") is not None:
                    ph = signal.get("product")
                if ph is not None:
                    values["product_hint"] = ph

        platform = values.get("platform")
        # Accept either a string or a list like ["fyers"]
        if isinstance(platform, list) and platform:
            values["platform"] = str(platform[0])

        # Accept alternate key naming used by some TradingView templates.
        if "trade_details" not in values and "tradeDetails" in values:
            values["trade_details"] = values.get("tradeDetails")

        # Some TradingView templates emit a root-level timestamp; treat it as bar_time
        # when bar_time is not explicitly provided.
        if "bar_time" not in values and values.get("timestamp") is not None:
            values["bar_time"] = values.get("timestamp")

        # Backward compatible: allow "flat" order fields at the root (without
        # nesting them under trade_details).
        if "trade_details" not in values:
            flat_keys = {
                "order_action",
                "orderAction",
                "order_id",
                "quantity",
                "order_contracts",
                "price",
                "order_price",
                "product",
                "trade_type",
                "comment",
                "order_comment",
                "alert_message",
                "order_alert_message",
            }
            if any(k in values for k in flat_keys):
                values["trade_details"] = {
                    "order_action": values.get("order_action")
                    or values.get("orderAction"),
                    "quantity": (
                        values.get("quantity")
                        if "quantity" in values
                        else values.get("order_contracts")
                    ),
                    "price": (
                        values.get("price")
                        if "price" in values
                        else values.get("order_price")
                    ),
                    "product": values.get("product"),
                    "trade_type": values.get("trade_type"),
                    "comment": values.get("comment") or values.get("order_comment"),
                    "alert_message": values.get("alert_message")
                    or values.get("order_alert_message"),
                }

        # If symbol is omitted but exchange+ticker are present, derive it.
        if "symbol" not in values and "ticker" in values:
            exchange_val = values.get("exchange") or values.get("Exchange") or ""
            ticker_val = values.get("ticker") or ""
            if exchange_val:
                values["symbol"] = f"{exchange_val}:{ticker_val}"
            else:
                values["symbol"] = str(ticker_val)

        # Accept "strategy" as an alias for strategy_name.
        if "strategy_name" not in values and "strategy" in values:
            values["strategy_name"] = values.get("strategy")

        # Normalize bar_time/timestamp representations (ISO string, epoch seconds/ms).
        if "bar_time" in values:
            values["bar_time"] = _coerce_datetime(values.get("bar_time"))
        if "timestamp" in values:
            values["timestamp"] = _coerce_datetime(values.get("timestamp"))

        return values


__all__ = ["TradeDetails", "TradingViewWebhookPayload"]
