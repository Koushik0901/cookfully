"""Import preview persistence. Short-lived preview scoped to an owner."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base


class ImportPreviewRecord(Base):
    __tablename__ = "import_previews"
    __table_args__ = (
        Index("ix_import_previews_expires_at", "expires_at"),
        Index("ix_import_previews_owner_parse_id", "owner_id", "parse_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("owner_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    parse_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)