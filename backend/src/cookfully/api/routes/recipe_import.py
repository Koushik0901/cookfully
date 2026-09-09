from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.dependencies.auth import require_browser_owner
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
    version: int = Field(ge=1)


class RecipeImportSettingsWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cleanup_enabled: bool = Field(alias="cleanupEnabled")
    openrouter_fallback_enabled: bool = Field(alias="openrouterFallbackEnabled")
    version: int = Field(ge=1)


def _get_or_create(request: Request) -> RecipeImportSettings:
    with request.app.state.sessions.begin() as session:
        value = session.get(RecipeImportSettings, 1)
        if value is None:
            value = RecipeImportSettings(id=1)
            session.add(value)
            session.flush()
        session.expunge(value)
        return cast(RecipeImportSettings, value)


def _response(value: RecipeImportSettings, settings: Settings) -> RecipeImportSettingsResponse:
    return RecipeImportSettingsResponse(
        cleanup_enabled=value.cleanup_enabled,
        openrouter_fallback_enabled=value.openrouter_fallback_enabled,
        local_available=settings.intelligence_enabled,
        openrouter_configured=bool(
            settings.openrouter_api_key.get_secret_value() and settings.openrouter_model
        ),
        openrouter_model=settings.openrouter_model or None,
        version=value.version,
    )


@router.get("/settings", response_model=RecipeImportSettingsResponse)
def get_recipe_import_settings(
    request: Request, owner: Annotated[OwnerAccount, Depends(require_browser_owner)]
) -> RecipeImportSettingsResponse:
    del owner
    return _response(_get_or_create(request), request.app.state.settings)


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
            from cookfully.domain.common import DomainError

            raise DomainError("recipe_import_settings_stale", "Settings changed elsewhere.", 409)
        value.cleanup_enabled = payload.cleanup_enabled
        value.openrouter_fallback_enabled = payload.openrouter_fallback_enabled
        value.version += 1
        session.flush()
        response = _response(value, request.app.state.settings)
    return response
