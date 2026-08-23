from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.ingredient_engine import engine
from cookfully.domain.common import NUTRIENT_SCALE, DomainError, quantize_decimal, require_version
from cookfully.domain.ingredient_nutrition.normalization import normalize as normalize_pantry_name
from cookfully.infrastructure.models.pantry import PantryDeduction, PantryItem
from cookfully.infrastructure.models.reference_foods import FoodReference

__all__ = [
    "PantryItemRead",
    "PantryQuantity",
    "PantryService",
    "QuantityDeduction",
    "apply_quantity_deduction",
    "canonical_pantry_unit",
    "convert_quantity",
    "normalize_pantry_name",
    "reverse_quantity_deduction",
]


@dataclass(frozen=True, slots=True)
class _Unit:
    dimension: str
    canonical: str
    factor: Decimal


_UNITS = {
    "mg": _Unit("mass", "mg", Decimal("0.001")),
    "g": _Unit("mass", "g", Decimal("1")),
    "gram": _Unit("mass", "g", Decimal("1")),
    "grams": _Unit("mass", "g", Decimal("1")),
    "kg": _Unit("mass", "kg", Decimal("1000")),
    "ml": _Unit("volume", "ml", Decimal("1")),
    "l": _Unit("volume", "l", Decimal("1000")),
    "count": _Unit("count", "count", Decimal("1")),
    "each": _Unit("count", "count", Decimal("1")),
    "ea": _Unit("count", "count", Decimal("1")),
}


@dataclass(frozen=True, slots=True)
class PantryQuantity:
    quantity: Decimal
    unit: str
    version: int


@dataclass(frozen=True, slots=True)
class QuantityDeduction:
    pantry_before: PantryQuantity
    grocery_before: PantryQuantity
    pantry_after: PantryQuantity
    grocery_after: PantryQuantity
    pantry_amount: Decimal
    grocery_amount: Decimal
    assumption: str


@dataclass(frozen=True, slots=True)
class PantryItemRead:
    id: UUID
    display_name: str
    normalized_food_name: str
    quantity: Decimal
    unit: str
    expires_on: date | None
    food_reference_id: UUID | None
    match_status: str
    match_confidence: Decimal | None
    version: int


def canonical_pantry_unit(value: str) -> str:
    normalized = value.strip().casefold().rstrip(".")
    unit = _UNITS.get(normalized)
    if unit is None:
        raise DomainError(
            "pantry_unit_unsupported",
            "Pantry quantities require a supported mass, volume, or count unit.",
            422,
        )
    return unit.canonical


def convert_quantity(quantity: Decimal, from_unit: str, to_unit: str) -> Decimal:
    source = _UNITS.get(from_unit.strip().casefold().rstrip("."))
    target = _UNITS.get(to_unit.strip().casefold().rstrip("."))
    if source is None or target is None:
        raise DomainError(
            "pantry_unit_unsupported",
            "Pantry quantities require a supported mass, volume, or count unit.",
            422,
        )
    if source.dimension != target.dimension:
        raise DomainError(
            "pantry_unit_incompatible",
            "Pantry and grocery quantities must use compatible units.",
            422,
        )
    if quantity < 0:
        raise DomainError("pantry_quantity_negative", "Pantry quantity cannot be negative.", 422)
    return quantize_decimal(quantity * source.factor / target.factor, NUTRIENT_SCALE)


def apply_quantity_deduction(
    pantry: PantryQuantity,
    grocery: PantryQuantity,
) -> QuantityDeduction:
    available_in_grocery_units = convert_quantity(pantry.quantity, pantry.unit, grocery.unit)
    grocery_amount = min(available_in_grocery_units, grocery.quantity)
    pantry_amount = convert_quantity(grocery_amount, grocery.unit, pantry.unit)
    pantry_after = PantryQuantity(
        quantize_decimal(pantry.quantity - pantry_amount, NUTRIENT_SCALE),
        canonical_pantry_unit(pantry.unit),
        pantry.version + 1,
    )
    grocery_after = PantryQuantity(
        quantize_decimal(grocery.quantity - grocery_amount, NUTRIENT_SCALE),
        canonical_pantry_unit(grocery.unit),
        grocery.version + 1,
    )
    return QuantityDeduction(
        pantry_before=PantryQuantity(
            quantize_decimal(pantry.quantity, NUTRIENT_SCALE),
            canonical_pantry_unit(pantry.unit),
            pantry.version,
        ),
        grocery_before=PantryQuantity(
            quantize_decimal(grocery.quantity, NUTRIENT_SCALE),
            canonical_pantry_unit(grocery.unit),
            grocery.version,
        ),
        pantry_after=pantry_after,
        grocery_after=grocery_after,
        pantry_amount=pantry_amount,
        grocery_amount=grocery_amount,
        assumption="Exact same-dimension conversion; no density or package-size assumption.",
    )


def reverse_quantity_deduction(
    deduction: QuantityDeduction,
    *,
    pantry: PantryQuantity,
    grocery: PantryQuantity,
) -> tuple[PantryQuantity, PantryQuantity]:
    if pantry != deduction.pantry_after or grocery != deduction.grocery_after:
        raise DomainError(
            "pantry_deduction_state_changed",
            "Pantry or grocery quantity changed after the deduction; reload before reversing.",
            409,
        )
    return (
        PantryQuantity(
            deduction.pantry_before.quantity,
            deduction.pantry_before.unit,
            pantry.version + 1,
        ),
        PantryQuantity(
            deduction.grocery_before.quantity,
            deduction.grocery_before.unit,
            grocery.version + 1,
        ),
    )


