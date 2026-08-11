from __future__ import annotations

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status

from vigor_vine.api.dependencies.auth import require_browser_owner, require_scopes
from vigor_vine.api.schemas.jobs import JobAcceptedResponse
from vigor_vine.api.schemas.recipes import (
    ImportRecipeRequest,
    NutritionCorrectionWriteRequest,
    PermanentDeleteRequest,
    RecalculateRequest,
    RecipeDetailResponse,
    RecipePageResponse,
    RecipeResponse,
    RecipeWriteRequest,
    ResolvedNutritionResponse,
)
from vigor_vine.application.corrections import CorrectionService
from vigor_vine.application.idempotency import IdempotencyService
from vigor_vine.application.recipe_queries import RecipeQueryService
from vigor_vine.application.recipes import RecipeService
from vigor_vine.domain.common import DomainError, utc_now
from vigor_vine.infrastructure.models.identity import OwnerAccount
from vigor_vine.infrastructure.observability import correlation_id

router = APIRouter(prefix="/recipes", tags=["Recipes"])


def expected_version(
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> int:
    if if_match is None:
        raise DomainError("if_match_required", "If-Match is required.", 428)
    match = re.fullmatch(r'"([1-9][0-9]*)"', if_match)
    if match is None:
        raise DomainError("if_match_invalid", "If-Match must contain a quoted version.", 422)
    return int(match.group(1))


def idempotency_key(
    value: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=16, max_length=128),
    ],
) -> str:
    return value


def recipe_service(request: Request) -> RecipeService:
    service: RecipeService = request.app.state.recipes
    return service


def recipe_queries(request: Request) -> RecipeQueryService:
    service: RecipeQueryService = request.app.state.recipe_queries
    return service


def correction_service(request: Request) -> CorrectionService:
    service: CorrectionService = request.app.state.corrections
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


@router.get("", response_model=RecipePageResponse, response_model_by_alias=True)
def list_recipes(
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    _: Annotated[OwnerAccount, Depends(require_scopes("recipes:read"))],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    query: Annotated[str | None, Query(max_length=200)] = None,
    nutrition_state: Annotated[str | None, Query(alias="nutritionState")] = None,
    include_archived: Annotated[bool, Query(alias="includeArchived")] = False,
) -> RecipePageResponse:
    return RecipePageResponse.from_read(
        queries.list(
            query=query,
            nutrition_state=nutrition_state,
            include_archived=include_archived,
            cursor=cursor,
            limit=limit,
        )
    )


