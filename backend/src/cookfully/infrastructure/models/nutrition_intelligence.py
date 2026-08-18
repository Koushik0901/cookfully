from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.infrastructure.models.base import Base, TimestampMixin


class NutritionIntelligenceSettings(TimestampMixin, Base):
    __tablename__ = "nutrition_intelligence_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_nutrition_intelligence_settings"),
        CheckConstraint("backend IN ('hashing', 'fastembed')", name="valid_nutrition_backend"),
        CheckConstraint("concurrency BETWEEN 1 AND 4", name="valid_nutrition_concurrency"),
        CheckConstraint("version > 0", name="positive_nutrition_settings_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    backend: Mapped[str] = mapped_column(String(16), nullable=False, default="hashing")
    model_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="BAAI/bge-small-en-v1.5"
    )
    model_revision: Mapped[str | None] = mapped_column(String(80))
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
