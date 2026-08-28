from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.auth import AuthService
from cookfully.application.owner_onboarding import OwnerOnboardingService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerOnboardingState


def test_owner_onboarding_persists_terminal_choice_and_rejects_replay(
    session_factory: sessionmaker[Session],
) -> None:
    owner = AuthService(session_factory).bootstrap_owner(
        "owner@example.com", "correct horse battery staple", "Owner"
    )
    service = OwnerOnboardingService(session_factory)

    resolved = service.resolve(
        owner.id,
        state="completed",
        first_action="manual_recipe",
        expected_version=1,
    )
    assert resolved.state == "completed"
    assert resolved.first_action == "manual_recipe"
    assert resolved.version == 2
    with session_factory() as session:
        stored = session.scalar(
            select(OwnerOnboardingState).where(OwnerOnboardingState.owner_id == owner.id)
        )
        assert stored is not None and stored.state == "completed"

    with pytest.raises(DomainError, match="already complete"):
        service.resolve(
            owner.id,
            state="dismissed",
            first_action=None,
            expected_version=2,
        )


def test_legacy_owner_without_onboarding_state_is_not_blocked(
    session_factory: sessionmaker[Session],
) -> None:
    owner = AuthService(session_factory).bootstrap_owner(
        "owner@example.com", "correct horse battery staple", "Owner"
    )
    with session_factory.begin() as session:
        state = session.get(OwnerOnboardingState, owner.id)
        assert state is not None
        session.delete(state)

    service = OwnerOnboardingService(session_factory)
    assert service.get(owner.id).state == "dismissed"
    with pytest.raises(DomainError, match="only available to new kitchens"):
        service.resolve(
            owner.id,
            state="completed",
            first_action="manual_recipe",
            expected_version=1,
        )
