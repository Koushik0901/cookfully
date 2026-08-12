from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass
from typing import Literal

from redis import Redis
from redis.exceptions import RedisError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from cookfully.application.access_tokens import AccessTokenPrincipal, AccessTokenService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.observability import correlation_id, safe_log

RateCategory = Literal["read", "search", "mutation"]
RATE_LIMITS: dict[RateCategory, int] = {"read": 120, "search": 30, "mutation": 20}
principal_context: contextvars.ContextVar[AccessTokenPrincipal | None] = contextvars.ContextVar(
    "mcp_principal", default=None
)
logger = logging.getLogger(__name__)


class RedisTokenRateLimiter:
    def __init__(self, redis: Redis[str], *, window_seconds: int = 60) -> None:
        self._redis = redis
        self._window_seconds = window_seconds

    def enforce(self, token_id: str, category: RateCategory) -> None:
        key = f"cookfully:mcp:rate:{token_id}:{category}"
        try:
            with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, self._window_seconds, nx=True)
                count, _ = pipe.execute()
        except RedisError as exc:
            raise DomainError(
                "rate_limit_unavailable",
                "Agent access is temporarily unavailable; retry later.",
                503,
            ) from exc
        if int(count) > RATE_LIMITS[category]:
            raise DomainError("rate_limit_exceeded", "Agent rate limit exceeded.", 429)


@dataclass(slots=True)
class McpSecurity:
    tokens: AccessTokenService
    limiter: RedisTokenRateLimiter

    def authenticate(self, authorization: str) -> AccessTokenPrincipal:
        if not authorization.lower().startswith("bearer "):
            raise DomainError("authentication_required", "Bearer authentication is required.", 401)
        return self.tokens.authenticate_principal(authorization[7:].strip(), set())

    def authorize(
        self,
        required_scope: str | None,
        category: RateCategory,
        action: str,
    ) -> AccessTokenPrincipal:
        principal = principal_context.get()
        if principal is None:
            raise DomainError("authentication_required", "Bearer authentication is required.", 401)
        if required_scope is not None and required_scope not in principal.scopes:
            raise DomainError("insufficient_scope", "Access token lacks the required scope.", 403)
        self.limiter.enforce(str(principal.token_id), category)
        safe_log(
            logger,
            "mcp_action",
            fields={
                "action": action,
                "token_id": str(principal.token_id),
                "owner_id": str(principal.owner.id),
                "origin": "external",
                "correlation_id": correlation_id.get(),
            },
        )
        return principal


class McpAuthenticationMiddleware:
    def __init__(self, app: ASGIApp, security: McpSecurity) -> None:
        self._app = app
        self._security = security

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        try:
            principal = self._security.authenticate(headers.get("authorization", ""))
        except DomainError as exc:
            response = JSONResponse(
                {
                    "type": f"urn:cookfully:problem:{exc.code}",
                    "title": exc.safe_message,
                    "status": exc.status,
                    "code": exc.code,
                },
                status_code=exc.status,
                headers={"WWW-Authenticate": "Bearer"},
                media_type="application/problem+json",
            )
            await response(scope, receive, send)
            return
        token = principal_context.set(principal)
        try:
            await self._app(scope, receive, send)
        finally:
            principal_context.reset(token)


def safe_tool_error(exc: Exception) -> str:
    if isinstance(exc, DomainError):
        return f"{exc.code}: {exc.safe_message}"
    logger.exception("MCP tool failed", extra={"correlation_id": correlation_id.get()})
    return "internal_error: The tool could not complete the request."
