from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from mcp.server.transport_security import TransportSecuritySettings
from redis import Redis
from starlette.middleware.gzip import GZipMiddleware

from cookfully.api.problems import install_problem_handlers
from cookfully.api.routes import (
    access_tokens,
    auth,
    exports,
    foods,
    goals,
    grocery,
    health,
    intelligence,
    jobs,
    meal_plans,
    media,
    nutrition_intelligence,
    owner,
    pantry,
    recipes,
    reference_data,
    suggestions,
)
from cookfully.application.access_tokens import AccessTokenService
from cookfully.application.auth import AuthService
from cookfully.application.corrections import CorrectionService
from cookfully.application.exports import ExportJobService
from cookfully.application.grocery_lists import GroceryListService
from cookfully.application.grocery_shopping_stops import GroceryShoppingStopService
from cookfully.application.idempotency import IdempotencyService
from cookfully.application.import_preview import ImportPreviewCoordinator
from cookfully.application.intelligence_drafts import IntelligenceDraftService
from cookfully.application.jobs import JobService
from cookfully.application.meal_plans import GoalService, MealPlanService
from cookfully.application.nutrition_intelligence import NutritionIntelligenceService
from cookfully.application.owner_onboarding import OwnerOnboardingService
from cookfully.application.owner_preferences import OwnerPreferenceService
from cookfully.application.pantry import PantryService
from cookfully.application.pantry_deductions import PantryDeductionService
from cookfully.application.pantry_search import PantrySearchService
from cookfully.application.recipe_organization import RecipeOrganizationService
from cookfully.application.recipe_photos import RecipePhotoService
from cookfully.application.recipe_queries import RecipeQueryService
from cookfully.application.recipes import RecipeService
from cookfully.application.reference_data import ReferenceDataInstallService
from cookfully.application.suggestions import SuggestionService
from cookfully.infrastructure.config import Settings, get_settings
from cookfully.infrastructure.database import create_database_engine, create_session_factory
from cookfully.infrastructure.erasure_ledger import ErasureLedger
from cookfully.infrastructure.instance_lease import runtime_service_lease
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.observability import correlation_middleware
from cookfully.infrastructure.recipe_images import RecipeImageService
from cookfully.infrastructure.recipe_importer import RecipeImporter
from cookfully.infrastructure.safe_fetch import SafeFetcher
from cookfully.intelligence.client import IntelligenceClient
from cookfully.mcp.read_tools import ReadTools
from cookfully.mcp.resources import McpResources
from cookfully.mcp.security import (
    McpAuthenticationMiddleware,
    McpSecurity,
    RedisTokenRateLimiter,
)
from cookfully.mcp.server import build_mcp_server
from cookfully.mcp.write_tools import WriteTools