class PantryService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list(self, owner_id: UUID) -> tuple[PantryItemRead, ...]:
        with self._session_factory() as session:
            items = session.scalars(
                select(PantryItem)
                .where(PantryItem.owner_id == owner_id)
                .order_by(PantryItem.normalized_food_name, PantryItem.id)
            )
            return tuple(self._read(item) for item in items)

    def create(
        self,
        owner_id: UUID,
        *,
        display_name: str,
        quantity: Decimal,
        unit: str,
        expires_on: date | None = None,
        food_reference_id: UUID | None = None,
    ) -> PantryItemRead:
        name = self._name(display_name)
        amount = self._quantity(quantity)
        canonical_unit = canonical_pantry_unit(unit)
        with self._session_factory.begin() as session:
            reference_id, status, confidence = self._resolve_match(session, name, food_reference_id)
            item = PantryItem(
                owner_id=owner_id,
                display_name=name,
                normalized_food_name=normalize_pantry_name(name),
                quantity=amount,
                unit_code=canonical_unit,
                expires_on=expires_on,
                food_reference_id=reference_id,
                match_status=status,
                match_confidence=confidence,
                version=1,
            )
            session.add(item)
            session.flush()
            return self._read(item)

    def update(
        self,
        owner_id: UUID,
        item_id: UUID,
        values: dict[str, Any],
        *,
        expected_version: int,
    ) -> PantryItemRead:
        with self._session_factory.begin() as session:
            item = session.scalar(
                select(PantryItem)
                .where(PantryItem.id == item_id, PantryItem.owner_id == owner_id)
                .with_for_update()
            )
            if item is None:
                raise DomainError("pantry_item_not_found", "Pantry item was not found.", 404)
            require_version(expected_version, item.version)
            if "display_name" in values:
                item.display_name = self._name(str(values["display_name"]))
                item.normalized_food_name = normalize_pantry_name(item.display_name)
            if "quantity" in values:
                item.quantity = self._quantity(values["quantity"])
            if "unit" in values:
                item.unit_code = canonical_pantry_unit(str(values["unit"]))
            if "expires_on" in values:
                item.expires_on = values["expires_on"]
            if "food_reference_id" in values:
                reference_id = values["food_reference_id"]
                resolved, status, confidence = self._resolve_match(
                    session, item.display_name, reference_id
                )
                item.food_reference_id = resolved
                item.match_status = status
                item.match_confidence = confidence
            elif "display_name" in values and item.match_status != "manual":
                resolved, status, confidence = self._resolve_match(session, item.display_name, None)
                item.food_reference_id = resolved
                item.match_status = status
                item.match_confidence = confidence
            item.version += 1
            session.flush()
            return self._read(item)

    def remove(self, owner_id: UUID, item_id: UUID, *, expected_version: int) -> None:
        with self._session_factory.begin() as session:
            item = session.scalar(
                select(PantryItem)
                .where(PantryItem.id == item_id, PantryItem.owner_id == owner_id)
                .with_for_update()
            )
            if item is None:
                raise DomainError("pantry_item_not_found", "Pantry item was not found.", 404)
            require_version(expected_version, item.version)
            has_applied = session.scalar(
                select(PantryDeduction.id).where(
                    PantryDeduction.pantry_item_id == item.id,
                    PantryDeduction.status == "applied",
                )
            )
            if has_applied is not None:
                raise DomainError(
                    "pantry_item_has_deductions",
                    "Reverse applied grocery deductions before deleting this pantry item.",
                    409,
                )
            session.execute(delete(PantryItem).where(PantryItem.id == item.id))

    @staticmethod
    def _name(value: str) -> str:
        name = value.strip()
        if not name:
            raise DomainError("pantry_name_required", "Food name is required.", 422)
        if len(name) > 240:
            raise DomainError("pantry_name_too_long", "Food name is too long.", 422)
        return name

    @staticmethod
    def _quantity(value: Decimal) -> Decimal:
        quantity = quantize_decimal(value, NUTRIENT_SCALE)
        if quantity < 0:
            raise DomainError(
                "pantry_quantity_negative", "Pantry quantity cannot be negative.", 422
            )
        return quantity

    @staticmethod
    def _resolve_match(
        session: Session,
        display_name: str,
        requested_reference_id: UUID | None,
    ) -> tuple[UUID | None, str, Decimal | None]:
        if requested_reference_id is not None:
            if session.get(FoodReference, requested_reference_id) is None:
                raise DomainError("food_reference_not_found", "Food reference was not found.", 404)
            return requested_reference_id, "manual", Decimal("1.000000")
        decision = engine.match_ingredient(session, display_name)
        candidate = decision.candidate
        if candidate is None and decision.status == "ambiguous" and decision.alternatives:
            candidate = decision.alternatives[0]
        status_map = {"matched": "matched", "ambiguous": "proposed", "unmatched": "unmatched"}
        return (
            UUID(str(candidate.food.id)) if candidate is not None else None,
            status_map.get(decision.status, "unmatched"),
            candidate.score if candidate is not None else None,
        )

    @staticmethod
    def _read(item: PantryItem) -> PantryItemRead:
        return PantryItemRead(
            id=item.id,
            display_name=item.display_name,
            normalized_food_name=item.normalized_food_name,
            quantity=item.quantity,
            unit=item.unit_code,
            expires_on=item.expires_on,
            food_reference_id=item.food_reference_id,
            match_status=item.match_status,
            match_confidence=item.match_confidence,
            version=item.version,
        )
