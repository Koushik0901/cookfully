from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.food_match_propagation import propagate_food_choice
from cookfully.application.ingredient_engine import engine
from cookfully.domain.common import NUTRIENT_SCALE, DomainError, quantize_decimal, require_version
from cookfully.domain.ingredient_nutrition.normalization import normalize as normalize_pantry_name
from cookfully.infrastructure.models.owner_foods import OwnerFood
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
    owner_food_id: UUID | None = None
    purchased_at: datetime | None = None
    expiry_source: str | None = None


def canonical_pantry_unit(value: str) -> str:
    try:
        return engine.canonical_pantry_unit(value)
    except DomainError as e:
        if e.code in ("unsafe_conversion", "quantity_unavailable"):
            raise DomainError(
                "pantry_unit_unsupported",
                "Pantry quantities require a supported mass, volume, or count unit.",
                422,
            ) from e
        raise


def convert_quantity(quantity: Decimal, from_unit: str, to_unit: str) -> Decimal:
    try:
        return engine.convert_quantity(quantity, from_unit, to_unit)
    except DomainError as e:
        if e.code == "unsafe_conversion":
            raise DomainError(
                "pantry_unit_incompatible",
                "Pantry and grocery quantities must use compatible units.",
                422,
            ) from e
        if e.code in ("quantity_unavailable",):
            raise DomainError(
                "pantry_unit_unsupported",
                "Pantry quantities require a supported mass, volume, or count unit.",
                422,
            ) from e
        raise


def apply_quantity_deduction(
    pantry: PantryQuantity,
    grocery: PantryQuantity,
) -> QuantityDeduction:
    from cookfully.domain.ingredient_nutrition.quantities import PantryQuantity as QPantry

    q_pantry = QPantry(pantry.quantity, pantry.unit, pantry.version)
    q_grocery = QPantry(grocery.quantity, grocery.unit, grocery.version)
    raw = engine.apply_deduction(q_pantry, q_grocery)
    return QuantityDeduction(
        pantry_before=PantryQuantity(
            raw.pantry_before.quantity, raw.pantry_before.unit, raw.pantry_before.version
        ),
        grocery_before=PantryQuantity(
            raw.grocery_before.quantity, raw.grocery_before.unit, raw.grocery_before.version
        ),
        pantry_after=PantryQuantity(
            raw.pantry_after.quantity, raw.pantry_after.unit, raw.pantry_after.version
        ),
        grocery_after=PantryQuantity(
            raw.grocery_after.quantity, raw.grocery_after.unit, raw.grocery_after.version
        ),
        pantry_amount=raw.pantry_amount,
        grocery_amount=raw.grocery_amount,
        assumption=raw.assumption,
    )


def reverse_quantity_deduction(
    deduction: QuantityDeduction,
    *,
    pantry: PantryQuantity,
    grocery: PantryQuantity,
) -> tuple[PantryQuantity, PantryQuantity]:
    from cookfully.domain.ingredient_nutrition.quantities import PantryQuantity as QPantry
    from cookfully.domain.ingredient_nutrition.quantities import QuantityDeduction as QDeduction

    q_deduction = QDeduction(
        pantry_before=QPantry(
            deduction.pantry_before.quantity,
            deduction.pantry_before.unit,
            deduction.pantry_before.version,
        ),
        grocery_before=QPantry(
            deduction.grocery_before.quantity,
            deduction.grocery_before.unit,
            deduction.grocery_before.version,
        ),
        pantry_after=QPantry(
            deduction.pantry_after.quantity,
            deduction.pantry_after.unit,
            deduction.pantry_after.version,
        ),
        grocery_after=QPantry(
            deduction.grocery_after.quantity,
            deduction.grocery_after.unit,
            deduction.grocery_after.version,
        ),
        pantry_amount=deduction.pantry_amount,
        grocery_amount=deduction.grocery_amount,
        assumption=deduction.assumption,
    )
    q_pantry = QPantry(pantry.quantity, pantry.unit, pantry.version)
    q_grocery = QPantry(grocery.quantity, grocery.unit, grocery.version)
    raw_pantry, raw_grocery = engine.reverse_deduction(
        q_deduction, pantry=q_pantry, grocery=q_grocery
    )
    return (
        PantryQuantity(raw_pantry.quantity, raw_pantry.unit, raw_pantry.version),
        PantryQuantity(raw_grocery.quantity, raw_grocery.unit, raw_grocery.version),
    )


