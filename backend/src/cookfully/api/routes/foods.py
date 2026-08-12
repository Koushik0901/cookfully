from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session, sessionmaker

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.schemas.foods import (
    FoodCandidateResponse,
    FoodSearchResponse,
    OwnerFoodResponse,
    OwnerFoodUpdateRequest,
    OwnerFoodWriteRequest,
)
from cookfully.application.food_matching import FoodMatcher, normalize_food
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.owner_foods import OwnerFood
from cookfully.infrastructure.models.reference_foods import FoodReference
from cookfully.infrastructure.repositories.nutrition import NutritionRepository
from cookfully.infrastructure.repositories.owner_foods import (
    OwnerFoodWrite,
    UserFoodRepository,
)

router = APIRouter(tags=["Foods"])


def _open_session(request: Request) -> Session:
    sessions: object = request.app.state.sessions
    return cast(sessionmaker[Session], sessions)()


def _candidate_from_owner(uf: OwnerFood) -> FoodCandidateResponse:
    return FoodCandidateResponse(
        source="owner",
        id=uf.id,
        description=uf.display_name,
        brand_owner=uf.brand,
        serving_size_g=uf.typical_serving_g,
        serving_unit=uf.typical_serving_unit,
    )


def _candidate_from_usda(ref: FoodReference) -> FoodCandidateResponse:
    return FoodCandidateResponse(
        source="usda",
        id=ref.id,
        description=ref.description,
        brand_owner=ref.brand_owner,
        serving_size_g=ref.serving_size_g,
        serving_unit=ref.serving_unit,
    )


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
    repo = UserFoodRepository(session)
    user_foods = repo.search(owner.id, query, limit=10)
    for uf in user_foods:
        candidates.append(_candidate_from_owner(uf))

    nut_repo = NutritionRepository(session)
    usda_foods = nut_repo.search_foods(query, limit=10)
    for ref in usda_foods:
        candidates.append(_candidate_from_usda(ref))
    session.close()

    return FoodSearchResponse(query=q, candidates=candidates)


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
) -> FoodSearchResponse:
    from cookfully.infrastructure.models.recipes import Ingredient

    session = _open_session(request)
    ingredient = session.get(Ingredient, ingredient_id)
    if ingredient is None or ingredient.recipe_id != recipe_id:
        session.close()
        raise HTTPException(status_code=404, detail="Ingredient not found on this recipe.")
    food_name = ingredient.food_name or ingredient.original_text or ""
    query = normalize_food(food_name)
    candidates: list[FoodCandidateResponse] = []

    repo = UserFoodRepository(session)
    for uf in repo.search(owner.id, query, limit=10):
        candidates.append(_candidate_from_owner(uf))

    nut_repo = NutritionRepository(session)
    matcher = FoodMatcher(nut_repo)
    for fc in matcher.candidates(food_name):
        candidates.append(_candidate_from_usda(fc.food))

    session.close()
    return FoodSearchResponse(query=food_name, candidates=candidates)
