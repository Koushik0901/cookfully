from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import DomainError, require_version, utc_now
from cookfully.infrastructure.models.identity import OwnerOnboardingState

OnboardingResolution = Literal["completed", "dismissed"]
FirstAction = Literal["manual_recipe", "import_recipe", "view_plan"]


@dataclass(frozen=True, slots=True)
class OnboardingStateRead:
    state: str
    first_action: str | None
    reference_data_choice: str | None
    resolved_at: datetime | None
    version: int


class OwnerOnboardingService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, owner_id: UUID) -> OnboardingStateRead:
        with self._session_factory() as session:
            value = session.get(OwnerOnboardingState, owner_id)
            return self._read(value)

    def resolve(
        self,
        owner_id: UUID,
        *,
        state: OnboardingResolution,
        first_action: FirstAction | None,
        reference_data_choice: str | None = None,
        expected_version: int,
    ) -> OnboardingStateRead:
        with self._session_factory.begin() as session:
            value = session.get(OwnerOnboardingState, owner_id, with_for_update=True)
            if value is None:
                raise DomainError(
                    "onboarding_not_available",
                    "The welcome journey is only available to new kitchens.",
                    409,
                )
            require_version(expected_version, value.version)
            if value.state != "pending":
                raise DomainError(
                    "onboarding_already_resolved",
                    "Your welcome journey is already complete.",
                    409,
                )
            value.state = state
            value.first_action = first_action
            value.reference_data_choice = reference_data_choice
            value.resolved_at = utc_now()
            value.version += 1
            session.flush()
            return self._read(value)

    @staticmethod
    def _read(value: OwnerOnboardingState | None) -> OnboardingStateRead:
        if value is None:
            # Accounts created before onboarding was introduced have no row.
            # Fail closed so an established kitchen never appears brand new.
            return OnboardingStateRead("dismissed", None, None, None, 1)
        return OnboardingStateRead(
            value.state,
            value.first_action,
            value.reference_data_choice,
            value.resolved_at,
            value.version,
        )
