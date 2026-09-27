"""Shared structured logging and correlation context."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from fastapi import FastAPI, Request


correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id",
    default="-",
)


class CorrelationFilter(logging.Filter):
    """Inject the active correlation ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log event for machine-friendly ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(
                record,
                "correlation_id",
                correlation_id_var.get(),
            ),
        }

        for key in (
            "event",
            "http_method",
            "http_path",
            "http_status",
            "duration_ms",
            "batch_id",
            "receive_count",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    """Configure root logging without duplicating handlers across app factories."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    log_format = os.getenv("LOG_FORMAT", "json").lower()

    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stdout))

    formatter: logging.Formatter
    if log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s "
            "[correlation_id=%(correlation_id)s] %(message)s"
        )

    for handler in root.handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)
        if not any(isinstance(item, CorrelationFilter) for item in handler.filters):
            handler.addFilter(CorrelationFilter())


def _safe_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate and len(candidate) <= 128 and all(
        char.isalnum() or char in "-_.:" for char in candidate
    ):
        return candidate
    return uuid.uuid4().hex


@contextmanager
def correlation_scope(correlation_id: str) -> Iterator[str]:
    """Bind a correlation ID for logs emitted within a unit of work."""
    token = correlation_id_var.set(_safe_request_id(correlation_id))
    try:
        yield correlation_id_var.get()
    finally:
        correlation_id_var.reset(token)


def install_request_observability(app: FastAPI) -> None:
    """Attach request correlation and latency logging middleware."""

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = _safe_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        started_at = time.perf_counter()

        with correlation_scope(request_id):
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            logging.getLogger("app.http").info(
                "request_completed",
                extra={
                    "event": "http_request",
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