@router.post(
    "",
    response_model=RecipeResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_recipe(
    payload: RecipeWriteRequest,
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeResponse:
    mutation = recipes.create(payload.to_write(), trace_id=correlation_id.get(), owner_id=owner.id)
    return RecipeResponse.from_read(queries.get(mutation.recipe.id))


@router.post(
    "/import",
    response_model=JobAcceptedResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def import_recipe(
    payload: ImportRecipeRequest,
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> JobAcceptedResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="recipe.import",
        payload=payload.model_dump(mode="json", by_alias=True),
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return JobAcceptedResponse.model_validate(decision.response_body)
    try:
        mutation = recipes.create_import_placeholder(
            str(payload.url), trace_id=correlation_id.get()
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    assert mutation.job is not None
    response = JobAcceptedResponse(job_id=mutation.job.id, resource_id=mutation.recipe.id)
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=202,
        resource_id=mutation.recipe.id,
        job_id=mutation.job.id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.get("/{recipeId}", response_model=RecipeDetailResponse, response_model_by_alias=True)
def get_recipe(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    _: Annotated[OwnerAccount, Depends(require_scopes("recipes:read"))],
) -> RecipeDetailResponse:
    return RecipeDetailResponse.from_read(queries.get(recipe_id))


@router.patch("/{recipeId}", response_model=RecipeDetailResponse, response_model_by_alias=True)
def update_recipe(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    payload: RecipeWriteRequest,
    version: Annotated[int, Depends(expected_version)],
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeDetailResponse:
    recipes.update(
        recipe_id,
        payload.to_write(),
        expected_version=version,
        trace_id=correlation_id.get(),
        owner_id=owner.id,
    )
    return RecipeDetailResponse.from_read(queries.get(recipe_id))


@router.delete("/{recipeId}", status_code=status.HTTP_204_NO_CONTENT)
def archive_recipe(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    version: Annotated[int, Depends(expected_version)],
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> Response:
    recipes.archive(recipe_id, expected_version=version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{recipeId}/restore",
    response_model=RecipeDetailResponse,
    response_model_by_alias=True,
)
def restore_recipe(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    version: Annotated[int, Depends(expected_version)],
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> RecipeDetailResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="recipe.restore",
        payload={"recipeId": str(recipe_id), "version": version},
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return RecipeDetailResponse.model_validate(decision.response_body)
    try:
        recipes.restore(recipe_id, expected_version=version)
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    response = RecipeDetailResponse.from_read(queries.get(recipe_id))
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=200,
        resource_id=recipe_id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.delete("/{recipeId}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_recipe(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    payload: PermanentDeleteRequest,
    version: Annotated[int, Depends(expected_version)],
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> Response:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="recipe.permanent_delete",
        payload={
            "recipeId": str(recipe_id),
            "version": version,
            "confirmation": payload.confirmation,
        },
    )
    if not decision.replay:
        try:
            recipes.permanent_delete(
                recipe_id,
                confirmed=payload.confirmation == "permanently-delete",
                latest_backup_expiry=utc_now(),
                expected_version=version,
            )
        except Exception:
            idempotency.abort(owner_id=owner.id, key=key)
            raise
        idempotency.complete(
            owner_id=owner.id,
            key=key,
            response_status=204,
            resource_id=recipe_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{recipeId}/nutrition/recalculate",
    response_model=JobAcceptedResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def recalculate_recipe_nutrition(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    payload: RecalculateRequest,
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> JobAcceptedResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="recipe.recalculate",
        payload={
            "recipeId": str(recipe_id),
            **payload.model_dump(mode="json", by_alias=True),
        },
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return JobAcceptedResponse.model_validate(decision.response_body)
    try:
        mutation = recipes.recalculate(
            recipe_id,
            reset_corrections=payload.reset_corrections,
            trace_id=correlation_id.get(),
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    assert mutation.job is not None
    response = JobAcceptedResponse(job_id=mutation.job.id, resource_id=recipe_id)
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=202,
        resource_id=recipe_id,
        job_id=mutation.job.id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.post(
    "/{recipeId}/nutrition/corrections",
    response_model=ResolvedNutritionResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_nutrition_correction(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    payload: NutritionCorrectionWriteRequest,
    corrections: Annotated[CorrectionService, Depends(correction_service)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> ResolvedNutritionResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="recipe.correction.create",
        payload={
            "recipeId": str(recipe_id),
            **payload.model_dump(mode="json", by_alias=True),
        },
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return ResolvedNutritionResponse.model_validate(decision.response_body)
    try:
        correction = corrections.activate(
            recipe_id=recipe_id,
            ingredient_id=payload.ingredient_id,
            field=payload.field,
            decimal_value=payload.decimal_value,
            text_value=payload.text_value,
            reference_id_value=payload.reference_id_value,
            reason=payload.reason,
            created_by=owner.id,
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    nutrition = queries.nutrition(recipe_id)
    response = ResolvedNutritionResponse.from_read(nutrition)
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=201,
        resource_id=correction.id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.delete(
    "/{recipeId}/nutrition/corrections/{correctionId}",
    response_model=ResolvedNutritionResponse,
    response_model_by_alias=True,
)
def reset_nutrition_correction(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    correction_id: Annotated[UUID, Path(alias="correctionId")],
    corrections: Annotated[CorrectionService, Depends(correction_service)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> ResolvedNutritionResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="recipe.correction.reset",
        payload={"recipeId": str(recipe_id), "correctionId": str(correction_id)},
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return ResolvedNutritionResponse.model_validate(decision.response_body)
    try:
        corrections.reset(correction_id, recipe_id=recipe_id)
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    nutrition = queries.nutrition(recipe_id)
    response = ResolvedNutritionResponse.from_read(nutrition)
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=200,
        resource_id=correction_id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response
