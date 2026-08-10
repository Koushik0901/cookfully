from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response, status

from vigor_vine.api.dependencies.auth import require_owner
from vigor_vine.api.routes.recipes import expected_version, idempotency_key
from vigor_vine.api.schemas.grocery import (
    GroceryItemCreateRequest,
    GroceryItemResponse,
    GroceryItemWriteRequest,
    GroceryListResponse,
)
from vigor_vine.application.grocery_lists import GroceryListService
from vigor_vine.application.idempotency import IdempotencyService
from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.models.identity import OwnerAccount

router = APIRouter(tags=["Grocery"])


def grocery_service(request: Request) -> GroceryListService:
    service: GroceryListService = request.app.state.grocery_lists
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


@router.get(
    "/meal-plans/{weekStart}/grocery-list",
    response_model=GroceryListResponse,
    response_model_by_alias=True,
)
def get_grocery_list(
    week_start: Annotated[date, Path(alias="weekStart")],
    service: Annotated[GroceryListService, Depends(grocery_service)],
    owner: Annotated[OwnerAccount, Depends(require_owner)],
) -> GroceryListResponse:
    return GroceryListResponse.from_read(service.get(owner.id, week_start))


@router.post(
    "/meal-plans/{weekStart}/grocery-list",
    response_model=GroceryListResponse,
    response_model_by_alias=True,
)
def regenerate_grocery_list(
    week_start: Annotated[date, Path(alias="weekStart")],
    service: Annotated[GroceryListService, Depends(grocery_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> GroceryListResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="grocery.regenerate",
        payload={"weekStart": week_start.isoformat()},
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return GroceryListResponse.model_validate(decision.response_body)
    try:
        response = GroceryListResponse.from_read(service.generate(owner.id, week_start))
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


@router.post(
    "/meal-plans/{weekStart}/grocery-list/items",
    response_model=GroceryItemResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_grocery_item(
    week_start: Annotated[date, Path(alias="weekStart")],
    payload: GroceryItemCreateRequest,
    service: Annotated[GroceryListService, Depends(grocery_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> GroceryItemResponse:
    request_body = {"weekStart": week_start.isoformat(), **payload.model_dump(mode="json")}
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="grocery.item.create", payload=request_body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return GroceryItemResponse.model_validate(decision.response_body)
    try:
        response = GroceryItemResponse.from_read(
            service.create_manual(
                owner.id,
                week_start,
                display_name=payload.display_name,
                quantity=payload.quantity,
                unit=payload.unit,
                checked=payload.checked,
                position=payload.position,
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
    "/grocery-items/{itemId}",
    response_model=GroceryItemResponse,
    response_model_by_alias=True,
)
def update_grocery_item(
    item_id: Annotated[UUID, Path(alias="itemId")],
    payload: GroceryItemWriteRequest,
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[GroceryListService, Depends(grocery_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> GroceryItemResponse:
    values = payload.to_patch()
    request_body = {"itemId": str(item_id), "version": version, **values}
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="grocery.item.update", payload=request_body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return GroceryItemResponse.model_validate(decision.response_body)
    try:
        response = GroceryItemResponse.from_read(
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


@router.delete("/grocery-items/{itemId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_grocery_item(
    item_id: Annotated[UUID, Path(alias="itemId")],
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[GroceryListService, Depends(grocery_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> Response:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="grocery.item.delete",
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
