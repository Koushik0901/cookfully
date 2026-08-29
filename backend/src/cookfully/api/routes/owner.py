from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.schemas.grocery import GroceryListResponse
from cookfully.api.schemas.pantry import PantryItemResponse, PantryRecipeMatchResponse
from cookfully.api.schemas.plans import MealPlanResponse
from cookfully.api.schemas.recipes import RecipePageResponse
from cookfully.application.grocery_lists import GroceryListService
from cookfully.application.meal_plans import MealPlanService
from cookfully.application.owner_onboarding import OwnerOnboardingService
from cookfully.application.owner_preferences import OwnerPreferenceService
from cookfully.application.pantry import PantryService
from cookfully.application.pantry_search import PantrySearchService
from cookfully.application.recipe_queries import RecipeQueryService
from cookfully.domain.common import DomainError, utc_now
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/owner", tags=["Owner"])


class HealthProfile(BaseModel):
    """Optional planning context, never a medical recommendation or prescription."""

    model_config = ConfigDict(populate_by_name=True)

    age_years: int | None = Field(alias="ageYears", default=None, ge=13, le=130)
    height_cm: float | None = Field(alias="heightCm", default=None, ge=80, le=260)
    current_weight_kg: float | None = Field(alias="currentWeightKg", default=None, ge=20, le=500)
    target_weight_kg: float | None = Field(alias="targetWeightKg", default=None, ge=20, le=500)
    dietary_pattern: Literal[
        "no_preference",
        "vegetarian",
        "vegan",
        "pescatarian",
        "halal",
        "kosher",
        "gluten_free",
        "low_sodium",
    ] = Field(alias="dietaryPattern", default="no_preference")
    avoid_ingredients: tuple[str, ...] = Field(alias="avoidIngredients", default=(), max_length=24)

    @staticmethod
    def _clean_avoid(values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(item.strip() for item in values if item.strip())

    @property
    def normalized_avoid_ingredients(self) -> tuple[str, ...]:
        values = self._clean_avoid(self.avoid_ingredients)
        if any(len(item) > 80 for item in values):
            raise DomainError(
                "avoid_ingredient_too_long",
                "Avoided ingredients must be 80 characters or fewer.",
                422,
            )
        if len(values) > 24:
            raise DomainError(
                "too_many_avoided_ingredients", "Choose up to 24 avoided ingredients.", 422
            )
        return values


class OwnerPreferences(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str = Field(alias="displayName", min_length=1, max_length=80)
    timezone: str
    week_starts_on: int = Field(alias="weekStartsOn", ge=1, le=7)
    health_profile: HealthProfile = Field(alias="healthProfile", default_factory=HealthProfile)
    version: int = Field(ge=1)


def _preferences(owner: OwnerAccount) -> OwnerPreferences:
    profile = HealthProfile.model_validate(owner.health_profile or {})
    # Access the normalized variant once so malformed historical JSON cannot
    # escape through the API after a migration or manual database edit.
    avoided = profile.normalized_avoid_ingredients
    return OwnerPreferences(
        display_name=owner.display_name,
        timezone=owner.timezone,
        week_starts_on=owner.week_starts_on,
        health_profile=profile.model_copy(update={"avoid_ingredients": avoided}),
        version=owner.version,
    )


class OwnerOnboarding(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    state: Literal["pending", "completed", "dismissed"]
    first_action: Literal["manual_recipe", "import_recipe", "view_plan"] | None = Field(
        alias="firstAction", default=None
    )
    reference_data_choice: Literal["both", "foundation_sr_legacy", "none"] | None = Field(
        alias="referenceDataChoice", default=None
    )
    resolved_at: datetime | None = Field(alias="resolvedAt", default=None)
    version: int = Field(ge=1)


class HomeBootstrap(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    preferences: OwnerPreferences
    recipes: RecipePageResponse
    pantry: tuple[PantryItemResponse, ...]
    plan: MealPlanResponse | None = None
    grocery: GroceryListResponse | None = None
    pantry_matches: tuple[PantryRecipeMatchResponse, ...] = Field(alias="pantryMatches")


def _current_week_start(owner: OwnerAccount) -> date:
    local_today = utc_now().astimezone(ZoneInfo(owner.timezone)).date()
    return local_today.fromordinal(
        local_today.toordinal() - ((local_today.isoweekday() - owner.week_starts_on) % 7)
    )


@router.get("/preferences", response_model=OwnerPreferences)
def get_preferences(
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> OwnerPreferences:
    return _preferences(owner)


@router.get("/home", response_model=HomeBootstrap, response_model_by_alias=True)
def get_home_bootstrap(
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> HomeBootstrap:
    """One bounded projection for Home, instead of a browser request fan-out."""

    recipes: RecipeQueryService = request.app.state.recipe_queries
    pantry: PantryService = request.app.state.pantry
    pantry_search: PantrySearchService = request.app.state.pantry_search
    meal_plans: MealPlanService = request.app.state.meal_plans
    groceries: GroceryListService = request.app.state.grocery_lists
    week_start = _current_week_start(owner)
    recipe_page = recipes.list(
        query=None,
        nutrition_state=None,
        include_archived=True,
        cursor=None,
        limit=12,
    )
    pantry_items = pantry.list(owner.id)
    try:
        plan = MealPlanResponse.from_read(meal_plans.get(owner.id, week_start))
    except DomainError as error:
        if error.status != 404:
            raise
        plan = None
    try:
        grocery = GroceryListResponse.from_read(groceries.get(owner.id, week_start))
    except DomainError as error:
        if error.status != 404:
            raise
        grocery = None
    recipe_ids = {item.id for item in recipe_page.items}
    matches = (
        tuple(item for item in pantry_search.search(owner.id) if item.recipe_id in recipe_ids)
        if pantry_items and recipe_ids
        else ()
    )
    return HomeBootstrap(
        preferences=_preferences(owner),
        recipes=RecipePageResponse.from_read(recipe_page),
        pantry=tuple(PantryItemResponse.from_read(item) for item in pantry_items),
        plan=plan,
        grocery=grocery,
        pantry_matches=tuple(PantryRecipeMatchResponse.from_score(item) for item in matches),
    )


@router.get("/onboarding", response_model=OwnerOnboarding, response_model_by_alias=True)
def get_onboarding(
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> OwnerOnboarding:
    service: OwnerOnboardingService = request.app.state.owner_onboarding
    value = service.get(owner.id)
    return OwnerOnboarding(
        state=value.state,
        first_action=value.first_action,
        reference_data_choice=value.reference_data_choice,
        resolved_at=value.resolved_at,
        version=value.version,
    )


@router.put("/onboarding", response_model=OwnerOnboarding, response_model_by_alias=True)
def resolve_onboarding(
    payload: OwnerOnboarding,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> OwnerOnboarding:
    if payload.state == "pending":
        raise DomainError(
            "onboarding_resolution_required",
            "Onboarding may only be completed or dismissed.",
            422,
        )
    service: OwnerOnboardingService = request.app.state.owner_onboarding
    value = service.resolve(
        owner.id,
        state=payload.state,
        first_action=payload.first_action,
        reference_data_choice=payload.reference_data_choice,
        expected_version=payload.version,
    )
    return OwnerOnboarding(
        state=value.state,
        first_action=value.first_action,
        reference_data_choice=value.reference_data_choice,
        resolved_at=value.resolved_at,
        version=value.version,
    )


@router.put("/preferences", response_model=OwnerPreferences)
def update_preferences(
    payload: OwnerPreferences,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> OwnerPreferences:
    service: OwnerPreferenceService = request.app.state.owner_preferences
    updated = service.update(
        owner.id,
        display_name=payload.display_name,
        timezone=payload.timezone,
        week_starts_on=payload.week_starts_on,
        health_profile=payload.health_profile.model_copy(
            update={"avoid_ingredients": payload.health_profile.normalized_avoid_ingredients}
        ).model_dump(mode="json", by_alias=True),
        expected_version=payload.version,
    )
    return _preferences(updated)
