from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from vigor_vine.application.auth import AuthService
from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.models.identity import OwnerAccount

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
        return auth.authenticate_token(authorization[7:].strip(), set())
    session_token = request.cookies.get("vv_session")
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
            return require_owner(request, auth)
        return auth.authenticate_token(authorization[7:].strip(), set(scopes))

    return dependency
