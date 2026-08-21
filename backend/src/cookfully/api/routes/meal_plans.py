from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response, status

from cookfully.api.dependencies.auth import require_scopes
from cookfully.api.routes.recipes import expected_version, idempotency_key
from cookfully.api.schemas.plans import (
    MealPlanEntryResponse,
    MealPlanEntrySwapRequest,
    MealPlanEntrySwapResponse,
    MealPlanEntryWriteRequest,
    MealPlanResponse,
)
from cookfully.application.idempotency import IdempotencyService
from cookfully.application.meal_plans import MealPlanService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(tags=["Meal Plans"])


def plan_service(request: Request) -> MealPlanService:
    service: MealPlanService = request.app.state.meal_plans
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


@router.get(
    "/meal-plans/{weekStart}", response_model=MealPlanResponse, response_model_by_alias=True
)
def get_meal_plan(
    week_start: Annotated[date, Path(alias="weekStart")],
    service: Annotated[MealPlanService, Depends(plan_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("plans:read"))],
) -> MealPlanResponse:
    return MealPlanResponse.from_read(service.get(owner.id, week_start))


@router.post(
    "/meal-plans/{weekStart}/entries",
    response_model=MealPlanEntryResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def add_meal_plan_entry(
    week_start: Annotated[date, Path(alias="weekStart")],
    payload: MealPlanEntryWriteRequest,
    service: Annotated[MealPlanService, Depends(plan_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("plans:write"))],
    key: Annotated[str, Depends(idempotency_key)],
) -> MealPlanEntryResponse:
    operation = "meal_plan.entry.add"
    request_body = {
        "weekStart": week_start.isoformat(),
        **payload.model_dump(mode="json", by_alias=True),
    }
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation=operation, payload=request_body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return MealPlanEntryResponse.model_validate(decision.response_body)
    try:
        response = MealPlanEntryResponse.from_read(
            service.add(owner.id, week_start, payload.to_write())
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=201,
        resource_id=response.id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.patch(
    "/meal-plan-entries/{entryId}",
    response_model=MealPlanEntryResponse,
    response_model_by_alias=True,
)
def update_meal_plan_entry(
    entry_id: Annotated[UUID, Path(alias="entryId")],
    payload: MealPlanEntryWriteRequest,
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[MealPlanService, Depends(plan_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("plans:write"))],
    key: Annotated[str, Depends(idempotency_key)],
) -> MealPlanEntryResponse:
    request_body = {
        "entryId": str(entry_id),
        "version": version,
        **payload.model_dump(mode="json", by_alias=True),
    }
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="meal_plan.entry.update", payload=request_body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return MealPlanEntryResponse.model_validate(decision.response_body)
    try:
        response = MealPlanEntryResponse.from_read(
            service.update(owner.id, entry_id, payload.to_write(), expected_version=version)
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=200,
        resource_id=entry_id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.post(
    "/meal-plan-entries/{entryId}/swap",
    response_model=MealPlanEntrySwapResponse,
    response_model_by_alias=True,
)
def swap_meal_plan_entries(
    entry_id: Annotated[UUID, Path(alias="entryId")],
    payload: MealPlanEntrySwapRequest,
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[MealPlanService, Depends(plan_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("plans:write"))],
    key: Annotated[str, Depends(idempotency_key)],
) -> MealPlanEntrySwapResponse:
    request_body = {
        "entryId": str(entry_id),
        "version": version,
        **payload.model_dump(mode="json", by_alias=True),
    }
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="meal_plan.entry.swap", payload=request_body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return MealPlanEntrySwapResponse.model_validate(decision.response_body)
    try:
        source, target = service.swap(
            owner.id,
            entry_id,
            payload.target_entry_id,
            expected_version=version,
            target_expected_version=payload.target_version,
        )
        response = MealPlanEntrySwapResponse(
            source=MealPlanEntryResponse.from_read(source),
            target=MealPlanEntryResponse.from_read(target),
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=200,
        resource_id=entry_id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.delete("/meal-plan-entries/{entryId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal_plan_entry(
    entry_id: Annotated[UUID, Path(alias="entryId")],
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[MealPlanService, Depends(plan_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("plans:write"))],
    key: Annotated[str, Depends(idempotency_key)],
) -> Response:
    request_body = {"entryId": str(entry_id), "version": version}
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="meal_plan.entry.delete", payload=request_body
    )
    if not decision.replay:
        try:
            service.remove(owner.id, entry_id, expected_version=version)
        except Exception:
            idempotency.abort(owner_id=owner.id, key=key)
            raise
        idempotency.complete(owner_id=owner.id, key=key, response_status=204, resource_id=entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
