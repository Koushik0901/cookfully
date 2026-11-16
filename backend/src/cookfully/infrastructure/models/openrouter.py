from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Integer, Numeric, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.infrastructure.models.base import Base, TimestampMixin


class OpenRouterSettings(TimestampMixin, Base):
    """Singleton row holding the owner's OpenRouter credential and model choices.

    The API key is stored only as ciphertext (``SecretBox``) plus a short display hint; it is never
    returned by the API.
    """

    __tablename__ = "openrouter_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_openrouter_settings"),
        CheckConstraint("version > 0", name="positive_openrouter_settings_version"),
        CheckConstraint(
            "decision_assist_tolerance_dv > 0 AND decision_assist_tolerance_dv <= 0.1",
            name="valid_decision_assist_tolerance",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    api_key_hint: Mapped[str | None] = mapped_column(String(8))
    cleanup_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", server_default=""
    )
    decision_assist_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    decision_assist_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="typesafe/jev-1.14", server_default="typesafe/jev-1.14"
    )
    decision_assist_tolerance_dv: Mapped[Decimal] = mapped_column(
        Numeric(7, 6), nullable=False, default=Decimal("0.02"), server_default="0.02"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
