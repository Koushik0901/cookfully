from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.access_tokens import token_hash
from cookfully.application.auth import ALL_TOKEN_SCOPES, AuthService
from cookfully.application.owner_preferences import OwnerPreferenceService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models import OwnerAccount, SessionRecord


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
        owner.id,
        display_name="Owner",
        timezone="America/Vancouver",
        week_starts_on=7,
        expected_version=1,
    )
    assert (updated.timezone, updated.week_starts_on, updated.version) == (
        "America/Vancouver",
        7,
        2,
    )
    with pytest.raises(DomainError, match="changed"):
        preferences.update(
            owner.id, display_name="Owner", timezone="UTC", week_starts_on=1, expected_version=1
        )
    with pytest.raises(DomainError, match="timezone"):
        preferences.update(
            owner.id,
            display_name="Owner",
            timezone="Mars/Base",
            week_starts_on=1,
            expected_version=2,
        )


def test_expired_session_is_rejected(session_factory: sessionmaker[Session]) -> None:
    service = AuthService(session_factory, session_ttl=timedelta(seconds=-1))
    service.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    issued = service.login("owner@example.com", "correct horse battery staple")
    with pytest.raises(DomainError, match="expired"):
        service.authenticate_session(issued.session_token, issued.csrf_token, now=datetime.now(UTC))


def test_login_honors_configured_session_ttl(session_factory: sessionmaker[Session]) -> None:
    service = AuthService(session_factory, session_ttl=timedelta(days=400))
    owner = service.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    service.login(
        "owner@example.com",
        "correct horse battery staple",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    )
    with session_factory() as session:
        record = session.scalar(select(SessionRecord).where(SessionRecord.owner_id == owner.id))
        assert record is not None
        assert record.expires_at - record.created_at == timedelta(days=400)
        assert record.client_label == "Chrome on Windows"


def test_session_lifetime_is_fixed_at_issuance(session_factory: sessionmaker[Session]) -> None:
    short = AuthService(session_factory, session_ttl=timedelta(hours=1))
    short.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    issued = short.login("owner@example.com", "correct horse battery staple")
    long = AuthService(session_factory, session_ttl=timedelta(days=400))
    with pytest.raises(DomainError, match="expired"):
        long.authenticate_session(
            issued.session_token, issued.csrf_token, now=datetime.now(UTC) + timedelta(hours=2)
        )


def test_list_sessions_flags_current(session_factory: sessionmaker[Session]) -> None:
    service = AuthService(session_factory)
    owner = service.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    service.login("owner@example.com", "correct horse battery staple", client_label="Device A")
    second = service.login(
        "owner@example.com", "correct horse battery staple", client_label="Device B"
    )
    sessions = service.list_sessions(owner.id, token_hash(second.session_token))
    assert len(sessions) == 2
    assert sum(1 for item in sessions if item.is_current) == 1
    assert next(item for item in sessions if item.is_current).client_label == "Device B"


def test_revoke_session_invalidates_other(session_factory: sessionmaker[Session]) -> None:
    service = AuthService(session_factory)
    owner = service.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    first = service.login(
        "owner@example.com", "correct horse battery staple", client_label="Device A"
    )
    second = service.login(
        "owner@example.com", "correct horse battery staple", client_label="Device B"
    )
    sessions = service.list_sessions(owner.id, token_hash(second.session_token))
    current_id = next(item for item in sessions if item.is_current).id
    other = next(item for item in sessions if not item.is_current)
    service.revoke_session(owner.id, other.id)
    remaining = service.list_sessions(owner.id, token_hash(second.session_token))
    assert [item.id for item in remaining] == [current_id]
    with pytest.raises(DomainError, match="expired"):
        service.authenticate_session(first.session_token, first.csrf_token)


def test_change_password_revokes_other_sessions(session_factory: sessionmaker[Session]) -> None:
    service = AuthService(session_factory)
    owner = service.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    current = service.login(
        "owner@example.com", "correct horse battery staple", client_label="Current"
    )
    other = service.login("owner@example.com", "correct horse battery staple", client_label="Other")
    service.change_password(
        owner.id,
        "correct horse battery staple",
        "brand new horse battery staple",
        token_hash(current.session_token),
    )
    assert service.authenticate_session(current.session_token, current.csrf_token).id == owner.id
    with pytest.raises(DomainError, match="expired"):
        service.authenticate_session(other.session_token, other.csrf_token)
    with pytest.raises(DomainError, match="Email or password"):
        service.login("owner@example.com", "correct horse battery staple")
    assert service.login("owner@example.com", "brand new horse battery staple").session_token


def test_change_password_validates(session_factory: sessionmaker[Session]) -> None:
    service = AuthService(session_factory)
    owner = service.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    current = service.login("owner@example.com", "correct horse battery staple")
    with pytest.raises(DomainError, match="incorrect"):
        service.change_password(
            owner.id,
            "wrong current password",
            "brand new horse battery staple",
            token_hash(current.session_token),
        )
    with pytest.raises(DomainError, match="12"):
        service.change_password(
            owner.id,
            "correct horse battery staple",
            "short",
            token_hash(current.session_token),
        )


def test_sweep_sessions_removes_expired_and_revoked(
    session_factory: sessionmaker[Session],
) -> None:
    from cookfully.jobs.retention import sweep_sessions

    service = AuthService(session_factory)
    owner = service.bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
    service.login("owner@example.com", "correct horse battery staple", client_label="Expired")
    service.login("owner@example.com", "correct horse battery staple", client_label="Revoked")
    active = service.login(
        "owner@example.com", "correct horse battery staple", client_label="Active"
    )

    with session_factory.begin() as session:
        expired = session.scalar(
            select(SessionRecord).where(SessionRecord.client_label == "Expired")
        )
        assert expired is not None
        expired.expires_at = datetime.now(UTC) - timedelta(days=31)
        revoked = session.scalar(
            select(SessionRecord).where(SessionRecord.client_label == "Revoked")
        )
        assert revoked is not None
        revoked.revoked_at = datetime.now(UTC) - timedelta(days=31)

    assert sweep_sessions(session_factory, now=datetime.now(UTC)) == 2
    remaining = service.list_sessions(owner.id, token_hash(active.session_token))
    assert [item.client_label for item in remaining] == ["Active"]
