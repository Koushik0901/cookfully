from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, status

from vigor_vine.api.dependencies.auth import require_owner
from vigor_vine.api.routes.recipes import idempotency_key
from vigor_vine.api.schemas.jobs import JobAcceptedResponse
from vigor_vine.api.schemas.plans import MealPlanResponse
from vigor_vine.api.schemas.suggestions import (
    SuggestionAcceptanceRequest,
    SuggestionRequest,
    SuggestionResultResponse,
)
from vigor_vine.application.idempotency import IdempotencyService
from vigor_vine.application.suggestions import SuggestionService
from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.models.identity import OwnerAccount
from vigor_vine.infrastructure.observability import correlation_id

router = APIRouter(prefix="/suggestions", tags=["Suggestions"])


def suggestion_service(request: Request) -> SuggestionService:
    service: SuggestionService = request.app.state.suggestions
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


@router.post(
    "",
    response_model=JobAcceptedResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_suggestion(
    payload: SuggestionRequest,
    service: Annotated[SuggestionService, Depends(suggestion_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> JobAcceptedResponse:
    body = payload.model_dump(mode="json", by_alias=True)
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="suggestion.create", payload=body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return JobAcceptedResponse.model_validate(decision.response_body)
    try:
        accepted = service.request(owner.id, payload.to_write(), trace_id=correlation_id.get())
        response = JobAcceptedResponse(
            job_id=accepted.job_id,
            resource_id=accepted.suggestion_id,
            status=accepted.status,
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=202,
        resource_id=accepted.suggestion_id,
        job_id=accepted.job_id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.get(
    "/{suggestionId}", response_model=SuggestionResultResponse, response_model_by_alias=True
)
def get_suggestion(
    suggestion_id: Annotated[UUID, Path(alias="suggestionId")],
    service: Annotated[SuggestionService, Depends(suggestion_service)],
    owner: Annotated[OwnerAccount, Depends(require_owner)],
) -> SuggestionResultResponse:
    return SuggestionResultResponse.from_read(service.get(suggestion_id, owner.id))


@router.post(
    "/{suggestionId}/accept",
    response_model=MealPlanResponse,
    response_model_by_alias=True,
)
def accept_suggestion(
    suggestion_id: Annotated[UUID, Path(alias="suggestionId")],
    payload: SuggestionAcceptanceRequest,
    service: Annotated[SuggestionService, Depends(suggestion_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> MealPlanResponse:
    body = {
        "suggestionId": str(suggestion_id),
        **payload.model_dump(mode="json", by_alias=True),
    }
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="suggestion.accept", payload=body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return MealPlanResponse.model_validate(decision.response_body)
    try:
        response = MealPlanResponse.from_read(
            service.accept(
                owner.id,
                suggestion_id,
                payload.selected_item_ids,
                expected_plan_version=payload.expected_plan_version,
            )
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=200,
        resource_id=suggestion_id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response
