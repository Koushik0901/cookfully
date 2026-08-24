from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.pantry import (
    PantryQuantity,
    apply_quantity_deduction,
    convert_quantity,
)
from cookfully.domain.common import (
    NUTRIENT_SCALE,
    DomainError,
    quantize_decimal,
    require_version,
    utc_now,
)
from cookfully.infrastructure.models.grocery import GroceryItem, GroceryList
from cookfully.infrastructure.models.pantry import PantryDeduction, PantryItem
from cookfully.infrastructure.models.plans import MealPlan


@dataclass(frozen=True, slots=True)
class PantryDeductionRead:
    id: UUID
    pantry_item_id: UUID
    grocery_item_id: UUID
    pantry_quantity: Decimal
    pantry_unit: str
    grocery_quantity: Decimal
    grocery_unit: str
    assumption: str
    status: str
    applied_at: datetime
    reversed_at: datetime | None
    version: int


class PantryDeductionService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def apply(
        self,
        owner_id: UUID,
        week_start: object,
        *,
        expected_grocery_list_version: int,
        grocery_item_ids: tuple[UUID, ...] | None = None,
    ) -> tuple[PantryDeductionRead, ...]:
        with self._session_factory.begin() as session:
            grocery_list = session.scalar(
                select(GroceryList)
                .join(MealPlan)
                .where(MealPlan.owner_id == owner_id, MealPlan.week_start == week_start)
                .with_for_update()
            )
            if grocery_list is None:
                raise DomainError("grocery_list_not_found", "Grocery list was not found.", 404)
            require_version(expected_grocery_list_version, grocery_list.version)
            statement = (
                select(GroceryItem)
                .where(GroceryItem.grocery_list_id == grocery_list.id)
                .order_by(GroceryItem.position, GroceryItem.id)
                .with_for_update()
            )
            if grocery_item_ids is not None:
                requested = set(grocery_item_ids)
                statement = statement.where(GroceryItem.id.in_(requested))
            grocery_items = list(session.scalars(statement))
            if grocery_item_ids is not None and {item.id for item in grocery_items} != set(
                grocery_item_ids
            ):
                raise DomainError(
                    "grocery_item_not_found", "A selected grocery item was not found.", 404
                )
            applied: list[PantryDeduction] = []
            for grocery in grocery_items:
                if (
                    grocery.quantity is None
                    or grocery.quantity <= 0
                    or not grocery.unit_code
                    or grocery.needs_review
                ):
                    continue
                pantry_items = list(
                    session.scalars(
                        select(PantryItem)
                        .where(
                            PantryItem.owner_id == owner_id,
                            PantryItem.normalized_food_name == grocery.normalized_food_name,
                            PantryItem.match_status.in_(("matched", "manual")),
                            PantryItem.quantity > 0,
                        )
                        .order_by(PantryItem.unit_code != grocery.unit_code, PantryItem.id)
                        .with_for_update()
                    )
                )
                for pantry in pantry_items:
                    if grocery.quantity <= 0:
                        break
                    try:
                        available = convert_quantity(
                            pantry.quantity, pantry.unit_code, grocery.unit_code
                        )
                    except DomainError:
                        continue
                    if available <= 0:
                        continue
                    value = apply_quantity_deduction(
                        PantryQuantity(pantry.quantity, pantry.unit_code, pantry.version),
                        PantryQuantity(grocery.quantity, grocery.unit_code, grocery.version),
                    )
                    if value.grocery_amount <= 0:
                        continue
                    # capture prior expiry for reversible restore before overwriting
                    prev_purchased_at = pantry.purchased_at
                    prev_expires_on = pantry.expires_on
                    prev_expiry_source = pantry.expiry_source
                    # copy expiry from grocery to pantry if grocery has expiry
                    # and pantry not manual; after guards so we don't
                    # clobber pantry when no deduction occurs
                    if (
                        grocery.expires_on is not None
                        and grocery.purchased_at is not None
                        and grocery.expiry_source is not None
                        and pantry.expiry_source != "manual"
                    ):
                        pantry.expires_on = grocery.expires_on
                        pantry.purchased_at = grocery.purchased_at
                        pantry.expiry_source = grocery.expiry_source
                    pantry.quantity = value.pantry_after.quantity
                    pantry.version = value.pantry_after.version
                    grocery.quantity = value.grocery_after.quantity
                    grocery.version = value.grocery_after.version
                    assumption = value.assumption
                    if grocery.expires_on is not None and grocery.expiry_source is not None:
                        assumption = (
                            f"{value.assumption}; expiry "
                            f"{grocery.expiry_source} {grocery.expires_on}"
                        )
                    deduction = PantryDeduction(
                        pantry_item_id=pantry.id,
                        grocery_item_id=grocery.id,
                        pantry_quantity=value.pantry_amount,
                        pantry_unit=value.pantry_after.unit,
                        grocery_quantity=value.grocery_amount,
                        grocery_unit=value.grocery_after.unit,
                        assumption=assumption,
                        status="applied",
                        pantry_version_after=pantry.version,
                        grocery_version_after=grocery.version,
                        prev_purchased_at=prev_purchased_at,
                        prev_expires_on=prev_expires_on,
                        prev_expiry_source=prev_expiry_source,
                        applied_at=utc_now(),
                        version=1,
                    )
                    session.add(deduction)
                    session.flush()
                    applied.append(deduction)
            if applied:
                grocery_list.version += 1
            session.flush()
            return tuple(self._read(item) for item in applied)

    def reverse(
        self,
        owner_id: UUID,
        deduction_id: UUID,
        *,
        expected_version: int,
    ) -> PantryDeductionRead:
        with self._session_factory.begin() as session:
            deduction = session.scalar(
                select(PantryDeduction)
                .join(PantryItem)
                .where(
                    PantryDeduction.id == deduction_id,
                    PantryItem.owner_id == owner_id,
                )
                .with_for_update()
            )
            if deduction is None:
                raise DomainError(
                    "pantry_deduction_not_found", "Pantry deduction was not found.", 404
                )
            require_version(expected_version, deduction.version)
            if deduction.status != "applied":
                raise DomainError(
                    "pantry_deduction_reversed", "Pantry deduction is already reversed.", 409
                )
            pantry = session.get(PantryItem, deduction.pantry_item_id, with_for_update=True)
            grocery = session.get(GroceryItem, deduction.grocery_item_id, with_for_update=True)
            if pantry is None or grocery is None:
                raise DomainError(
                    "pantry_deduction_target_missing",
                    "A deduction target no longer exists and cannot be reversed safely.",
                    409,
                )
            if (
                pantry.version != deduction.pantry_version_after
                or grocery.version != deduction.grocery_version_after
            ):
                raise DomainError(
                    "pantry_deduction_state_changed",
                    "Pantry or grocery quantity changed after the deduction; "
                    "reverse newer changes first.",
                    409,
                )
            pantry.quantity = quantize_decimal(
                pantry.quantity + deduction.pantry_quantity, NUTRIENT_SCALE
            )
            grocery.quantity = quantize_decimal(
                (grocery.quantity or Decimal(0)) + deduction.grocery_quantity,
                NUTRIENT_SCALE,
            )
            # restore prior expiry saved at apply time (reversible)
            pantry.purchased_at = deduction.prev_purchased_at
            pantry.expires_on = deduction.prev_expires_on
            pantry.expiry_source = deduction.prev_expiry_source
            pantry.version += 1
            grocery.version += 1
            grocery.grocery_list.version += 1
            deduction.status = "reversed"
            deduction.reversed_at = utc_now()
            deduction.version += 1
            session.flush()
            return self._read(deduction)

    @staticmethod
    def _read(item: PantryDeduction) -> PantryDeductionRead:
        return PantryDeductionRead(
            item.id,
            item.pantry_item_id,
            item.grocery_item_id,
            item.pantry_quantity,
            item.pantry_unit,
            item.grocery_quantity,
            item.grocery_unit,
            item.assumption,
            item.status,
            item.applied_at,
            item.reversed_at,
            item.version,
        )
