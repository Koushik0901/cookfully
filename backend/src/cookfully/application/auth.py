from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.access_tokens import ALL_TOKEN_SCOPES as ALL_TOKEN_SCOPES
from cookfully.application.access_tokens import AccessTokenService, token_hash
from cookfully.application.access_tokens import IssuedAccessToken as ManagedAccessToken
from cookfully.domain.common import DomainError, utc_now
from cookfully.infrastructure.models.identity import OwnerAccount, SessionRecord


def _token_hash(token: str) -> str:
    return token_hash(token)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    session_token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    id: UUID
    token: str
    scopes: frozenset[str]
    expires_at: datetime | None


class AuthService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        session_ttl: timedelta = timedelta(days=14),
    ) -> None:
        self._session_factory = session_factory
        self._session_ttl = session_ttl
        self._passwords = PasswordHasher()
        self._access_tokens = AccessTokenService(session_factory)

    def bootstrap_owner(self, email: str, password: str, display_name: str) -> OwnerAccount:
        normalized = email.strip().lower()
        if len(password) < 12:
            raise DomainError("weak_password", "Password must contain at least 12 characters.", 422)
        with self._session_factory.begin() as session:
            existing = session.scalar(select(OwnerAccount).where(OwnerAccount.email == normalized))
            if existing is not None:
                return existing
            owner = OwnerAccount(
                email=normalized,
                display_name=display_name.strip(),
                password_hash=self._passwords.hash(password),
                timezone="UTC",
                week_starts_on=1,
            )
            session.add(owner)
            session.flush()
            return owner

    def login(self, email: str, password: str, client_label: str | None = None) -> IssuedSession:
        normalized = email.strip().lower()
        with self._session_factory.begin() as session:
            owner = session.scalar(select(OwnerAccount).where(OwnerAccount.email == normalized))
            if owner is None or owner.status != "active":
                raise DomainError("invalid_credentials", "Email or password is incorrect.", 401)
            try:
                self._passwords.verify(owner.password_hash, password)
            except VerifyMismatchError as exc:
                raise DomainError(
                    "invalid_credentials", "Email or password is incorrect.", 401
                ) from exc
            if self._passwords.check_needs_rehash(owner.password_hash):
                owner.password_hash = self._passwords.hash(password)
            now = utc_now()
            raw_session = secrets.token_urlsafe(32)
            raw_csrf = secrets.token_urlsafe(32)
            expires_at = now + self._session_ttl
            session.add(
                SessionRecord(
                    id_hash=_token_hash(raw_session),
                    owner_id=owner.id,
                    csrf_secret_hash=_token_hash(raw_csrf),
                    created_at=now,
                    expires_at=expires_at,
                    last_seen_at=now,
                    client_label=client_label,
                )
            )
        return IssuedSession(raw_session, raw_csrf, expires_at)

    def authenticate_session(
        self,
        session_token: str,
        csrf_token: str | None = None,
        *,
        now: datetime | None = None,
        enforce_csrf: bool = True,
    ) -> OwnerAccount:
        checked_at = (now or utc_now()).astimezone(UTC)
        with self._session_factory.begin() as session:
            record = session.get(SessionRecord, _token_hash(session_token))
            if record is None or record.revoked_at is not None or record.expires_at <= checked_at:
                raise DomainError("session_expired", "Your session has expired.", 401)
            if enforce_csrf and (
                csrf_token is None
                or not hmac.compare_digest(record.csrf_secret_hash, _token_hash(csrf_token))
            ):
                raise DomainError("csrf_invalid", "CSRF validation failed.", 403)
            record.last_seen_at = checked_at
            return record.owner

    def logout(self, session_token: str) -> None:
        with self._session_factory.begin() as session:
            record = session.get(SessionRecord, _token_hash(session_token))
            if record is not None and record.revoked_at is None:
                record.revoked_at = utc_now()

    def create_access_token(
        self,
        owner_id: UUID,
        name: str,
        scopes: set[str],
        *,
        expires_at: datetime | None = None,
    ) -> IssuedAccessToken:
        issued: ManagedAccessToken = self._access_tokens.create(
            owner_id, name, scopes, expires_at=expires_at
        )
        return IssuedAccessToken(
            issued.token.id,
            issued.secret,
            frozenset(issued.token.scopes),
            issued.token.expires_at,
        )

    def authenticate_token(self, token: str, required_scopes: set[str]) -> OwnerAccount:
        return self._access_tokens.authenticate(token, required_scopes)
