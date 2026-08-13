from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.application.owner_onboarding import OwnerOnboardingService
from cookfully.application.owner_preferences import OwnerPreferenceService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/owner", tags=["Owner"])


class OwnerPreferences(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str = Field(alias="displayName", min_length=1, max_length=80)
    timezone: str
    week_starts_on: int = Field(alias="weekStartsOn", ge=1, le=7)
    version: int = Field(ge=1)


class OwnerOnboarding(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    state: Literal["pending", "completed", "dismissed"]
    first_action: Literal["manual_recipe", "import_recipe", "view_plan"] | None = Field(
        alias="firstAction", default=None
    )
    resolved_at: datetime | None = Field(alias="resolvedAt", default=None)
    version: int = Field(ge=1)


@router.get("/preferences", response_model=OwnerPreferences)
def get_preferences(
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> OwnerPreferences:
    return OwnerPreferences(
        display_name=owner.display_name,
        timezone=owner.timezone,
        week_starts_on=owner.week_starts_on,
        version=owner.version,
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
        expected_version=payload.version,
    )
    return OwnerOnboarding(
        state=value.state,
        first_action=value.first_action,
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
        expected_version=payload.version,
    )
    return OwnerPreferences(
        display_name=updated.display_name,
        timezone=updated.timezone,
        week_starts_on=updated.week_starts_on,
        version=updated.version,
    )
