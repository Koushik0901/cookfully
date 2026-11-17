from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.schemas.recipes import Decimal6
from cookfully.application import openrouter_settings as service
from cookfully.application.decisions import FeatureConfig
from cookfully.domain.common import MAX_VERSION, utc_now
from cookfully.domain.decisions import Purpose
from cookfully.infrastructure.decision_store import PostgresDecisionStore
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.openrouter import OpenRouterSettings

router = APIRouter(prefix="/openrouter", tags=["Nutrition Intelligence"])

_MODEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$"


ModelId = Annotated[str, Field(pattern=_MODEL_PATTERN)]


class DecisionFeature(BaseModel):
    """One decision-model feature: whether it runs and which models answer for it."""

    model_config = ConfigDict(extra="forbid")

    purpose: Purpose
    enabled: bool
    models: list[ModelId] = Field(max_length=service.MAX_PANEL_MODELS)

    @model_validator(mode="after")
    def validate_models(self) -> "DecisionFeature":
        if len(set(self.models)) != len(self.models):
            raise ValueError("models must not repeat")
        if self.enabled and not self.models:
            raise ValueError("an enabled feature needs at least one model")
        return self


class OpenRouterSettingsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key_configured: bool = Field(alias="keyConfigured")
    key_hint: str | None = Field(alias="keyHint")
    cleanup_model: str = Field(alias="cleanupModel")
    decision_assist_tolerance_dv: Decimal6 = Field(alias="decisionAssistToleranceDv")
    decision_features: list[DecisionFeature] = Field(alias="decisionFeatures")
    monthly_cap_usd: Decimal6 = Field(alias="monthlyCapUsd")
    spent_this_month_usd: Decimal6 = Field(alias="spentThisMonthUsd")
    version: int = Field(ge=1, le=MAX_VERSION)


class OpenRouterSettingsWrite(BaseModel):
    """``apiKey`` omitted keeps the stored key; ``clearApiKey`` removes it. Write-only."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    api_key: SecretStr | None = Field(default=None, alias="apiKey")
    clear_api_key: bool = Field(default=False, alias="clearApiKey")
    cleanup_model: Annotated[str, Field(pattern=r"^$|" + _MODEL_PATTERN[1:])] = Field(
        alias="cleanupModel"
    )
    decision_assist_tolerance_dv: Decimal6 = Field(
        alias="decisionAssistToleranceDv", gt=0, le=Decimal("0.1")
    )
    decision_features: list[DecisionFeature] = Field(
        default_factory=list, alias="decisionFeatures", max_length=len(Purpose)
    )
    monthly_cap_usd: Decimal6 = Field(alias="monthlyCapUsd", ge=0, le=Decimal(100))
    version: int = Field(ge=1, le=MAX_VERSION)

    @model_validator(mode="after")
    def validate_unique_purposes(self) -> "OpenRouterSettingsWrite":
        purposes = [feature.purpose for feature in self.decision_features]
        if len(set(purposes)) != len(purposes):
            raise ValueError("each feature may appear once")
        return self

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value().strip()
        if not 8 <= len(raw) <= 256 or any(char.isspace() for char in raw) or not raw.isascii():
            raise ValueError("API key must be 8-256 visible ASCII characters")
        return SecretStr(raw)


def _response(row: OpenRouterSettings, spent: Decimal) -> OpenRouterSettingsResponse:
    config = service.resolve(row)
    configured = config.api_key is not None
    return OpenRouterSettingsResponse(
        key_configured=configured,
        key_hint=row.api_key_hint if configured else None,
        cleanup_model=row.cleanup_model,
        decision_assist_tolerance_dv=row.decision_assist_tolerance_dv,
        decision_features=[
            DecisionFeature(
                purpose=purpose,
                enabled=config.features[purpose].enabled,
                models=list(config.features[purpose].models),
            )
            for purpose in Purpose
        ],
        monthly_cap_usd=row.decision_monthly_cap_usd,
        spent_this_month_usd=spent.quantize(Decimal("0.000001")),
        version=row.version,
    )


def _spent_this_month(request: Request) -> Decimal:
    month_start = utc_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return PostgresDecisionStore(request.app.state.sessions).spent_since(month_start)


@router.get("/settings", response_model=OpenRouterSettingsResponse, response_model_by_alias=True)
def get_openrouter_settings(
    request: Request, owner: Annotated[OwnerAccount, Depends(require_browser_owner)]
) -> OpenRouterSettingsResponse:
    del owner
    spent = _spent_this_month(request)
    with request.app.state.sessions.begin() as session:
        return _response(service.get_or_create(session), spent)


@router.put("/settings", response_model=OpenRouterSettingsResponse, response_model_by_alias=True)
def update_openrouter_settings(
    payload: OpenRouterSettingsWrite,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> OpenRouterSettingsResponse:
    del owner
    spent = _spent_this_month(request)
    with request.app.state.sessions.begin() as session:
        row = service.get_or_create(session)
        service.apply_update(
            row,
            version=payload.version,
            api_key=payload.api_key.get_secret_value() if payload.api_key else None,
            clear_api_key=payload.clear_api_key,
            cleanup_model=payload.cleanup_model,
            decision_assist_tolerance_dv=payload.decision_assist_tolerance_dv,
            features={
                feature.purpose: FeatureConfig(feature.enabled, tuple(feature.models))
                for feature in payload.decision_features
            },
            monthly_cap_usd=payload.monthly_cap_usd,
        )
        session.flush()
        return _response(row, spent)
