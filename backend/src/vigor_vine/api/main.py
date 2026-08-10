from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from redis import Redis

from vigor_vine.api.problems import install_problem_handlers
from vigor_vine.api.routes import auth, health, jobs, owner
from vigor_vine.application.auth import AuthService
from vigor_vine.application.jobs import JobService
from vigor_vine.application.owner_preferences import OwnerPreferenceService
from vigor_vine.infrastructure.config import Settings, get_settings
from vigor_vine.infrastructure.database import create_database_engine, create_session_factory
from vigor_vine.infrastructure.observability import correlation_middleware


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    engine = create_database_engine(resolved)
    sessions = create_session_factory(engine)
    redis_client = Redis.from_url(resolved.redis_url, decode_responses=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        auth_service = AuthService(sessions)
        auth_service.bootstrap_owner(
            str(resolved.owner_email),
            resolved.owner_bootstrap_password.get_secret_value(),
            "Owner",
        )
        app.state.auth_service = auth_service
        app.state.owner_preferences = OwnerPreferenceService(sessions)
        app.state.jobs = JobService(sessions)
        yield
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
    versioned.include_router(jobs.router)
    app.include_router(versioned)
    return app


app = create_app()
