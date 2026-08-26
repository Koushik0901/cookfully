from __future__ import annotations

from decimal import Decimal
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.schemas.foods import (
    FoodCandidateResponse,
    FoodSearchResponse,
    OwnerFoodResponse,
    OwnerFoodUpdateRequest,
    OwnerFoodWriteRequest,
)
from cookfully.application.food_embedding_index import embedding_storage_key
from cookfully.application.food_match_memories import remembered_food_choice_for_name
from cookfully.application.ingredient_engine import engine
from cookfully.domain.common import DomainError
from cookfully.domain.food_semantics import (
    Compatibility,
    CompatibilityResult,
    compare_compatibility,
    profile_from_text,
)
from cookfully.domain.ingredient_nutrition.matching import FoodMatcher
from cookfully.domain.ingredient_nutrition.normalization import normalize as normalize_food
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings
from cookfully.infrastructure.models.owner_foods import OwnerFood
from cookfully.infrastructure.models.recipes import Ingredient
from cookfully.infrastructure.models.reference_foods import FoodReference, ReferenceDataset
from cookfully.infrastructure.models.semantic_matching import FoodSemanticIndex
from cookfully.infrastructure.repositories.owner_foods import (
    OwnerFoodWrite,
    UserFoodRepository,
)

router = APIRouter(tags=["Foods"])

_SEARCH_CANDIDATE_POOL_LIMIT = 256


def _configured_search_matcher(session: Session) -> FoodMatcher:
    return engine.matcher(
        session,
        fallback=False,
        candidate_pool_limit=_SEARCH_CANDIDATE_POOL_LIMIT,
    )


def warm_search_embedder(session_factory: sessionmaker[Session]) -> None:
    """Load the configured local model before the first interactive search."""

    with session_factory() as session:
        try:
            engine.resolve_embedder(session, fallback=False)
        except DomainError:
            return


