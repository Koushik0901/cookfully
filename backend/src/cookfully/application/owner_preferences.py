from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import DomainError, require_version
from cookfully.infrastructure.models.identity import OwnerAccount


class OwnerPreferenceService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def update(
        self,
        owner_id: UUID,
        *,
        display_name: str,
        timezone: str,
        week_starts_on: int,
        health_profile: dict[str, Any],
        expected_version: int,
    ) -> OwnerAccount:
        normalized_name = display_name.strip()
        if not normalized_name or len(normalized_name) > 80:
            raise DomainError(
                "invalid_display_name", "Display name must be 1 to 80 characters.", 422
            )
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise DomainError("invalid_timezone", "Select a valid IANA timezone.", 422) from exc
        if not 1 <= week_starts_on <= 7:
            raise DomainError(
                "invalid_week_start", "Week start must be an ISO weekday from 1 to 7.", 422
            )
        with self._session_factory.begin() as session:
            owner = session.get(OwnerAccount, owner_id, with_for_update=True)
            if owner is None:
                raise DomainError("owner_not_found", "Owner account was not found.", 404)
            require_version(expected_version, owner.version)
            owner.display_name = normalized_name
            owner.timezone = timezone
            owner.week_starts_on = week_starts_on
            owner.health_profile = health_profile
            owner.version += 1
            session.flush()
            return owner
