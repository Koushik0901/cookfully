"""Stored import-review access with one owner-scoped expiry seam."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import DomainError, utc_now
from cookfully.infrastructure.models.import_preview import ImportPreviewRecord
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.repositories.recipes import RecipeRepository


class ImportReviewStore:
    """Resolve a live review payload and replacement target through one interface."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def load(self, parse_id: str, *, owner_id: UUID) -> dict[str, Any]:
        with self._session_factory() as session:
            record = session.scalar(
                select(ImportPreviewRecord).where(
                    ImportPreviewRecord.owner_id == owner_id,
                    ImportPreviewRecord.parse_id == parse_id,
                )
            )
            if record is None or record.expires_at < utc_now():
                raise DomainError(
                    "import_preview_expired",
                    "This import preview has expired. Try the import again.",
                    410,
                )
            return record.payload

    def load_for_replace(
        self, parse_id: str, recipe_id: UUID, *, owner_id: UUID
    ) -> tuple[dict[str, Any], Recipe]:
        with self._session_factory() as session:
            record = session.scalar(
                select(ImportPreviewRecord).where(
                    ImportPreviewRecord.owner_id == owner_id,
                    ImportPreviewRecord.parse_id == parse_id,
                )
            )
            if record is None or record.expires_at < utc_now():
                raise DomainError(
                    "import_preview_expired",
                    "This import preview has expired. Try the import again.",
                    410,
                )
            existing = RecipeRepository(session).get(recipe_id)
            return record.payload, existing