def _indexed_candidates(
    session: Session,
    owner_id: UUID,
    query: str,
    *,
    limit: int = 5,
) -> list[FoodCandidateResponse]:
    """Search the durable VectorChord index; return [] until it is populated."""

    settings = session.get(NutritionIntelligenceSettings, 1)
    model_name, model_version = embedding_storage_key(settings)
    embedder = engine.resolve_embedder(session, fallback=False)
    query_vector = list(embedder.embed((query,))[0])
    if len(query_vector) != 384:
        return []
    usda_rows = session.execute(
        select(FoodSemanticIndex, FoodReference)
        .join(FoodReference, FoodReference.id == FoodSemanticIndex.food_reference_id)
        .join(ReferenceDataset, ReferenceDataset.id == FoodReference.dataset_id)
        .where(
            FoodSemanticIndex.active.is_(True),
            FoodSemanticIndex.embedding_vector.is_not(None),
            FoodSemanticIndex.model_name == model_name,
            FoodSemanticIndex.model_version == model_version,
            ReferenceDataset.status == "active",
        )
        .order_by(FoodSemanticIndex.embedding_vector.cosine_distance(query_vector))
        .limit(25)
    ).all()
    owner_rows = session.execute(
        select(FoodSemanticIndex, OwnerFood)
        .join(OwnerFood, OwnerFood.id == FoodSemanticIndex.owner_food_id)
        .where(
            FoodSemanticIndex.active.is_(True),
            FoodSemanticIndex.embedding_vector.is_not(None),
            FoodSemanticIndex.model_name == model_name,
            FoodSemanticIndex.model_version == model_version,
            OwnerFood.owner_id == owner_id,
            OwnerFood.is_active.is_(True),
        )
        .order_by(FoodSemanticIndex.embedding_vector.cosine_distance(query_vector))
        .limit(25)
    ).all()
    query_profile = profile_from_text(query)
    candidates: list[tuple[Decimal, FoodCandidateResponse]] = []
    for row, food in usda_rows:
        compatibility = compare_compatibility(query_profile, profile_from_text(food.description))
        # The ANN ordering is authoritative; the SQL distance is not exposed by
        # the ORM row, so use a deterministic Python dot product for the 25-row
        # rerank set rather than embedding the catalog again.
        similarity = _stored_similarity(row.embedding_vector, query_vector)
        candidates.append((similarity, _candidate_from_usda_index(food, similarity, compatibility)))
    for row, food in owner_rows:
        compatibility = compare_compatibility(query_profile, profile_from_text(food.display_name))
        similarity = _stored_similarity(row.embedding_vector, query_vector)
        candidates.append(
            (similarity, _candidate_from_owner_index(food, similarity, compatibility))
        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [candidate for _, candidate in candidates[:limit]]


def _stored_similarity(vector: list[float] | None, query: list[float]) -> Decimal:
    if not vector or len(vector) != len(query):
        return Decimal("0")
    dot = sum(left * right for left, right in zip(vector, query, strict=True))
    return Decimal(str(max(-1.0, min(1.0, dot))))


def _candidate_from_usda_index(
    food: FoodReference, similarity: Decimal, compatibility: CompatibilityResult
) -> FoodCandidateResponse:
    return FoodCandidateResponse(
        source="usda",
        id=food.id,
        description=food.description,
        brand_owner=food.brand_owner,
        serving_size_g=food.serving_size_g,
        serving_unit=food.serving_unit,
        score=similarity,
        semantic_similarity=similarity,
        compatibility=compatibility.compatibility.value,
        reasons=compatibility.reasons,
    )


def _candidate_from_owner_index(
    food: OwnerFood, similarity: Decimal, compatibility: CompatibilityResult
) -> FoodCandidateResponse:
    return FoodCandidateResponse(
        source="owner",
        id=food.id,
        description=food.display_name,
        brand_owner=food.brand,
        serving_size_g=food.typical_serving_g,
        serving_unit=food.typical_serving_unit,
        score=similarity,
        semantic_similarity=similarity,
        compatibility=compatibility.compatibility.value,
        reasons=compatibility.reasons,
    )


def _open_session(request: Request) -> Session:
    sessions: object = request.app.state.sessions
    return cast(sessionmaker[Session], sessions)()


def _candidate_from_owner(uf: OwnerFood, *, remembered: bool = False) -> FoodCandidateResponse:
    return FoodCandidateResponse(
        source="owner",
        id=uf.id,
        description=uf.display_name,
        brand_owner=uf.brand,
        serving_size_g=uf.typical_serving_g,
        serving_unit=uf.typical_serving_unit,
        remembered=remembered,
    )


def _candidate_from_usda(
    ref: FoodReference, candidate: object | None = None, *, remembered: bool = False
) -> FoodCandidateResponse:
    return FoodCandidateResponse(
        source="usda",
        id=ref.id,
        description=ref.description,
        brand_owner=ref.brand_owner,
        serving_size_g=ref.serving_size_g,
        serving_unit=ref.serving_unit,
        score=getattr(candidate, "score", None),
        semantic_similarity=getattr(candidate, "semantic_similarity", None),
        compatibility=(
            getattr(getattr(candidate, "compatibility", None), "value", None)
            if candidate is not None
            else None
        ),
        reasons=getattr(candidate, "reasons", ()),
        remembered=remembered,
    )


def _remembered_candidate(
    session: Session,
    *,
    owner_id: UUID,
    ingredient: Ingredient,
    query: str,
) -> FoodCandidateResponse | None:
    food_name = ingredient.food_name or ingredient.original_text
    return _remembered_candidate_for_name(session, owner_id, food_name, query=query)


def _remembered_candidate_for_name(
    session: Session,
    owner_id: UUID,
    food_name: str,
    *,
    query: str | None = None,
) -> FoodCandidateResponse | None:
    choice = remembered_food_choice_for_name(
        session,
        owner_id=owner_id,
        food_name=food_name,
        touch=False,
    )
    if choice.food_reference is None and choice.owner_food is None:
        return None
    if choice.food_reference is not None:
        description = choice.food_reference.description
    elif choice.owner_food is not None:
        description = choice.owner_food.display_name
    else:
        return None
    compatibility = compare_compatibility(
        profile_from_text(query or food_name), profile_from_text(description)
    )
    if compatibility.compatibility is Compatibility.CONTRADICTORY:
        return None
    if choice.owner_food is not None:
        return _candidate_from_owner(choice.owner_food, remembered=True)
    assert choice.food_reference is not None
    return _candidate_from_usda(choice.food_reference, remembered=True)


def _prioritize_remembered(
    candidates: list[FoodCandidateResponse],
    remembered: FoodCandidateResponse | None,
    *,
    limit: int = 5,
) -> list[FoodCandidateResponse]:
    if remembered is None:
        return candidates[:limit]
    existing = next(
        (
            candidate
            for candidate in candidates
            if candidate.source == remembered.source and candidate.id == remembered.id
        ),
        None,
    )
    if existing is not None:
        return [remembered if candidate is existing else candidate for candidate in candidates][
            :limit
        ]
    return [remembered, *candidates][:limit]


@router.get(
    "/foods/search",
    response_model=FoodSearchResponse,
    response_model_by_alias=True,
)
def search_foods(
    q: Annotated[str, Query(alias="q", min_length=1, max_length=256)],
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> FoodSearchResponse:
    query = normalize_food(q)
    candidates: list[FoodCandidateResponse] = []

    session = _open_session(request)
    remembered = _remembered_candidate_for_name(session, owner.id, q)
    indexed = _indexed_candidates(session, owner.id, q)
    if indexed:
        session.close()
        return FoodSearchResponse(
            query=q,
            candidates=_prioritize_remembered(indexed, remembered),
        )
    repo = UserFoodRepository(session)
    user_foods = repo.search(owner.id, query, limit=5)
    for uf in user_foods:
        candidates.append(_candidate_from_owner(uf))

    matcher = _configured_search_matcher(session)
    for match in matcher.candidates(q, limit=5):
        candidates.append(_candidate_from_usda(match.food, match))
    session.close()

    return FoodSearchResponse(
        query=q,
        candidates=_prioritize_remembered(candidates, remembered),
    )


@router.get(
    "/foods/user",
    response_model=list[OwnerFoodResponse],
    response_model_by_alias=True,
)
def list_user_foods(
    q: Annotated[str | None, Query(alias="q")] = None,
    request: Request = None,  # type: ignore[assignment]
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)] = None,  # type: ignore[assignment]
) -> list[OwnerFoodResponse]:
    session = _open_session(request)
    repo = UserFoodRepository(session)
    norm = normalize_food(q) if q else ""
    foods = repo.search(owner.id, norm)
    result = [OwnerFoodResponse.from_row(f) for f in foods]
    session.close()
    return result