# Operation IDs are a public compatibility surface used by generated clients. Keep this
# endpoint-name mapping aligned with contracts/openapi.yaml; the contract drift test enforces it.
_OPERATION_IDS = {
    "health": "getHealth",
    "create_session": "createSession",
    "delete_session": "deleteSession",
    "get_preferences": "getOwnerPreferences",
    "update_preferences": "putOwnerPreferences",
    "get_onboarding": "getOwnerOnboarding",
    "resolve_onboarding": "putOwnerOnboarding",
    "get_current_job": "getCurrentJob",
    "get_job": "getJob",
    "get_food_embedding_summary": "getFoodEmbeddingSummary",
    "run_food_embeddings": "runFoodEmbeddingIndex",
    "list_recipes": "listRecipes",
    "list_recipe_collections": "listRecipeCollections",
    "create_recipe_collection": "createRecipeCollection",
    "update_recipe_collection": "updateRecipeCollection",
    "delete_recipe_collection": "deleteRecipeCollection",
    "replace_recipe_organization": "replaceRecipeOrganization",
    "create_recipe": "createRecipe",
    "bulk_archive_recipes": "bulkArchiveRecipes",
    "import_recipe": "importRecipe",
    "preview_recipe_import": "previewRecipeImport",
    "confirm_recipe_import": "confirmRecipeImport",
    "get_recipe": "getRecipe",
    "update_recipe": "updateRecipe",
    "replace_recipe_photo": "replaceRecipePhoto",
    "remove_recipe_photo": "removeRecipePhoto",
    "list_recipe_source_images": "listRecipeSourceImages",
    "replace_recipe_photo_from_source": "replaceRecipePhotoFromSource",
    "attach_recipe_photo": "attachRecipePhoto",
    "merge_recipe_import": "mergeRecipeImport",
    "archive_recipe": "archiveRecipe",
    "restore_recipe": "restoreRecipe",
    "permanently_delete_recipe": "permanentlyDeleteRecipe",
    "recalculate_recipe_nutrition": "recalculateRecipeNutrition",
    "create_nutrition_correction": "createNutritionCorrection",
    "reset_nutrition_correction": "resetNutritionCorrection",
    "get_current_goal": "getCurrentGoal",
    "put_current_goal": "putCurrentGoal",
    "get_meal_plan": "getMealPlan",
    "add_meal_plan_entry": "addMealPlanEntry",
    "update_meal_plan_entry": "updateMealPlanEntry",
    "swap_meal_plan_entries": "swapMealPlanEntries",
    "delete_meal_plan_entry": "deleteMealPlanEntry",
    "get_grocery_list": "getGroceryList",
    "regenerate_grocery_list": "regenerateGroceryList",
    "create_grocery_item": "createGroceryItem",
    "update_grocery_item": "updateGroceryItem",
    "delete_grocery_item": "deleteGroceryItem",
    "list_shopping_stops": "listGroceryShoppingStops",
    "create_shopping_stop": "createGroceryShoppingStop",
    "update_shopping_stop": "updateGroceryShoppingStop",
    "delete_shopping_stop": "deleteGroceryShoppingStop",
    "complete_grocery_list": "completeGroceryList",
    "reopen_grocery_list": "reopenGroceryList",
    "apply_pantry_deductions": "applyPantryDeductions",
    "reverse_pantry_deduction": "reversePantryDeduction",
    "list_pantry_items": "listPantryItems",
    "create_pantry_item": "createPantryItem",
    "update_pantry_item": "updatePantryItem",
    "delete_pantry_item": "deletePantryItem",
    "find_makeable_recipes": "findMakeableRecipes",
    "create_portable_export": "createPortableExport",
    "download_portable_export": "downloadPortableExport",
    "create_suggestion": "createSuggestion",
    "get_suggestion": "getSuggestion",
    "accept_suggestion": "acceptSuggestion",
    "get_recipe_media": "getRecipeMedia",
    "get_settings": "getNutritionIntelligenceSettings",
    "estimate": "estimateNutritionIntelligence",
    "update_settings": "updateNutritionIntelligenceSettings",
    "infer_intelligence": "inferIntelligence",
    "create_draft": "createIntelligenceDraft",
    "get_draft": "getIntelligenceDraft",
    "execute_draft": "executeIntelligenceDraft",
    "create_extraction_job": "createIntelligenceExtractionJob",
}


