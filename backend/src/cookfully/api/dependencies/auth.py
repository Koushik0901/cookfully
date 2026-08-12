from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from cookfully.application.auth import AuthService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerAccount

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_auth_service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth_service
    return service


def require_owner(
    request: Request,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> OwnerAccount:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        raise DomainError(
            "scope_required",
            "Bearer tokens are not permitted on an endpoint without a declared scope.",
            403,
        )
    return _authenticate_browser(request, auth)


def require_browser_owner(
    request: Request,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> OwnerAccount:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        raise DomainError(
            "browser_session_required", "This endpoint requires a browser session.", 403
        )
    return _authenticate_browser(request, auth)


def _authenticate_browser(request: Request, auth: AuthService) -> OwnerAccount:
    session_token = request.cookies.get("cookfully_session")
    if not session_token:
        raise DomainError("authentication_required", "Authentication is required.", 401)
    return auth.authenticate_session(
        session_token,
        request.headers.get("x-csrf-token"),
        enforce_csrf=request.method not in SAFE_METHODS,
    )


def require_scopes(*scopes: str) -> Callable[..., OwnerAccount]:
    def dependency(
        request: Request,
        auth: Annotated[AuthService, Depends(get_auth_service)],
    ) -> OwnerAccount:
        authorization = request.headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            return _authenticate_browser(request, auth)
        return auth.authenticate_token(authorization[7:].strip(), set(scopes))

    return dependency
