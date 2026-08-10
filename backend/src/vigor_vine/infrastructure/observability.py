from __future__ import annotations

import contextvars
import logging
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastapi import Request, Response

from vigor_vine.domain.common import uuid7

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")
SENSITIVE_KEY = re.compile(r"password|secret|token|authorization|cookie|prompt|goal|raw|html", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class HealthMetrics:
    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()

    def increment(self, metric: str, **labels: str) -> None:
        suffix = ",".join(f"{key}={value}" for key, value in sorted(labels.items()))
        self.counters[f"{metric}|{suffix}"] += 1


async def correlation_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    requested = request.headers.get("x-request-id", "")
    request_id = requested if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", requested) else str(uuid7())
    token = correlation_id.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        correlation_id.reset(token)


def safe_log(logger: logging.Logger, message: str, *, fields: Mapping[str, Any]) -> None:
    logger.info(
        message, extra={"safe_fields": redact(fields), "correlation_id": correlation_id.get()}
    )
