from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.schemas.recipes import Decimal6
from cookfully.application import openrouter_settings as service
from cookfully.domain.common import MAX_VERSION
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.openrouter import OpenRouterSettings

router = APIRouter(prefix="/openrouter", tags=["Nutrition Intelligence"])

_MODEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$"


class OpenRouterSettingsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key_configured: bool = Field(alias="keyConfigured")
    key_hint: str | None = Field(alias="keyHint")
    cleanup_model: str = Field(alias="cleanupModel")
    decision_assist_enabled: bool = Field(alias="decisionAssistEnabled")
    decision_assist_model: str = Field(alias="decisionAssistModel")
    decision_assist_tolerance_dv: Decimal6 = Field(alias="decisionAssistToleranceDv")
    version: int = Field(ge=1, le=MAX_VERSION)


class OpenRouterSettingsWrite(BaseModel):
    """``apiKey`` omitted keeps the stored key; ``clearApiKey`` removes it. Write-only."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    api_key: SecretStr | None = Field(default=None, alias="apiKey")
    clear_api_key: bool = Field(default=False, alias="clearApiKey")
    cleanup_model: Annotated[str, Field(pattern=r"^$|" + _MODEL_PATTERN[1:])] = Field(
        alias="cleanupModel"
    )
    decision_assist_enabled: bool = Field(alias="decisionAssistEnabled")
    decision_assist_model: Annotated[str, Field(pattern=_MODEL_PATTERN)] = Field(
        alias="decisionAssistModel"
    )
    decision_assist_tolerance_dv: Decimal6 = Field(
        alias="decisionAssistToleranceDv", gt=0, le=Decimal("0.1")
    )
    version: int = Field(ge=1, le=MAX_VERSION)

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value().strip()
        if not 8 <= len(raw) <= 256 or any(char.isspace() for char in raw) or not raw.isascii():
            raise ValueError("API key must be 8-256 visible ASCII characters")
        return SecretStr(raw)


def _response(row: OpenRouterSettings) -> OpenRouterSettingsResponse:
    configured = service.resolve(row).api_key is not None
    return OpenRouterSettingsResponse(
        key_configured=configured,
        key_hint=row.api_key_hint if configured else None,
        cleanup_model=row.cleanup_model,
        decision_assist_enabled=row.decision_assist_enabled,
        decision_assist_model=row.decision_assist_model,
        decision_assist_tolerance_dv=row.decision_assist_tolerance_dv,
        version=row.version,
    )


@router.get("/settings", response_model=OpenRouterSettingsResponse, response_model_by_alias=True)
def get_openrouter_settings(
    request: Request, owner: Annotated[OwnerAccount, Depends(require_browser_owner)]
) -> OpenRouterSettingsResponse:
    del owner
    with request.app.state.sessions.begin() as session:
        return _response(service.get_or_create(session))


@router.put("/settings", response_model=OpenRouterSettingsResponse, response_model_by_alias=True)
def update_openrouter_settings(
    payload: OpenRouterSettingsWrite,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> OpenRouterSettingsResponse:
    del owner
    with request.app.state.sessions.begin() as session:
        row = service.get_or_create(session)
        service.apply_update(
            row,
            version=payload.version,
            api_key=payload.api_key.get_secret_value() if payload.api_key else None,
            clear_api_key=payload.clear_api_key,
            cleanup_model=payload.cleanup_model,
            decision_assist_enabled=payload.decision_assist_enabled,
            decision_assist_model=payload.decision_assist_model,
            decision_assist_tolerance_dv=payload.decision_assist_tolerance_dv,
        )
        session.flush()
        return _response(row)
