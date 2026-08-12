from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cookfully.application.access_tokens import AccessTokenRead

TokenScope = Literal[
    "recipes:read",
    "goals:read",
    "plans:read",
    "plans:write",
    "grocery:read",
    "grocery:write",
]


class AccessTokenWriteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    scopes: Annotated[list[TokenScope], Field(min_length=1)]
    expires_at: datetime | None = Field(default=None, alias="expiresAt")

    @model_validator(mode="after")
    def unique_scopes(self) -> AccessTokenWriteRequest:
        if len(set(self.scopes)) != len(self.scopes):
            raise ValueError("Token scopes must be unique.")
        return self


class AccessTokenResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    name: str
    scopes: list[TokenScope]
    created_at: datetime = Field(alias="createdAt")
    expires_at: datetime | None = Field(alias="expiresAt")
    last_used_at: datetime | None = Field(alias="lastUsedAt")
    revoked_at: datetime | None = Field(alias="revokedAt")

    @classmethod
    def from_read(cls, token: AccessTokenRead) -> AccessTokenResponse:
        return cls(
            id=token.id,
            name=token.name,
            scopes=list(token.scopes),
            created_at=token.created_at,
            expires_at=token.expires_at,
            last_used_at=token.last_used_at,
            revoked_at=token.revoked_at,
        )


class AccessTokenCreatedResponse(AccessTokenResponse):
    secret: str = Field(min_length=32, json_schema_extra={"x-sensitive": True})
