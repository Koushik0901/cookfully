from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response, status

from cookfully.api.dependencies.auth import require_scopes
from cookfully.api.routes.recipes import expected_version, idempotency_key
from cookfully.api.schemas.grocery import (
    GroceryItemCreateRequest,
    GroceryItemResponse,
    GroceryItemWriteRequest,
    GroceryListResponse,
    GroceryShoppingStopCreateRequest,
    GroceryShoppingStopResponse,
    GroceryShoppingStopWriteRequest,
)
from cookfully.application.grocery_lists import GroceryListService
from cookfully.application.grocery_shopping_stops import GroceryShoppingStopService
from cookfully.application.idempotency import IdempotencyService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(tags=["Grocery"])


def grocery_service(request: Request) -> GroceryListService:
    service: GroceryListService = request.app.state.grocery_lists
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


def shopping_stop_service(request: Request) -> GroceryShoppingStopService:
    service: GroceryShoppingStopService = request.app.state.grocery_shopping_stops
    return service


@router.get("/grocery-shopping-stops", response_model=tuple[GroceryShoppingStopResponse, ...])
def list_shopping_stops(
    service: Annotated[GroceryShoppingStopService, Depends(shopping_stop_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:read"))],
) -> tuple[GroceryShoppingStopResponse, ...]:
    return tuple(GroceryShoppingStopResponse.from_read(value) for value in service.list(owner.id))


@router.post(
    "/grocery-shopping-stops",
    response_model=GroceryShoppingStopResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_shopping_stop(
    payload: GroceryShoppingStopCreateRequest,
    service: Annotated[GroceryShoppingStopService, Depends(shopping_stop_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:write"))],
) -> GroceryShoppingStopResponse:
    return GroceryShoppingStopResponse.from_read(
        service.create(owner.id, name=payload.name, position=payload.position)
    )


@router.patch(
    "/grocery-shopping-stops/{stopId}",
    response_model=GroceryShoppingStopResponse,
    response_model_by_alias=True,
)
def update_shopping_stop(
    stop_id: Annotated[UUID, Path(alias="stopId")],
    payload: GroceryShoppingStopWriteRequest,
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[GroceryShoppingStopService, Depends(shopping_stop_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:write"))],
) -> GroceryShoppingStopResponse:
    return GroceryShoppingStopResponse.from_read(
        service.update(
            owner.id,
            stop_id,
            expected_version=version,
            name=payload.name,
            position=payload.position,
        )
    )


@router.delete("/grocery-shopping-stops/{stopId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shopping_stop(
    stop_id: Annotated[UUID, Path(alias="stopId")],
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[GroceryShoppingStopService, Depends(shopping_stop_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:write"))],
) -> Response:
    service.remove(owner.id, stop_id, expected_version=version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/meal-plans/{weekStart}/grocery-list",
    response_model=GroceryListResponse,
    response_model_by_alias=True,
)
def get_grocery_list(
    week_start: Annotated[date, Path(alias="weekStart")],
    service: Annotated[GroceryListService, Depends(grocery_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:read"))],
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
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:write"))],
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
    "/meal-plans/{weekStart}/grocery-list/complete",
    response_model=GroceryListResponse,
    response_model_by_alias=True,
)
def complete_grocery_list(
    week_start: Annotated[date, Path(alias="weekStart")],
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[GroceryListService, Depends(grocery_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:write"))],
) -> GroceryListResponse:
    return GroceryListResponse.from_read(
        service.complete(owner.id, week_start, expected_version=version)
    )


@router.post(
    "/meal-plans/{weekStart}/grocery-list/reopen",
    response_model=GroceryListResponse,
    response_model_by_alias=True,
)
def reopen_grocery_list(
    week_start: Annotated[date, Path(alias="weekStart")],
    version: Annotated[int, Depends(expected_version)],
    service: Annotated[GroceryListService, Depends(grocery_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:write"))],
) -> GroceryListResponse:
    return GroceryListResponse.from_read(
        service.reopen(owner.id, week_start, expected_version=version)
    )


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
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:write"))],
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
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:write"))],
    key: Annotated[str, Depends(idempotency_key)],
) -> GroceryItemResponse:
    values = payload.to_patch()
    request_body = {
        "itemId": str(item_id),
        "version": version,
        **payload.model_dump(mode="json", by_alias=True, exclude_unset=True),
    }
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
    owner: Annotated[OwnerAccount, Depends(require_scopes("grocery:write"))],
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
