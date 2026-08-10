from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from mcp.server.transport_security import TransportSecuritySettings
from redis import Redis

from vigor_vine.api.problems import install_problem_handlers
from vigor_vine.api.routes import (
    access_tokens,
    auth,
    exports,
    goals,
    grocery,
    health,
    jobs,
    meal_plans,
    media,
    owner,
    recipes,
    suggestions,
)
from vigor_vine.application.access_tokens import AccessTokenService
from vigor_vine.application.auth import AuthService
from vigor_vine.application.corrections import CorrectionService
from vigor_vine.application.exports import ExportJobService
from vigor_vine.application.grocery_lists import GroceryListService
from vigor_vine.application.idempotency import IdempotencyService
from vigor_vine.application.jobs import JobService
from vigor_vine.application.meal_plans import GoalService, MealPlanService
from vigor_vine.application.owner_preferences import OwnerPreferenceService
from vigor_vine.application.recipe_queries import RecipeQueryService
from vigor_vine.application.recipes import RecipeService
from vigor_vine.application.suggestions import SuggestionService
from vigor_vine.infrastructure.config import Settings, get_settings
from vigor_vine.infrastructure.database import create_database_engine, create_session_factory
from vigor_vine.infrastructure.erasure_ledger import ErasureLedger
from vigor_vine.infrastructure.media_store import MediaStore
from vigor_vine.infrastructure.observability import correlation_middleware
from vigor_vine.mcp.read_tools import ReadTools
from vigor_vine.mcp.resources import McpResources
from vigor_vine.mcp.security import (
    McpAuthenticationMiddleware,
    McpSecurity,
    RedisTokenRateLimiter,
)
from vigor_vine.mcp.server import build_mcp_server
from vigor_vine.mcp.write_tools import WriteTools


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    engine = create_database_engine(resolved)
    sessions = create_session_factory(engine)
    redis_client = Redis.from_url(resolved.redis_url, decode_responses=True)
    access_token_service = AccessTokenService(sessions)
    goal_service = GoalService(sessions)
    meal_plan_service = MealPlanService(sessions)
    grocery_list_service = GroceryListService(sessions)
    idempotency_service = IdempotencyService(sessions)
    recipe_query_service = RecipeQueryService(sessions)
    mcp_security = McpSecurity(
        access_token_service,
        RedisTokenRateLimiter(redis_client),
    )
    mcp_server = build_mcp_server(
        ReadTools(goal_service, meal_plan_service, recipe_query_service),
        WriteTools(meal_plan_service, grocery_list_service, idempotency_service),
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
        auth_service = AuthService(sessions)
        auth_service.bootstrap_owner(
            str(resolved.owner_email),
            resolved.owner_bootstrap_password.get_secret_value(),
            "Owner",
        )
        app.state.auth_service = auth_service
        app.state.access_tokens = access_token_service
        app.state.owner_preferences = OwnerPreferenceService(sessions)
        app.state.jobs = JobService(sessions)
        app.state.recipes = RecipeService(
            sessions,
            ErasureLedger(resolved.erasure_ledger_root),
            source_instance_id=resolved.instance_id,
        )
        app.state.recipe_queries = recipe_query_service
        app.state.corrections = CorrectionService(sessions)
        app.state.idempotency = idempotency_service
        app.state.goals = goal_service
        app.state.meal_plans = meal_plan_service
        app.state.grocery_lists = grocery_list_service
        app.state.suggestions = SuggestionService(sessions)
        app.state.sessions = sessions
        media_store = MediaStore(resolved.media_root, resolved.secret_key.get_secret_value())
        app.state.media_store = media_store
        app.state.exports = ExportJobService(sessions, media_store, resolved.export_root)
        try:
            async with mcp_http.router.lifespan_context(mcp_http):
                yield
        finally:
            redis_client.close()
            engine.dispose()

    app = FastAPI(
        title="Vigor & Vine API",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.engine = engine
    app.state.redis = redis_client
    app.middleware("http")(correlation_middleware)
    install_problem_handlers(app)
    versioned = APIRouter(prefix="/api/v1")
    versioned.include_router(health.router)
    versioned.include_router(auth.router)
    versioned.include_router(owner.router)
    versioned.include_router(access_tokens.router)
    versioned.include_router(jobs.router)
    versioned.include_router(recipes.router)
    versioned.include_router(goals.router)
    versioned.include_router(meal_plans.router)
    versioned.include_router(grocery.router)
    versioned.include_router(exports.router)
    versioned.include_router(suggestions.router)
    versioned.include_router(media.router)
    app.include_router(versioned)
    app.mount("/mcp", McpAuthenticationMiddleware(mcp_http, mcp_security), name="mcp")
    return app


app = create_app()
