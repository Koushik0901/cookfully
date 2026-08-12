from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import DomainError, utc_now
from cookfully.infrastructure.models.identity import AccessToken, OwnerAccount

ALL_TOKEN_SCOPES = frozenset(
    {
        "recipes:read",
        "goals:read",
        "plans:read",
        "plans:write",
        "grocery:read",
        "grocery:write",
    }
)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AccessTokenRead:
    id: UUID
    name: str
    scopes: tuple[str, ...]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    token: AccessTokenRead
    secret: str


@dataclass(frozen=True, slots=True)
class AccessTokenPrincipal:
    token_id: UUID
    owner: OwnerAccount
    scopes: frozenset[str]


class AccessTokenService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(
        self,
        owner_id: UUID,
        name: str,
        scopes: set[str],
        *,
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> IssuedAccessToken:
        checked_at = (now or utc_now()).astimezone(UTC)
        normalized_name = name.strip()
        if not normalized_name:
            raise DomainError("invalid_token_name", "Token name is required.", 422)
        if not scopes:
            raise DomainError("invalid_scope", "At least one token scope is required.", 422)
        unknown = scopes - ALL_TOKEN_SCOPES
        if unknown:
            raise DomainError("invalid_scope", f"Unknown token scope: {sorted(unknown)[0]}", 422)
        if expires_at is not None:
            if expires_at.utcoffset() is None:
                raise DomainError(
                    "invalid_token_expiry", "Token expiry must include a timezone offset.", 422
                )
            if expires_at.astimezone(UTC) <= checked_at:
                raise DomainError(
                    "invalid_token_expiry", "Token expiry must be in the future.", 422
                )

        raw_token = f"cookfully_{secrets.token_urlsafe(32)}"
        with self._session_factory.begin() as session:
            record = AccessToken(
                owner_id=owner_id,
                token_hash=token_hash(raw_token),
                name=normalized_name,
                scopes=sorted(scopes),
                expires_at=expires_at,
            )
            session.add(record)
            session.flush()
            read = self._to_read(record)
        return IssuedAccessToken(read, raw_token)

    def list(self, owner_id: UUID) -> tuple[AccessTokenRead, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(AccessToken)
                .where(AccessToken.owner_id == owner_id)
                .order_by(AccessToken.created_at.desc(), AccessToken.id.desc())
            )
            return tuple(self._to_read(record) for record in records)

    def revoke(
        self, owner_id: UUID, token_id: UUID, *, now: datetime | None = None
    ) -> AccessTokenRead:
        revoked_at = (now or utc_now()).astimezone(UTC)
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(AccessToken)
                .where(AccessToken.id == token_id, AccessToken.owner_id == owner_id)
                .with_for_update()
            )
            if record is None:
                raise DomainError("access_token_not_found", "Access token was not found.", 404)
            if record.revoked_at is None:
                record.revoked_at = revoked_at
            session.flush()
            return self._to_read(record)

    def authenticate(self, token: str, required_scopes: set[str]) -> OwnerAccount:
        return self.authenticate_principal(token, required_scopes).owner

    def authenticate_principal(self, token: str, required_scopes: set[str]) -> AccessTokenPrincipal:
        if not token:
            raise DomainError("token_invalid", "Access token is invalid or expired.", 401)
        unknown = required_scopes - ALL_TOKEN_SCOPES
        if unknown:
            raise DomainError("scope_not_declared", "The requested scope is not declared.", 500)
        now = utc_now()
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(AccessToken).where(AccessToken.token_hash == token_hash(token))
            )
            if (
                record is None
                or record.revoked_at is not None
                or (record.expires_at is not None and record.expires_at <= now)
            ):
                raise DomainError("token_invalid", "Access token is invalid or expired.", 401)
            if not required_scopes.issubset(set(record.scopes)):
                raise DomainError(
                    "insufficient_scope", "Access token lacks the required scope.", 403
                )
            record.last_used_at = now
            return AccessTokenPrincipal(record.id, record.owner, frozenset(record.scopes))

    @staticmethod
    def _to_read(record: AccessToken) -> AccessTokenRead:
        return AccessTokenRead(
            id=record.id,
            name=record.name,
            scopes=tuple(sorted(record.scopes)),
            created_at=record.created_at,
            expires_at=record.expires_at,
            last_used_at=record.last_used_at,
            revoked_at=record.revoked_at,
        )
