from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from vigor_vine.domain.common import NUTRIENT_SCALE, DomainError, quantize_decimal, utc_now
from vigor_vine.infrastructure.models.owner_foods import OwnerFood


class OwnerFoodWrite:
    __slots__ = (
        "basis_grams",
        "brand",
        "calories_kcal",
        "carbohydrate_g",
        "display_name",
        "fat_g",
        "normalized_name",
        "protein_g",
        "typical_serving_g",
        "typical_serving_unit",
    )

    def __init__(
        self,
        *,
        display_name: str,
        normalized_name: str,
        brand: str | None = None,
        calories_kcal: Decimal,
        protein_g: Decimal,
        carbohydrate_g: Decimal,
        fat_g: Decimal,
        basis_grams: Decimal = Decimal(100),
        typical_serving_g: Decimal | None = None,
        typical_serving_unit: str | None = None,
    ) -> None:
        self.display_name = display_name
        self.normalized_name = normalized_name
        self.brand = brand
        self.calories_kcal = quantize_decimal(calories_kcal, NUTRIENT_SCALE)
        self.protein_g = quantize_decimal(protein_g, NUTRIENT_SCALE)
        self.carbohydrate_g = quantize_decimal(carbohydrate_g, NUTRIENT_SCALE)
        self.fat_g = quantize_decimal(fat_g, NUTRIENT_SCALE)
        self.basis_grams = quantize_decimal(basis_grams, NUTRIENT_SCALE)
        self.typical_serving_g = (
            quantize_decimal(typical_serving_g, NUTRIENT_SCALE)
            if typical_serving_g is not None
            else None
        )
        self.typical_serving_unit = typical_serving_unit


class UserFoodRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def search(self, owner_id: UUID, normalized_query: str, *, limit: int = 20) -> list[OwnerFood]:
        tokens = [t for t in normalized_query.split() if t]
        if not tokens:
            return list(
                self.session.scalars(
                    select(OwnerFood)
                    .where(
                        OwnerFood.owner_id == owner_id,
                        OwnerFood.is_active.is_(True),
                    )
                    .order_by(OwnerFood.normalized_name)
                    .limit(limit)
                )
            )
        name_filter = or_(*(OwnerFood.normalized_name.ilike(f"%{token}%") for token in tokens))
        return list(
            self.session.scalars(
                select(OwnerFood)
                .where(
                    OwnerFood.owner_id == owner_id,
                    OwnerFood.is_active.is_(True),
                    name_filter,
                )
                .order_by(OwnerFood.normalized_name)
                .limit(limit)
            )
        )

    def by_id(self, owner_id: UUID, food_id: UUID) -> OwnerFood | None:
        return cast(
            OwnerFood | None,
            self.session.scalar(
                select(OwnerFood).where(
                    OwnerFood.id == food_id,
                    OwnerFood.owner_id == owner_id,
                )
            ),
        )

    def create(self, owner_id: UUID, write: OwnerFoodWrite) -> OwnerFood:
        existing = self.session.scalar(
            select(OwnerFood).where(
                OwnerFood.owner_id == owner_id,
                OwnerFood.normalized_name == write.normalized_name,
                OwnerFood.is_active.is_(True),
            )
        )
        if existing is not None:
            raise DomainError(
                "owner_food_duplicate",
                f"You already have an active food named '{write.display_name}'. "
                "Update or deactivate it instead.",
                409,
            )
        now = utc_now()
        food = OwnerFood(
            owner_id=owner_id,
            display_name=write.display_name,
            normalized_name=write.normalized_name,
            brand=write.brand,
            calories_kcal=write.calories_kcal,
            protein_g=write.protein_g,
            carbohydrate_g=write.carbohydrate_g,
            fat_g=write.fat_g,
            basis_grams=write.basis_grams,
            typical_serving_g=write.typical_serving_g,
            typical_serving_unit=write.typical_serving_unit,
            is_active=True,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(food)
        self.session.flush()
        return food

    def update(
        self,
        owner_id: UUID,
        food_id: UUID,
        *,
        write: OwnerFoodWrite,
        expected_version: int,
    ) -> OwnerFood:
        result = cast(
            CursorResult[Any],
            self.session.execute(
                update(OwnerFood)
                .where(
                    OwnerFood.id == food_id,
                    OwnerFood.owner_id == owner_id,
                    OwnerFood.version == expected_version,
                )
                .values(
                    display_name=write.display_name,
                    normalized_name=write.normalized_name,
                    brand=write.brand,
                    calories_kcal=write.calories_kcal,
                    protein_g=write.protein_g,
                    carbohydrate_g=write.carbohydrate_g,
                    fat_g=write.fat_g,
                    basis_grams=write.basis_grams,
                    typical_serving_g=write.typical_serving_g,
                    typical_serving_unit=write.typical_serving_unit,
                    version=OwnerFood.version + 1,
                    updated_at=utc_now(),
                ),
            ),
        )
        if result.rowcount == 0:
            raise DomainError(
                "owner_food_version_conflict",
                "This food was changed by another request; reload and retry.",
                409,
            )
        return cast(OwnerFood, self.by_id(owner_id, food_id))

    def deactivate(self, owner_id: UUID, food_id: UUID, *, expected_version: int) -> None:
        result = cast(
            CursorResult[Any],
            self.session.execute(
                update(OwnerFood)
                .where(
                    OwnerFood.id == food_id,
                    OwnerFood.owner_id == owner_id,
                    OwnerFood.version == expected_version,
                )
                .values(is_active=False, version=OwnerFood.version + 1, updated_at=utc_now())
            ),
        )
        if result.rowcount == 0:
            raise DomainError(
                "owner_food_version_conflict",
                "This food was changed by another request; reload and retry.",
                409,
            )
