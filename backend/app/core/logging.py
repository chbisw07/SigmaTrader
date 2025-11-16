from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from typing import Any, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message


def configure_logging(level: int = logging.INFO) -> None:
    """Configure application-wide structured logging."""

    handler = logging.StreamHandler(sys.stdout)

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
            payload: Dict[str, Any] = {
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if hasattr(record, "extra") and isinstance(record.extra, dict):
                payload.update(record.extra)  # type: ignore[arg-type]
            if record.exc_info:
                payload["exc_info"] = self.formatException(record.exc_info)
            return json.dumps(payload, ensure_ascii=False)

    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    # Remove default handlers that may have been set by libraries.
    root.handlers.clear()
    root.addHandler(handler)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware that adds correlation IDs and basic request logging."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Put the correlation id in the state so handlers can reuse it.
        request.state.correlation_id = correlation_id

        start = time.perf_counter()

        # Ensure the correlation id is visible in the response.
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", correlation_id.encode("utf-8")))
                message["headers"] = headers
            await send(message)  # type: ignore[name-defined]

        send = None  # type: ignore[assignment]

        async def call_next_with_send(req: Request):
            nonlocal send
            send = await call_next(req)

        # Note: BaseHTTPMiddleware expects call_next to be called directly.
        # We only add logging; response header is set via normal flow.

        response = await call_next(request)

        duration = time.perf_counter() - start

        logging.getLogger("sigma.request").info(
            "HTTP request",
            extra={
                "extra": {
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": int(duration * 1000),
                }
            },
        )

        return response


def log_with_correlation(
    logger: logging.Logger,
    request: Request,
    level: int,
    message: str,
    **fields: Any,
) -> None:
    """Helper to emit a log with the request's correlation id."""

    correlation_id = getattr(request.state, "correlation_id", None)
    extra = {"correlation_id": correlation_id}
    extra.update(fields)
    logger.log(level, message, extra={"extra": extra})


__all__ = ["configure_logging", "RequestContextMiddleware", "log_with_correlation"]
