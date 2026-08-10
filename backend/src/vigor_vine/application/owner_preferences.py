from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.domain.common import DomainError, require_version
from vigor_vine.infrastructure.models.identity import OwnerAccount


class OwnerPreferenceService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def update(
        self,
        owner_id: UUID,
        *,
        timezone: str,
        week_starts_on: int,
        expected_version: int,
    ) -> OwnerAccount:
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
            owner.timezone = timezone
            owner.week_starts_on = week_starts_on
            owner.version += 1
            session.flush()
            return owner