def _contract_operation_id(route: APIRoute) -> str:
    return _OPERATION_IDS.get(route.name, route.name)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    engine = create_database_engine(resolved)
    sessions = create_session_factory(engine)
    redis_client = Redis.from_url(resolved.redis_url, decode_responses=True)
    intelligence_client = IntelligenceClient(
        str(resolved.intelligence_url),
        resolved.intelligence_service_key.get_secret_value(),
        enabled=resolved.intelligence_enabled,
        timeout_seconds=resolved.intelligence_timeout_seconds,
    )
    access_token_service = AccessTokenService(sessions)
    goal_service = GoalService(sessions)
    meal_plan_service = MealPlanService(sessions)
    grocery_list_service = GroceryListService(sessions)
    idempotency_service = IdempotencyService(sessions)
    recipe_query_service = RecipeQueryService(sessions)
    suggestion_service = SuggestionService(sessions)
    job_service = JobService(sessions)
    pantry_service = PantryService(sessions, job_service)
    mcp_security = McpSecurity(
        access_token_service,
        RedisTokenRateLimiter(redis_client),
    )
    mcp_server = build_mcp_server(
        ReadTools(
            goal_service,
            meal_plan_service,
            recipe_query_service,
            suggestion_service,
            pantry_service,
        ),
        WriteTools(
            meal_plan_service,
            grocery_list_service,
            idempotency_service,
            suggestion_service,
            pantry_service,
        ),
        McpResources(),
        mcp_security,
    )
    mcp_http = mcp_server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[
                str(resolved.api_base_url.host),
                f"{resolved.api_base_url.host}:*",
                *(["testserver"] if resolved.environment == "test" else []),
            ],
            allowed_origins=[str(resolved.public_base_url).rstrip("/")],
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with runtime_service_lease(engine, resolved.erasure_ledger_root):
            auth_service = AuthService(
                sessions, session_ttl=timedelta(days=resolved.session_ttl_days)
            )
            auth_service.bootstrap_owner(
                str(resolved.owner_email),
                resolved.owner_bootstrap_password.get_secret_value(),
                "Owner",
            )
            app.state.auth_service = auth_service
            app.state.access_tokens = access_token_service
            app.state.owner_preferences = OwnerPreferenceService(sessions)
            app.state.owner_onboarding = OwnerOnboardingService(sessions)
            app.state.jobs = job_service
            media_store = MediaStore(resolved.media_root, resolved.secret_key.get_secret_value())
            app.state.media_store = media_store
            app.state.recipes = RecipeService(
                sessions,
                ErasureLedger(resolved.erasure_ledger_root),
                source_instance_id=resolved.instance_id,
            )
            app.state.recipe_photos = RecipePhotoService(
                sessions,
                RecipeImageService(SafeFetcher(max_bytes=20 * 1024 * 1024), media_store),
                media_store,
                SafeFetcher(max_bytes=3 * 1024 * 1024),
            )
            app.state.recipe_organization = RecipeOrganizationService(sessions)
            app.state.recipe_queries = recipe_query_service
            app.state.import_previews = ImportPreviewCoordinator(
                sessions,
                RecipeImporter(SafeFetcher(max_bytes=25 * 1024 * 1024), media_store),
                app.state.recipes,
                recipe_query_service,
                photos=app.state.recipe_photos,
            )
            app.state.corrections = CorrectionService(sessions, jobs=job_service)
            app.state.idempotency = idempotency_service
            app.state.goals = goal_service
            app.state.meal_plans = meal_plan_service
            app.state.grocery_lists = grocery_list_service
            app.state.grocery_shopping_stops = GroceryShoppingStopService(sessions)
            app.state.pantry = pantry_service
            app.state.pantry_search = PantrySearchService(sessions)
            app.state.pantry_deductions = PantryDeductionService(sessions)
            app.state.suggestions = SuggestionService(sessions)
            app.state.sessions = sessions
            # Warm the configured local embedding model during startup so the
            # first user search does not pay model-initialization latency.
            foods.warm_search_embedder(sessions)
            app.state.exports = ExportJobService(sessions, media_store, resolved.export_root)
            app.state.reference_data = ReferenceDataInstallService(sessions)
            app.state.nutrition_intelligence = NutritionIntelligenceService(sessions)
            app.state.intelligence = intelligence_client
            app.state.intelligence_enabled = resolved.intelligence_enabled
            app.state.intelligence_drafts = IntelligenceDraftService(sessions)
            try:
                async with mcp_http.router.lifespan_context(mcp_http):
                    yield
            finally:
                redis_client.close()
                intelligence_client.close()
                engine.dispose()

    app = FastAPI(
        title="Cookfully API",
        version="0.2.0",
        description=(
            "Canonical API for recipes, honest nutrition estimates, goals, meal plans, "
            "grocery lists, exports, agent access, and goal-aware suggestions. Public decimal "
            "values are canonical strings. Estimated nutrition and suggestion projections are "
            "planning aids, not medical advice."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.engine = engine
    app.state.redis = redis_client
    # Recipe, pantry, and plan payloads are often large enough that response
    # compression improves real-world latency without affecting small health
    # or mutation responses.
    app.add_middleware(GZipMiddleware, minimum_size=1_000, compresslevel=5)
    app.middleware("http")(correlation_middleware)
    install_problem_handlers(app)
    versioned = APIRouter(
        prefix="/api/v1",
        generate_unique_id_function=_contract_operation_id,
    )
    versioned.include_router(health.router)
    versioned.include_router(auth.router)
    versioned.include_router(owner.router)
    versioned.include_router(access_tokens.router)
    versioned.include_router(jobs.router)
    versioned.include_router(recipes.router)
    versioned.include_router(goals.router)
    versioned.include_router(meal_plans.router)
    versioned.include_router(grocery.router)
    versioned.include_router(pantry.router)
    versioned.include_router(exports.router)
    versioned.include_router(suggestions.router)
    versioned.include_router(media.router)
    versioned.include_router(foods.router)
    versioned.include_router(reference_data.router)
    versioned.include_router(nutrition_intelligence.router)
    versioned.include_router(intelligence.router)
    app.include_router(versioned)
    app.mount("/mcp", McpAuthenticationMiddleware(mcp_http, mcp_security), name="mcp")
    return app


app = create_app()
