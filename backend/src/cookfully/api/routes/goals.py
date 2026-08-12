import re
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request

from cookfully.api.dependencies.auth import require_browser_owner, require_scopes
from cookfully.api.schemas.plans import UserGoalResponse, UserGoalWriteRequest
from cookfully.application.meal_plans import GoalService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/goals", tags=["Goals"])


def optional_version(
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> int | None:
    if if_match is None:
        return None
    match = re.fullmatch(r'"([1-9][0-9]*)"', if_match)
    if match is None:
        raise DomainError("if_match_invalid", "If-Match must contain a quoted version.", 422)
    return int(match.group(1))


def goal_service(request: Request) -> GoalService:
    service: GoalService = request.app.state.goals
    return service


@router.get("/current", response_model=UserGoalResponse, response_model_by_alias=True)
def get_current_goal(
    service: Annotated[GoalService, Depends(goal_service)],
    owner: Annotated[OwnerAccount, Depends(require_scopes("goals:read"))],
    on_date: Annotated[date | None, Query(alias="onDate")] = None,
) -> UserGoalResponse:
    return UserGoalResponse.from_read(service.get(owner.id, on_date or datetime.now(UTC).date()))


@router.put("/current", response_model=UserGoalResponse, response_model_by_alias=True)
def put_current_goal(
    payload: UserGoalWriteRequest,
    service: Annotated[GoalService, Depends(goal_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    version: Annotated[int | None, Depends(optional_version)],
) -> UserGoalResponse:
    return UserGoalResponse.from_read(
        service.put(owner.id, payload.to_write(), expected_version=version)
    )