class PantryService:
    def __init__(self, session_factory: sessionmaker[Session], jobs: object | None = None) -> None:
        self._session_factory = session_factory
        self._jobs = jobs

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
        owner_food_id: UUID | None = None,
    ) -> PantryItemRead:
        # Legacy-only: bulk inline split is handled async in api/routes/pantry.py
        return self._create_single(
            owner_id,
            display_name=display_name,
            quantity=quantity,
            unit=unit,
            expires_on=expires_on,
            food_reference_id=food_reference_id,
            owner_food_id=owner_food_id,
        )

    def _create_single(
        self,
        owner_id: UUID,
        *,
        display_name: str,
        quantity: Decimal,
        unit: str,
        expires_on: date | None = None,
        food_reference_id: UUID | None = None,
        owner_food_id: UUID | None = None,
    ) -> PantryItemRead:
        name = self._name(display_name)
        amount = self._quantity(quantity)
        canonical_unit = canonical_pantry_unit(unit)
        with self._session_factory.begin() as session:
            reference_id, resolved_owner_food_id, status, confidence = self._resolve_match(
                session, owner_id, name, food_reference_id, owner_food_id
            )
            item = PantryItem(
                owner_id=owner_id,
                display_name=name,
                normalized_food_name=normalize_pantry_name(name),
                quantity=amount,
                unit_code=canonical_unit,
                expires_on=expires_on,
                food_reference_id=reference_id,
                owner_food_id=resolved_owner_food_id,
                match_status=status,
                match_confidence=confidence,
                version=1,
            )
            session.add(item)
            session.flush()
            if food_reference_id is not None or owner_food_id is not None:
                propagate_food_choice(
                    session,
                    owner_id=owner_id,
                    ingredient_name=name,
                    food_reference_id=reference_id,
                    owner_food_id=resolved_owner_food_id,
                    jobs=self._jobs,
                )
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
            if "food_reference_id" in values or "owner_food_id" in values:
                reference_id = values.get("food_reference_id")
                owner_food_id = values.get("owner_food_id")
                resolved, resolved_owner_food_id, status, confidence = self._resolve_match(
                    session, owner_id, item.display_name, reference_id, owner_food_id
                )
                item.food_reference_id = resolved
                item.owner_food_id = resolved_owner_food_id
                item.match_status = status
                item.match_confidence = confidence
                if reference_id is not None or owner_food_id is not None:
                    propagate_food_choice(
                        session,
                        owner_id=owner_id,
                        ingredient_name=item.display_name,
                        food_reference_id=resolved,
                        owner_food_id=resolved_owner_food_id,
                        jobs=self._jobs,
                    )
            elif "display_name" in values and item.match_status != "manual":
                resolved, resolved_owner_food_id, status, confidence = self._resolve_match(
                    session, owner_id, item.display_name, None, None
                )
                item.food_reference_id = resolved
                item.owner_food_id = resolved_owner_food_id
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
        owner_id: UUID,
        display_name: str,
        requested_reference_id: UUID | None,
        requested_owner_food_id: UUID | None,
    ) -> tuple[UUID | None, UUID | None, str, Decimal | None]:
        if requested_reference_id is not None and requested_owner_food_id is not None:
            raise DomainError("food_match_source_conflict", "Choose one food source.", 422)
        if requested_reference_id is not None:
            if session.get(FoodReference, requested_reference_id) is None:
                raise DomainError("food_reference_not_found", "Food reference was not found.", 404)
            return requested_reference_id, None, "manual", Decimal("1.000000")
        if requested_owner_food_id is not None:
            owner_food = session.get(OwnerFood, requested_owner_food_id)
            if owner_food is None or owner_food.owner_id != owner_id or not owner_food.is_active:
                raise DomainError("owner_food_not_found", "Your custom food was not found.", 404)
            return None, requested_owner_food_id, "manual", Decimal("1.000000")
        decision = engine.match_ingredient(session, display_name)
        candidate = decision.candidate
        if candidate is None and decision.status == "ambiguous" and decision.alternatives:
            candidate = decision.alternatives[0]
        status_map = {"matched": "matched", "ambiguous": "proposed", "unmatched": "unmatched"}
        return (
            UUID(str(candidate.food.id)) if candidate is not None else None,
            None,
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
            owner_food_id=item.owner_food_id,
            match_status=item.match_status,
            match_confidence=item.match_confidence,
            version=item.version,
            purchased_at=item.purchased_at,
            expiry_source=item.expiry_source,
        )
