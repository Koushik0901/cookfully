from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Integer, Numeric, String, Text
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
        CheckConstraint(
            "decision_monthly_cap_usd >= 0 AND decision_monthly_cap_usd <= 100",
            name="valid_decision_monthly_cap",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    api_key_hint: Mapped[str | None] = mapped_column(String(8))
    cleanup_model: Mapped[str] = mapped_column(
        String(120), nullable=False, default="", server_default=""
    )
    # Owner overrides per decision feature: {purpose: {"enabled": bool, "models": [str]}}. A feature
    # without an entry uses the defaults in ``application.decisions.DEFAULT_FEATURES``.
    decision_features: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    decision_monthly_cap_usd: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False, default=Decimal("2.00"), server_default="2.00"
    )
    decision_assist_tolerance_dv: Mapped[Decimal] = mapped_column(
        Numeric(7, 6), nullable=False, default=Decimal("0.02"), server_default="0.02"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
