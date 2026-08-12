from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.auth import ALL_TOKEN_SCOPES, AuthService
from cookfully.application.owner_preferences import OwnerPreferenceService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models import OwnerAccount


def test_bootstrap_session_csrf_expiry_and_logout(session_factory: sessionmaker[Session]) -> None:
    service = AuthService(session_factory, session_ttl=timedelta(hours=1))
    owner = service.bootstrap_owner("Owner@Example.com", "correct horse battery staple", "Owner")
    assert owner.email == "owner@example.com"

    issued = service.login("owner@example.com", "correct horse battery staple")
    assert service.authenticate_session(issued.session_token, issued.csrf_token).id == owner.id
    with pytest.raises(DomainError, match="CSRF"):
        service.authenticate_session(issued.session_token, "wrong")

    service.logout(issued.session_token)
    with pytest.raises(DomainError, match="expired"):
        service.authenticate_session(issued.session_token, issued.csrf_token)


def test_token_is_hashed_scoped_expiring_and_returned_once(
    session_factory: sessionmaker[Session],
) -> None:
    service = AuthService(session_factory)
    owner = service.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    issued = service.create_access_token(owner.id, "Meal planner", {"plans:read"})

    with session_factory() as session:
        stored = session.get(OwnerAccount, owner.id)
        assert stored is not None
        assert stored.access_tokens[0].token_hash != issued.token
    assert service.authenticate_token(issued.token, {"plans:read"}).id == owner.id
    with pytest.raises(DomainError, match="scope"):
        service.authenticate_token(issued.token, {"plans:write"})
    with pytest.raises(DomainError, match="Unknown token scope"):
        service.create_access_token(owner.id, "Bad", {"admin"})
    assert "plans:read" in ALL_TOKEN_SCOPES


def test_owner_timezone_week_start_and_optimistic_version(
    session_factory: sessionmaker[Session],
) -> None:
    auth = AuthService(session_factory)
    owner = auth.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    preferences = OwnerPreferenceService(session_factory)
    updated = preferences.update(
        owner.id, timezone="America/Vancouver", week_starts_on=7, expected_version=1
    )
    assert (updated.timezone, updated.week_starts_on, updated.version) == (
        "America/Vancouver",
        7,
        2,
    )
    with pytest.raises(DomainError, match="changed"):
        preferences.update(owner.id, timezone="UTC", week_starts_on=1, expected_version=1)
    with pytest.raises(DomainError, match="timezone"):
        preferences.update(owner.id, timezone="Mars/Base", week_starts_on=1, expected_version=2)


def test_expired_session_is_rejected(session_factory: sessionmaker[Session]) -> None:
    service = AuthService(session_factory, session_ttl=timedelta(seconds=-1))
    service.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    issued = service.login("owner@example.com", "correct horse battery staple")
    with pytest.raises(DomainError, match="expired"):
        service.authenticate_session(issued.session_token, issued.csrf_token, now=datetime.now(UTC))
