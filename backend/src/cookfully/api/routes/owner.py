from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.application.owner_preferences import OwnerPreferenceService
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/owner", tags=["Owner"])


class OwnerPreferences(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str = Field(alias="displayName", min_length=1, max_length=80)
    timezone: str
    week_starts_on: int = Field(alias="weekStartsOn", ge=1, le=7)
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
