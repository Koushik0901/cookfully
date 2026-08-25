from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.routes.recipes import expected_version, idempotency_key
from cookfully.api.schemas.pantry import (
    BulkPantryCreateResponse,
    PantryDeductionApplyRequest,
    PantryDeductionResponse,
    PantryItemResponse,
    PantryItemWriteRequest,
    PantryRecipeMatchResponse,
)
from cookfully.application.idempotency import IdempotencyService
from cookfully.application.pantry import PantryService
from cookfully.application.pantry_deductions import PantryDeductionService
from cookfully.application.pantry_search import PantrySearchService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerAccount

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
    response_model=PantryItemResponse | BulkPantryCreateResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_pantry_item(
    payload: PantryItemWriteRequest,
    service: Annotated[PantryService, Depends(pantry_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> PantryItemResponse | BulkPantryCreateResponse:
    # idempotency begin first to support replay of both single and bulk shapes
    request_body = payload.model_dump(mode="json", by_alias=True)
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="pantry.item.create", payload=request_body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        if "items" in decision.response_body:
            return BulkPantryCreateResponse.model_validate(decision.response_body)
        return PantryItemResponse.model_validate(decision.response_body)
    # Inline bulk paste: detect delimiters and race pantry_extract (600ms gate)
    display_name = payload.display_name
    has_bulk = "," in display_name or ";" in display_name or "\n" in display_name
    if has_bulk:
        try:
            from cookfully.infrastructure.config import get_settings

            settings = get_settings()
            if settings.intelligence_inline_enabled:
                from cookfully.application.inline_repair import (
                    InlineRepairGateway,
                    PantryExtractSchema,
                    _window,
                )
                from cookfully.domain.common import utc_now
                from cookfully.intelligence.client import IntelligenceClient
                from cookfully.intelligence.contracts import InferenceRequest, ToolDefinition

                system = f"date: {utc_now().date().isoformat()}; locale: en-US; device: server"

                import time as _time

                from cookfully.application.inline_repair import _est_toks as _est

                prompt, has_more = _window(display_name)
                _prompt_toks_est = _est(
                    prompt
                )  # for observability (plumbed via _emit_log if needed)
                client = IntelligenceClient(
                    settings.intelligence_url,
                    settings.intelligence_service_key.get_secret_value(),
                    enabled=settings.intelligence_enabled,
                    timeout_seconds=settings.intelligence_timeout_seconds,
                )
                gw = InlineRepairGateway(
                    client,
                    threshold=settings.intelligence_inline_threshold,
                    timeout_ms=settings.intelligence_inline_timeout_ms,
                )
                tools = (
                    ToolDefinition(
                        name="pantry_items",
                        description="Extract pantry items",
                        parameters=PantryExtractSchema.model_json_schema(),
                    ),
                )
                req = InferenceRequest(
                    requestId="inline-pantry",
                    operation="pantry_extract",
                    prompt=prompt,
                    tools=tools,
                    context={},
                    system=system,
                )
                resp = None
                t0 = _time.perf_counter()
                try:
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(client.infer, req, timeout_seconds=gw._timeout),
                        timeout=gw._timeout,
                    )
                except (asyncio.TimeoutError, TimeoutError):  # noqa: UP041
                    resp = None
                except Exception:
                    resp = None
                # second-window retry: if first is empty/unsupported and has_more and budget>120ms
                if has_more:
                    is_empty = resp is None or resp.status != "ok" or not resp.function_calls
                    if not is_empty and resp is not None and resp.function_calls:
                        try:
                            args0 = resp.function_calls[0].arguments
                            if isinstance(args0, dict) and "items" in args0:
                                vals = args0.get("items")
                                if isinstance(vals, list) and len(vals) == 0:
                                    is_empty = True
                        except Exception:
                            pass
                    if is_empty:
                        elapsed = _time.perf_counter() - t0
                        remaining = gw._timeout - elapsed
                        if remaining > 0.12:
                            second_prompt = display_name[400:800][:256]
                            second_req = InferenceRequest(
                                requestId="inline-pantry",
                                operation="pantry_extract",
                                prompt=second_prompt,
                                tools=tools,
                                context={},
                                system=system,
                            )
                            try:
                                resp2 = await asyncio.wait_for(
                                    asyncio.to_thread(
                                        client.infer, second_req, timeout_seconds=remaining
                                    ),
                                    timeout=remaining,
                                )
                                if resp2 is not None and gw._gate(resp2):
                                    resp = resp2
                            except (asyncio.TimeoutError, TimeoutError):  # noqa: UP041
                                pass
                            except Exception:
                                pass
                if resp is not None and gw._gate(resp):
                    try:
                        parsed = PantryExtractSchema.model_validate(
                            resp.function_calls[0].arguments
                        )
                    except Exception:
                        parsed = None
                    if parsed is not None and len(parsed.items) > 1:
                        created = [
                            service._create_single(
                                owner.id,
                                display_name=i.name,
                                quantity=Decimal(str(i.quantity)),
                                unit=i.unit,
                                expires_on=payload.expires_on,
                                food_reference_id=None,
                                owner_food_id=None,
                            )
                            for i in parsed.items
                        ]
                        bulk = BulkPantryCreateResponse(
                            items=[PantryItemResponse.from_read(r) for r in created],
                            created=len(created),
                        )
                        # idempotency stores vector
                        try:
                            idempotency.complete(
                                owner_id=owner.id,
                                key=key,
                                response_status=201,
                                resource_id=bulk.items[0].id,
                                response_body={
                                    "items": [
                                        i.model_dump(mode="json", by_alias=True) for i in bulk.items
                                    ],
                                    "created": bulk.created,
                                },
                            )
                        except Exception:
                            pass
                        return bulk
        except Exception:
            pass
    try:
        result = service.create(
            owner.id,
            display_name=payload.display_name,
            quantity=payload.quantity,
            unit=payload.unit,
            expires_on=payload.expires_on,
            food_reference_id=payload.food_reference_id,
            owner_food_id=payload.owner_food_id,
        )
        response = PantryItemResponse.from_read(result)
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
