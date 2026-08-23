from __future__ import annotations

import asyncio
import re
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse

from cookfully.api.dependencies.auth import require_browser_owner, require_scopes
from cookfully.api.schemas.foods import OwnerFoodSelectionRequest
from cookfully.api.schemas.jobs import JobAcceptedResponse
from cookfully.api.schemas.recipes import (
    DuplicateSummary,
    ImportConfirmRequest,
    ImportMergeRequest,
    ImportPreviewIngredient,
    ImportPreviewRequest,
    ImportPreviewResponse,
    ImportPreviewSection,
    ImportRecipeRequest,
    NutritionCorrectionWriteRequest,
    PermanentDeleteRequest,
    RecalculateRequest,
    RecipeBulkArchiveRequest,
    RecipeBulkArchiveResponse,
    RecipeBulkArchiveResult,
    RecipeCollectionResponse,
    RecipeCollectionWriteRequest,
    RecipeDetailResponse,
    RecipeOrganizationWriteRequest,
    RecipePageResponse,
    RecipePhotoAttachRequest,
    RecipeResponse,
    RecipeSourceImageChoiceRequest,
    RecipeSourceImageResponse,
    RecipeWriteRequest,
    ResolvedNutritionResponse,
    ThumbnailCropRequest,
)
from cookfully.application.corrections import CorrectionService
from cookfully.application.idempotency import IdempotencyService
from cookfully.application.import_preview import ImportPreviewCoordinator
from cookfully.application.recipe_organization import RecipeOrganizationService
from cookfully.application.recipe_photos import RecipePhotoService
from cookfully.application.recipe_queries import RecipeQueryService
from cookfully.application.recipes import RecipeService
from cookfully.domain.common import DomainError, utc_now
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.observability import correlation_id

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


def import_preview_coordinator(request: Request) -> ImportPreviewCoordinator:
    service: ImportPreviewCoordinator = request.app.state.import_previews
    return service


def recipe_queries(request: Request) -> RecipeQueryService:
    service: RecipeQueryService = request.app.state.recipe_queries
    return service


def recipe_photos(request: Request) -> RecipePhotoService:
    service: RecipePhotoService = request.app.state.recipe_photos
    return service


def recipe_organization(request: Request) -> RecipeOrganizationService:
    service: RecipeOrganizationService = request.app.state.recipe_organization
    return service


@router.get(
    "/collections",
    response_model=tuple[RecipeCollectionResponse, ...],
    response_model_by_alias=True,
)
def list_recipe_collections(
    organization: Annotated[RecipeOrganizationService, Depends(recipe_organization)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("recipes:read"))],
) -> tuple[RecipeCollectionResponse, ...]:
    return tuple(
        RecipeCollectionResponse.from_read(value) for value in organization.collections(owner.id)
    )


