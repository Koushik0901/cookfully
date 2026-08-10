from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from vigor_vine.api.dependencies.auth import require_browser_owner
from vigor_vine.application.owner_preferences import OwnerPreferenceService
from vigor_vine.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/owner", tags=["Owner"])


class OwnerPreferences(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    timezone: str
    week_starts_on: int = Field(alias="weekStartsOn", ge=1, le=7)
    version: int = Field(ge=1)


@router.get("/preferences", response_model=OwnerPreferences)
def get_preferences(
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> OwnerPreferences:
    return OwnerPreferences(
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
        timezone=payload.timezone,
        week_starts_on=payload.week_starts_on,
        expected_version=payload.version,
    )
    return OwnerPreferences(
        timezone=updated.timezone,
        week_starts_on=updated.week_starts_on,
        version=updated.version,
    )
