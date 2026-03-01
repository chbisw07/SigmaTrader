from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ClientTimeContext:
    now_iso: str
    time_zone: str | None
    utc_offset_minutes: int | None


def _fmt_offset(offset_min: int) -> str:
    sign = "+" if offset_min >= 0 else "-"
    m = abs(int(offset_min))
    hh = m // 60
    mm = m % 60
    return f"UTC{sign}{hh:02d}:{mm:02d}"


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        try:
            return int(value.strip())
        except Exception:
            return None
    return None


def build_client_time_context(
    *,
    client_now_ms: Any | None,
    client_time_zone: Any | None,
    client_utc_offset_minutes: Any | None,
) -> ClientTimeContext | None:
    now_ms = _coerce_int(client_now_ms)
    if now_ms is None or now_ms <= 0:
        return None

    tz_name = str(client_time_zone or "").strip() or None
    offset_min = _coerce_int(client_utc_offset_minutes)

    dt_utc = datetime.fromtimestamp(float(now_ms) / 1000.0, tz=timezone.utc)
    dt_local = dt_utc

    if tz_name and ZoneInfo is not None:
        try:
            dt_local = dt_utc.astimezone(ZoneInfo(tz_name))
        except Exception:
            dt_local = dt_utc

    if dt_local is dt_utc and offset_min is not None:
        try:
            dt_local = dt_utc.astimezone(timezone(timedelta(minutes=int(offset_min))))
        except Exception:
            dt_local = dt_utc

    now_iso = dt_local.isoformat(timespec="seconds")
    return ClientTimeContext(now_iso=now_iso, time_zone=tz_name, utc_offset_minutes=offset_min)


def time_context_from_ui_context(ui_context: Any | None) -> ClientTimeContext | None:
    if not isinstance(ui_context, dict):
        return None
    return build_client_time_context(
        client_now_ms=ui_context.get("client_now_ms"),
        client_time_zone=ui_context.get("client_time_zone"),
        client_utc_offset_minutes=ui_context.get("client_utc_offset_minutes"),
    )


def time_context_from_test_payload(payload: Any) -> ClientTimeContext | None:
    if payload is None:
        return None
    return build_client_time_context(
        client_now_ms=getattr(payload, "client_now_ms", None),
        client_time_zone=getattr(payload, "client_time_zone", None),
        client_utc_offset_minutes=getattr(payload, "client_utc_offset_minutes", None),
    )


def format_time_context_line(ctx: ClientTimeContext) -> str:
    tz_part = f"{ctx.time_zone}" if ctx.time_zone else None
    off_part = _fmt_offset(ctx.utc_offset_minutes) if ctx.utc_offset_minutes is not None else None
    parts = [p for p in (tz_part, off_part) if p]
    suffix = f" ({', '.join(parts)})" if parts else ""
    return f"{ctx.now_iso}{suffix}"


__all__ = [
    "ClientTimeContext",
    "build_client_time_context",
    "format_time_context_line",
    "time_context_from_test_payload",
    "time_context_from_ui_context",
]

