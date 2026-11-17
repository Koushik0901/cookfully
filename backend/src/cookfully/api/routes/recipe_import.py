from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.application import openrouter_settings
from cookfully.domain.common import MAX_VERSION, DomainError
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.recipe_import import RecipeImportSettings

router = APIRouter(prefix="/recipe-import", tags=["Recipe Import"])


class RecipeImportSettingsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cleanup_enabled: bool = Field(alias="cleanupEnabled")
    openrouter_fallback_enabled: bool = Field(alias="openrouterFallbackEnabled")
    local_available: bool = Field(alias="localAvailable")
    openrouter_configured: bool = Field(alias="openrouterConfigured")
    openrouter_model: str | None = Field(alias="openrouterModel")
    version: int = Field(ge=1, le=MAX_VERSION)


class RecipeImportSettingsWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cleanup_enabled: bool = Field(alias="cleanupEnabled")
    openrouter_fallback_enabled: bool = Field(alias="openrouterFallbackEnabled")
    version: int = Field(ge=1, le=MAX_VERSION)


def _get_or_create(request: Request) -> RecipeImportSettings:
    with request.app.state.sessions.begin() as session:
        value = session.get(RecipeImportSettings, 1)
        if value is None:
            value = RecipeImportSettings(id=1)
            session.add(value)
            session.flush()
        session.expunge(value)
        return cast(RecipeImportSettings, value)


def _response(
    value: RecipeImportSettings, settings: Settings, remote: openrouter_settings.OpenRouterConfig
) -> RecipeImportSettingsResponse:
    return RecipeImportSettingsResponse(
        cleanup_enabled=value.cleanup_enabled,
        openrouter_fallback_enabled=value.openrouter_fallback_enabled,
        local_available=settings.intelligence_enabled,
        openrouter_configured=remote.cleanup_configured,
        openrouter_model=remote.cleanup_model or None,
        version=value.version,
    )


@router.get("/settings", response_model=RecipeImportSettingsResponse)
def get_recipe_import_settings(
    request: Request, owner: Annotated[OwnerAccount, Depends(require_browser_owner)]
) -> RecipeImportSettingsResponse:
    del owner
    value = _get_or_create(request)
    with request.app.state.sessions() as session:
        remote = openrouter_settings.load_config(session)
    return _response(value, request.app.state.settings, remote)


@router.put("/settings", response_model=RecipeImportSettingsResponse)
def update_recipe_import_settings(
    payload: RecipeImportSettingsWrite,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeImportSettingsResponse:
    del owner
    with request.app.state.sessions.begin() as session:
        value = session.get(RecipeImportSettings, 1)
        if value is None:
            value = RecipeImportSettings(id=1)
            session.add(value)
            session.flush()
        if value.version != payload.version:
            raise DomainError("recipe_import_settings_stale", "Settings changed elsewhere.", 409)
        value.cleanup_enabled = payload.cleanup_enabled
        value.openrouter_fallback_enabled = payload.openrouter_fallback_enabled
        value.version += 1
        session.flush()
        return _response(
            value, request.app.state.settings, openrouter_settings.load_config(session)
        )
