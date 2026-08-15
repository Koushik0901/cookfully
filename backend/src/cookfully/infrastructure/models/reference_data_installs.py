from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base, TimestampMixin


class ReferenceDataInstall(TimestampMixin, Base):
    __tablename__ = "reference_data_installs"
    __table_args__ = (Index("ix_reference_data_installs_owner_id", "owner_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("owner_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    datasets: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
