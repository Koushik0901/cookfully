from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from vigor_vine.api.dependencies.auth import require_browser_owner
from vigor_vine.api.routes.recipes import expected_version, idempotency_key
from vigor_vine.api.schemas.pantry import (
    PantryDeductionApplyRequest,
    PantryDeductionResponse,
    PantryItemResponse,
    PantryItemWriteRequest,
    PantryRecipeMatchResponse,
)
from vigor_vine.application.idempotency import IdempotencyService
from vigor_vine.application.pantry import PantryService
from vigor_vine.application.pantry_deductions import PantryDeductionService
from vigor_vine.application.pantry_search import PantrySearchService
from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.models.identity import OwnerAccount

router = APIRouter(tags=["Pantry"])


def pantry_service(request: Request) -> PantryService:
    service: PantryService = request.app.state.pantry
    return service


def search_service(request: Request) -> PantrySearchService:
    service: PantrySearchService = request.app.state.pantry_search
    return service


def deduction_service(request: Request) -> PantryDeductionService:
    service: PantryDeductionService = request.app.state.pantry_deductions
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


@router.get("/pantry-items", response_model=list[PantryItemResponse], response_model_by_alias=True)
def list_pantry_items(
    service: Annotated[PantryService, Depends(pantry_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> list[PantryItemResponse]:
    return [PantryItemResponse.from_read(item) for item in service.list(owner.id)]


@router.post(
    "/pantry-items",
    response_model=PantryItemResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_pantry_item(
    payload: PantryItemWriteRequest,
    service: Annotated[PantryService, Depends(pantry_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> PantryItemResponse:
    request_body = payload.model_dump(mode="json", by_alias=True)
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="pantry.item.create", payload=request_body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return PantryItemResponse.model_validate(decision.response_body)
    try:
        response = PantryItemResponse.from_read(
            service.create(
                owner.id,
                display_name=payload.display_name,
                quantity=payload.quantity,
                unit=payload.unit,
                food_reference_id=payload.food_reference_id,
            )
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
    "/pantry-items/{itemId}", response_model=PantryItemResponse, response_model_by_alias=True
)
def update_pantry_item(
    item_id: Annotated[UUID, Path(alias="itemId")],
    payload: PantryItemWriteRequest,
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[PantryService, Depends(pantry_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> PantryItemResponse:
    request_body = {
        "itemId": str(item_id),
        "version": version,
        **payload.model_dump(mode="json", by_alias=True),
    }
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="pantry.item.update", payload=request_body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return PantryItemResponse.model_validate(decision.response_body)
    values = payload.model_dump(by_alias=False)
    try:
        response = PantryItemResponse.from_read(
            service.update(owner.id, item_id, values, expected_version=version)
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=200,
        resource_id=response.id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.delete("/pantry-items/{itemId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pantry_item(
    item_id: Annotated[UUID, Path(alias="itemId")],
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[PantryService, Depends(pantry_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> Response:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="pantry.item.delete",
        payload={"itemId": str(item_id), "version": version},
    )
    if not decision.replay:
        try:
            service.remove(owner.id, item_id, expected_version=version)
        except Exception:
            idempotency.abort(owner_id=owner.id, key=key)
            raise
        idempotency.complete(owner_id=owner.id, key=key, response_status=204, resource_id=item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/pantry/recipe-matches",
    response_model=list[PantryRecipeMatchResponse],
    response_model_by_alias=True,
)
def find_makeable_recipes(
    service: Annotated[PantrySearchService, Depends(search_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    query: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[PantryRecipeMatchResponse]:
    matches = service.search(owner.id)
    if query:
        normalized = query.casefold().strip()
        matches = tuple(item for item in matches if normalized in item.title.casefold())
    return [PantryRecipeMatchResponse.from_score(item) for item in matches[:limit]]


@router.post(
    "/meal-plans/{weekStart}/grocery-list/pantry-deductions",
    response_model=list[PantryDeductionResponse],
    response_model_by_alias=True,
)
def apply_pantry_deductions(
    week_start: Annotated[date, Path(alias="weekStart")],
    payload: PantryDeductionApplyRequest,
    service: Annotated[PantryDeductionService, Depends(deduction_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> list[PantryDeductionResponse]:
    request_body = {"weekStart": week_start.isoformat(), **payload.model_dump(mode="json")}
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="pantry.deductions.apply", payload=request_body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return [
            PantryDeductionResponse.model_validate(item) for item in decision.response_body["items"]
        ]
    try:
        response = [
            PantryDeductionResponse.from_read(item)
            for item in service.apply(
                owner.id,
                week_start,
                expected_grocery_list_version=payload.expected_grocery_list_version,
                grocery_item_ids=payload.grocery_item_ids,
            )
        ]
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=200,
        resource_id=response[0].id if response else None,
        response_body={"items": [item.model_dump(mode="json", by_alias=True) for item in response]},
    )
    return response


@router.delete(
    "/pantry-deductions/{deductionId}",
    response_model=PantryDeductionResponse,
    response_model_by_alias=True,
)
def reverse_pantry_deduction(
    deduction_id: Annotated[UUID, Path(alias="deductionId")],
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[PantryDeductionService, Depends(deduction_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> PantryDeductionResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="pantry.deduction.reverse",
        payload={"deductionId": str(deduction_id), "version": version},
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return PantryDeductionResponse.model_validate(decision.response_body)
    try:
        response = PantryDeductionResponse.from_read(
            service.reverse(owner.id, deduction_id, expected_version=version)
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=200,
        resource_id=response.id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response
