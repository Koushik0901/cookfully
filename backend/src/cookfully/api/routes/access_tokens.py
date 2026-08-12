from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response, status

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.routes.recipes import idempotency_key
from cookfully.api.schemas.access_tokens import (
    AccessTokenCreatedResponse,
    AccessTokenResponse,
    AccessTokenWriteRequest,
)
from cookfully.application.access_tokens import AccessTokenService
from cookfully.application.idempotency import IdempotencyService
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/access-tokens", tags=["Agent Access"])


def token_service(request: Request) -> AccessTokenService:
    service: AccessTokenService = request.app.state.access_tokens
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


@router.get(
    "",
    response_model=list[AccessTokenResponse],
    response_model_by_alias=True,
    operation_id="listAccessTokens",
)
def list_access_tokens(
    service: Annotated[AccessTokenService, Depends(token_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> list[AccessTokenResponse]:
    return [AccessTokenResponse.from_read(token) for token in service.list(owner.id)]


@router.post(
    "",
    response_model=AccessTokenCreatedResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAccessToken",
)
def create_access_token(
    payload: AccessTokenWriteRequest,
    service: Annotated[AccessTokenService, Depends(token_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> AccessTokenCreatedResponse:
    issued = service.create(
        owner.id, payload.name, set(payload.scopes), expires_at=payload.expires_at
    )
    return AccessTokenCreatedResponse(
        **AccessTokenResponse.from_read(issued.token).model_dump(), secret=issued.secret
    )


@router.delete(
    "/{tokenId}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="revokeAccessToken",
)
def revoke_access_token(
    token_id: Annotated[UUID, Path(alias="tokenId")],
    service: Annotated[AccessTokenService, Depends(token_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> Response:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="access_token.revoke",
        payload={"tokenId": str(token_id)},
    )
    if not decision.replay:
        try:
            service.revoke(owner.id, token_id)
        except Exception:
            idempotency.abort(owner_id=owner.id, key=key)
            raise
        idempotency.complete(owner_id=owner.id, key=key, response_status=204, resource_id=token_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