@router.post(
    "/collections",
    response_model=RecipeCollectionResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_recipe_collection(
    payload: RecipeCollectionWriteRequest,
    organization: Annotated[RecipeOrganizationService, Depends(recipe_organization)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeCollectionResponse:
    if payload.name is None:
        raise DomainError("recipe_collection_name_required", "Collection name is required.", 422)
    return RecipeCollectionResponse.from_read(
        organization.create_collection(owner.id, payload.name)
    )


@router.patch(
    "/collections/{collectionId}",
    response_model=RecipeCollectionResponse,
    response_model_by_alias=True,
)
def update_recipe_collection(
    collection_id: Annotated[UUID, Path(alias="collectionId")],
    payload: RecipeCollectionWriteRequest,
    version: Annotated[int, Depends(expected_version)],
    organization: Annotated[RecipeOrganizationService, Depends(recipe_organization)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeCollectionResponse:
    return RecipeCollectionResponse.from_read(
        organization.update_collection(
            owner.id,
            collection_id,
            version,
            name=payload.name,
            position=payload.position,
        )
    )


@router.delete("/collections/{collectionId}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe_collection(
    collection_id: Annotated[UUID, Path(alias="collectionId")],
    version: Annotated[int, Depends(expected_version)],
    organization: Annotated[RecipeOrganizationService, Depends(recipe_organization)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> Response:
    organization.delete_collection(owner.id, collection_id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{recipeId}/organization", response_model=RecipeDetailResponse, response_model_by_alias=True
)
def replace_recipe_organization(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    payload: RecipeOrganizationWriteRequest,
    version: Annotated[int, Depends(expected_version)],
    organization: Annotated[RecipeOrganizationService, Depends(recipe_organization)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeDetailResponse:
    organization.replace(
        owner.id,
        recipe_id,
        version,
        favorite=payload.favorite,
        collection_ids=payload.collection_ids,
        meal_roles=payload.meal_roles,
    )
    return RecipeDetailResponse.from_read(queries.get(recipe_id))


def correction_service(request: Request) -> CorrectionService:
    service: CorrectionService = request.app.state.corrections
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


_ALLOWED_UNITS = {"g", "kg", "ml", "l", "cup", "tbsp", "tsp", "count", "scoop", "oz", "lb"}


async def _maybe_repair_recipe_ingredients(payload: RecipeWriteRequest) -> RecipeWriteRequest:
    """Gap-only unit repair for editor rows where unit is None or not in allowlist."""
    try:
        from cookfully.infrastructure.config import get_settings

        settings = get_settings()
        if not settings.intelligence_inline_enabled:
            return payload
        needs: list[int] = []
        for idx, ing in enumerate(payload.ingredients):
            if ing.unit is None or ing.unit not in _ALLOWED_UNITS:
                needs.append(idx)
        if not needs:
            return payload
        from cookfully.application.inline_repair import InlineRepairGateway
        from cookfully.domain.common import utc_now
        from cookfully.intelligence.client import IntelligenceClient

        system = f"date: {utc_now().date().isoformat()}; locale: en-US; device: server"
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

        async def _repair_one(ing: Any) -> str | None:
            legacy: dict[str, Any] = {
                "quantity": float(ing.quantity_min) if ing.quantity_min is not None else None,
                "unit": ing.unit,
            }
            try:
                result = await gw.repair_ingredient_row(legacy, ing.original_text[:256], system)
            except Exception:
                return None
            new_unit = result.get("unit")
            if isinstance(new_unit, str) and new_unit != ing.unit and new_unit in _ALLOWED_UNITS:
                return new_unit
            return None

        # Parallel gather similar to Task4 (bounded 600ms per row via gateway)
        tasks = [_repair_one(payload.ingredients[i]) for i in needs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        new_ingredients = list(payload.ingredients)
        for idx, res in zip(needs, results, strict=False):
            if isinstance(res, Exception) or res is None:
                continue
            orig = new_ingredients[idx]
            try:
                new_ingredients[idx] = orig.model_copy(update={"unit": res})
            except Exception:
                continue
        return payload.model_copy(update={"ingredients": tuple(new_ingredients)})
    except Exception:
        return payload


@router.get("", response_model=RecipePageResponse, response_model_by_alias=True)
def list_recipes(
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    _: Annotated[OwnerAccount, Depends(require_scopes("recipes:read"))],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    query: Annotated[str | None, Query(max_length=200)] = None,
    nutrition_state: Annotated[str | None, Query(alias="nutritionState")] = None,
    favorite: bool | None = None,
    collection_id: Annotated[UUID | None, Query(alias="collectionId")] = None,
    meal_role: Annotated[str | None, Query(alias="mealRole")] = None,
    include_archived: Annotated[bool, Query(alias="includeArchived")] = False,
) -> RecipePageResponse:
    return RecipePageResponse.from_read(
        queries.list(
            query=query,
            nutrition_state=nutrition_state,
            favorite=favorite,
            collection_id=collection_id,
            meal_role=meal_role,
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
async def create_recipe(
    payload: RecipeWriteRequest,
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeResponse:
    repaired = await _maybe_repair_recipe_ingredients(payload)
    mutation = recipes.create(repaired.to_write(), trace_id=correlation_id.get(), owner_id=owner.id)
    return RecipeResponse.from_read(queries.get(mutation.recipe.id))


@router.post(
    "/bulk/archive",
    response_model=RecipeBulkArchiveResponse,
    response_model_by_alias=True,
)
def bulk_archive_recipes(
    payload: RecipeBulkArchiveRequest,
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeBulkArchiveResponse:
    results = recipes.bulk_archive(tuple((item.id, item.version) for item in payload.recipes))
    return RecipeBulkArchiveResponse(
        results=tuple(
            RecipeBulkArchiveResult(
                id=result.recipe_id,
                status=result.status,
                version=result.version,
                code=result.code,
                message=result.message,
            )
            for result in results
        )
    )


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


@router.post(
    "/import/preview",
    response_model=ImportPreviewResponse,
    response_model_by_alias=True,
)
async def preview_recipe_import(
    payload: ImportPreviewRequest,
    coordinator: Annotated[ImportPreviewCoordinator, Depends(import_preview_coordinator)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> Response | ImportPreviewResponse:
    try:
        data = await coordinator.preview(
            str(payload.url), owner_id=owner.id, trace_id=correlation_id.get()
        )
    except DomainError:
        raise
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"ready": False}
        )
    return ImportPreviewResponse(
        parse_id=data["parse_id"],
        title=data["title"],
        yield_quantity=data["yield_quantity"],
        yield_text=data["yield_text"],
        image_sources=tuple(data["image_sources"]),
        duplicates=tuple(DuplicateSummary(**item) for item in data.get("duplicates", [])),
        sections=tuple(
            ImportPreviewSection(
                title=section["title"],
                ingredients=tuple(
                    ImportPreviewIngredient(
                        original_text=ingredient["original_text"],
                        needs_quantity=ingredient["needs_quantity"],
                    )
                    for ingredient in section["ingredients"]
                ),
                instructions=tuple(section["instructions"]),
            )
            for section in data["sections"]
        ),
        origin_kind=data.get("origin_kind", "web_import"),
    )


@router.post(
    "/import/confirm",
    response_model=JobAcceptedResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def confirm_recipe_import(
    payload: ImportConfirmRequest,
    coordinator: Annotated[ImportPreviewCoordinator, Depends(import_preview_coordinator)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> JobAcceptedResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="recipe.import.confirm",
        payload=payload.model_dump(mode="json", by_alias=True),
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return JobAcceptedResponse.model_validate(decision.response_body)
    try:
        mutation = await coordinator.confirm(
            payload.parse_id,
            payload.model_dump(mode="json", by_alias=True),
            owner_id=owner.id,
            trace_id=correlation_id.get(),
        )
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    assert mutation.job is not None
    response = JobAcceptedResponse(
        job_id=mutation.job.id,
        resource_id=mutation.recipe.id,
        cover_status=mutation.cover_status,
    )
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=202,
        resource_id=mutation.recipe.id,
        job_id=mutation.job.id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.post(
    "/import/merge",
    response_model=JobAcceptedResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def merge_recipe_import(
    payload: ImportMergeRequest,
    coordinator: Annotated[ImportPreviewCoordinator, Depends(import_preview_coordinator)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> JobAcceptedResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="recipe.import.merge",
        payload=payload.model_dump(mode="json", by_alias=True),
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return JobAcceptedResponse.model_validate(decision.response_body)
    try:
        mutation = coordinator.merge(
            payload.recipe_id,
            payload.parse_id,
            payload.model_dump(mode="json", by_alias=True),
            owner_id=owner.id,
            expected_version=payload.expected_version,
            trace_id=correlation_id.get(),
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
async def update_recipe(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    payload: RecipeWriteRequest,
    version: Annotated[int, Depends(expected_version)],
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeDetailResponse:
    repaired = await _maybe_repair_recipe_ingredients(payload)
    recipes.update(
        recipe_id,
        repaired.to_write(),
        expected_version=version,
        trace_id=correlation_id.get(),
        owner_id=owner.id,
    )
    return RecipeDetailResponse.from_read(queries.get(recipe_id))


@router.put("/{recipeId}/photo", response_model=RecipeDetailResponse, response_model_by_alias=True)
async def replace_recipe_photo(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    photo: Annotated[UploadFile, File()],
    version: Annotated[int, Depends(expected_version)],
    photos: Annotated[RecipePhotoService, Depends(recipe_photos)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
    thumbnail_crop: Annotated[str | None, Form(alias="thumbnailCrop")] = None,
) -> RecipeDetailResponse:
    crop = None
    if thumbnail_crop:
        try:
            crop = ThumbnailCropRequest.model_validate_json(thumbnail_crop).to_domain()
        except ValueError as exc:
            raise DomainError("thumbnail_crop_invalid", "Thumbnail crop is invalid.", 422) from exc
    try:
        photos.replace(
            recipe_id,
            content=await photo.read(),
            content_type=photo.content_type or "",
            expected_version=version,
            crop=crop,
        )
    finally:
        await photo.close()
    return RecipeDetailResponse.from_read(queries.get(recipe_id))


@router.get(
    "/{recipeId}/source-images",
    response_model=tuple[RecipeSourceImageResponse, ...],
    response_model_by_alias=True,
)
async def list_recipe_source_images(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    photos: Annotated[RecipePhotoService, Depends(recipe_photos)],
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> tuple[RecipeSourceImageResponse, ...]:
    return tuple(
        RecipeSourceImageResponse(url=value) for value in await photos.source_candidates(recipe_id)
    )


@router.put(
    "/{recipeId}/photo/source",
    response_model=RecipeDetailResponse,
    response_model_by_alias=True,
)
async def replace_recipe_photo_from_source(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    payload: RecipeSourceImageChoiceRequest,
    version: Annotated[int, Depends(expected_version)],
    photos: Annotated[RecipePhotoService, Depends(recipe_photos)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeDetailResponse:
    await photos.replace_from_source(
        recipe_id,
        image_url=str(payload.url),
        expected_version=version,
        crop=payload.thumbnail_crop.to_domain() if payload.thumbnail_crop else None,
    )
    return RecipeDetailResponse.from_read(queries.get(recipe_id))


@router.put(
    "/{recipeId}/photo/attach",
    response_model=RecipeDetailResponse,
    response_model_by_alias=True,
)
async def attach_recipe_photo(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    payload: RecipePhotoAttachRequest,
    version: Annotated[int, Depends(expected_version)],
    photos: Annotated[RecipePhotoService, Depends(recipe_photos)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeDetailResponse:
    await photos.attach_url(
        recipe_id,
        payload.image_source,
        expected_version=version,
        crop=payload.thumbnail_crop.to_domain() if payload.thumbnail_crop else None,
    )
    return RecipeDetailResponse.from_read(queries.get(recipe_id))


@router.delete(
    "/{recipeId}/photo", response_model=RecipeDetailResponse, response_model_by_alias=True
)
def remove_recipe_photo(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    version: Annotated[int, Depends(expected_version)],
    photos: Annotated[RecipePhotoService, Depends(recipe_photos)],
    queries: Annotated[RecipeQueryService, Depends(recipe_queries)],
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeDetailResponse:
    photos.remove(recipe_id, expected_version=version)
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
            remember_match=payload.remember_match,
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


@router.post(
    "/{recipeId}/ingredients/{ingredientId}/owner-food/{ownerFoodId}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def select_owner_food(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    ingredient_id: Annotated[UUID, Path(alias="ingredientId")],
    owner_food_id: Annotated[UUID, Path(alias="ownerFoodId")],
    payload: OwnerFoodSelectionRequest,
    corrections: Annotated[CorrectionService, Depends(correction_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> None:
    del payload  # The selected owner food is already a durable owner-scoped choice.
    corrections.activate_owner_food_match(
        recipe_id=recipe_id,
        ingredient_id=ingredient_id,
        owner_food_id=owner_food_id,
        owner_id=owner.id,
    )


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
