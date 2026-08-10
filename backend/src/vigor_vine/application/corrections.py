from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.domain.common import (
    NUTRIENT_SCALE,
    SERVING_SCALE,
    DomainError,
    quantize_decimal,
    utc_now,
)
from vigor_vine.infrastructure.models.nutrition import NutritionCorrection
from vigor_vine.infrastructure.repositories.nutrition import NutritionRepository

DECIMAL_FIELDS = frozenset(
    {
        "quantity_min",
        "quantity_max",
        "grams",
        "yield_quantity",
        "calories_kcal",
        "protein_g",
        "carbohydrate_g",
        "fat_g",
    }
)
TEXT_FIELDS = frozenset({"unit", "food_name"})
REFERENCE_FIELDS = frozenset({"food_reference"})


class CorrectionService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def activate(
        self,
        *,
        recipe_id: UUID,
        ingredient_id: UUID | None,
        field: str,
        created_by: UUID,
        decimal_value: Decimal | None = None,
        text_value: str | None = None,
        reference_id_value: UUID | None = None,
        reason: str | None = None,
    ) -> NutritionCorrection:
        typed_count = sum(
            value is not None for value in (decimal_value, text_value, reference_id_value)
        )
        if typed_count != 1:
            raise DomainError(
                "correction_value_invalid", "Provide exactly one correction value.", 422
            )
        if field in DECIMAL_FIELDS and decimal_value is not None:
            scale = SERVING_SCALE if field == "yield_quantity" else NUTRIENT_SCALE
            decimal_value = quantize_decimal(decimal_value, scale)
            if decimal_value < 0 or (field == "yield_quantity" and decimal_value == 0):
                raise DomainError(
                    "correction_value_invalid", "Correction value is out of range.", 422
                )
        elif field in TEXT_FIELDS and text_value is not None:
            text_value = text_value.strip()
            if not text_value:
                raise DomainError(
                    "correction_value_invalid", "Correction text cannot be empty.", 422
                )
        elif field in REFERENCE_FIELDS and reference_id_value is not None:
            pass
        else:
            raise DomainError(
                "correction_field_invalid", "Correction field and value do not match.", 422
            )
        with self._session_factory.begin() as session:
            repository = NutritionRepository(session)
            return repository.activate_correction(
                NutritionCorrection(
                    recipe_id=recipe_id,
                    ingredient_id=ingredient_id,
                    field=field,
                    decimal_value=decimal_value,
                    text_value=text_value,
                    reference_id_value=reference_id_value,
                    reason=reason,
                    active=True,
                    created_by=created_by,
                )
            )

    def reset(self, correction_id: UUID, *, now: datetime | None = None) -> None:
        with self._session_factory.begin() as session:
            correction = session.scalar(
                select(NutritionCorrection)
                .where(NutritionCorrection.id == correction_id)
                .with_for_update()
            )
            if correction is None:
                raise DomainError("correction_not_found", "Correction was not found.", 404)
            correction.active = False
            correction.reset_at = now or utc_now()
