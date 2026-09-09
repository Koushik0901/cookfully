from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Integer, false, true
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.infrastructure.models.base import Base, TimestampMixin


class RecipeImportSettings(TimestampMixin, Base):
    __tablename__ = "recipe_import_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_recipe_import_settings"),
        CheckConstraint("version > 0", name="positive_recipe_import_settings_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    cleanup_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    openrouter_fallback_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