@router.post(
    "/foods/user",
    response_model=OwnerFoodResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_user_food(
    body: OwnerFoodWriteRequest,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> OwnerFoodResponse:
    write = OwnerFoodWrite(
        display_name=body.display_name,
        normalized_name=normalize_food(body.display_name),
        brand=body.brand,
        calories_kcal=body.calories_kcal,
        protein_g=body.protein_g,
        carbohydrate_g=body.carbohydrate_g,
        fat_g=body.fat_g,
        basis_grams=body.basis_grams,
        typical_serving_g=body.typical_serving_g,
        typical_serving_unit=body.typical_serving_unit,
    )
    session = _open_session(request)
    with session.begin():
        repo = UserFoodRepository(session)
        food = repo.create(owner.id, write)
        result = OwnerFoodResponse.from_row(food)
    session.close()
    return result


@router.put(
    "/foods/user/{foodId}",
    response_model=OwnerFoodResponse,
    response_model_by_alias=True,
)
def update_user_food(
    food_id: Annotated[UUID, Path(alias="foodId")],
    body: OwnerFoodUpdateRequest,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> OwnerFoodResponse:
    write = OwnerFoodWrite(
        display_name=body.display_name,
        normalized_name=normalize_food(body.display_name),
        brand=body.brand,
        calories_kcal=body.calories_kcal,
        protein_g=body.protein_g,
        carbohydrate_g=body.carbohydrate_g,
        fat_g=body.fat_g,
        basis_grams=body.basis_grams,
        typical_serving_g=body.typical_serving_g,
        typical_serving_unit=body.typical_serving_unit,
    )
    session = _open_session(request)
    with session.begin():
        repo = UserFoodRepository(session)
        food = repo.update(owner.id, food_id, write=write, expected_version=body.expected_version)
        result = OwnerFoodResponse.from_row(food)
    session.close()
    return result


@router.delete(
    "/foods/user/{foodId}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user_food(
    food_id: Annotated[UUID, Path(alias="foodId")],
    expected_version: Annotated[int, Query(alias="expectedVersion", ge=1)],
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> None:
    session = _open_session(request)
    with session.begin():
        repo = UserFoodRepository(session)
        repo.deactivate(owner.id, food_id, expected_version=expected_version)
    session.close()


@router.get(
    "/recipes/{recipeId}/ingredients/{ingredientId}/candidates",
    response_model=FoodSearchResponse,
    response_model_by_alias=True,
)
def list_ingredient_candidates(
    recipe_id: Annotated[UUID, Path(alias="recipeId")],
    ingredient_id: Annotated[UUID, Path(alias="ingredientId")],
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    q: Annotated[str | None, Query(alias="q", min_length=1, max_length=256)] = None,
) -> FoodSearchResponse:
    session = _open_session(request)
    ingredient = session.get(Ingredient, ingredient_id)
    if ingredient is None or ingredient.recipe_id != recipe_id:
        session.close()
        raise HTTPException(status_code=404, detail="Ingredient not found on this recipe.")
    food_name = ingredient.food_name or ingredient.original_text or ""
    search_name = q.strip() if q and q.strip() else food_name
    query = normalize_food(search_name)
    candidates: list[FoodCandidateResponse] = []
    remembered = _remembered_candidate(
        session,
        owner_id=owner.id,
        ingredient=ingredient,
        query=search_name,
    )

    indexed = _indexed_candidates(session, owner.id, search_name)
    if indexed:
        session.close()
        return FoodSearchResponse(
            query=search_name,
            candidates=_prioritize_remembered(indexed, remembered),
        )

    repo = UserFoodRepository(session)
    for uf in repo.search(owner.id, query, limit=5):
        candidates.append(_candidate_from_owner(uf))

    matcher = _configured_search_matcher(session)
    for fc in matcher.candidates(search_name, limit=5):
        candidates.append(_candidate_from_usda(fc.food, fc))

    session.close()
    return FoodSearchResponse(
        query=search_name,
        candidates=_prioritize_remembered(candidates, remembered),
    )
