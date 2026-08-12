from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.grocery_reconciliation import (
    ExistingGroceryItem,
    reconcile_grocery_items,
)
from cookfully.domain.common import DomainError, require_version, utc_now
from cookfully.domain.grocery import (
    GroceryIngredient,
    GrocerySource,
    aggregate_grocery_ingredients,
    normalize_food_name,
)
from cookfully.infrastructure.models.grocery import GroceryItem, GroceryItemSource, GroceryList
from cookfully.infrastructure.models.plans import MealPlan
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.repositories.grocery import GroceryRepository
from cookfully.infrastructure.repositories.plans import MealPlanRepository


@dataclass(frozen=True, slots=True)
class GrocerySourceRead:
    meal_plan_entry_id: UUID
    original_text: str
    quantity_contribution: Decimal | None


@dataclass(frozen=True, slots=True)
class GroceryItemRead:
    id: UUID
    display_name: str
    quantity: Decimal | None
    unit: str | None
    origin: str
    checked: bool
    needs_review: bool
    position: int
    sources: tuple[GrocerySourceRead, ...]
    version: int


@dataclass(frozen=True, slots=True)
class GroceryListRead:
    id: UUID
    week_start: date
    status: str
    generated_at: datetime | None
    items: tuple[GroceryItemRead, ...]
    version: int


class GroceryListService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, owner_id: UUID, week_start: date) -> GroceryListRead:
        with self._session_factory() as session:
            return self._list_read(GroceryRepository(session).get_for_week(owner_id, week_start))

    def generate(self, owner_id: UUID, week_start: date) -> GroceryListRead:
        with self._session_factory.begin() as session:
            plan = MealPlanRepository(session).get_week(owner_id, week_start, for_update=True)
            repository = GroceryRepository(session)
            grocery_list = repository.find_for_plan(plan.id, for_update=True)
            if grocery_list is None:
                grocery_list = GroceryList(
                    meal_plan_id=plan.id,
                    status="generating",
                    source_plan_version=plan.version,
                    version=1,
                )
                session.add(grocery_list)
                session.flush()
            else:
                grocery_list.status = "generating"

            proposed = aggregate_grocery_ingredients(self._ingredients(session, plan))
            current = [self._existing(item) for item in grocery_list.items]
            reconciled = reconcile_grocery_items(current, proposed)
            by_id = {item.id: item for item in grocery_list.items}
            retained = {item.id for item in reconciled if item.id is not None}
            for item in list(grocery_list.items):
                if item.id not in retained:
                    session.delete(item)
            session.flush()
            for value in reconciled:
                model = by_id.get(value.id) if value.id is not None else None
                if model is None:
                    model = GroceryItem()
                    grocery_list.items.append(model)
                self._apply_reconciled(model, value)
                model.sources.clear()
                session.flush()
                model.sources.extend(
                    GroceryItemSource(
                        meal_plan_entry_id=source.meal_plan_entry_id,
                        ingredient_id=source.ingredient_id,
                        original_text=source.original_text,
                        quantity_contribution=source.quantity_contribution,
                    )
                    for source in value.sources
                )
            grocery_list.status = "current"
            grocery_list.source_plan_version = plan.version
            grocery_list.generated_at = utc_now()
            if current:
                grocery_list.version += 1
            session.flush()
            return self._list_read(grocery_list)

    def create_manual(
        self,
        owner_id: UUID,
        week_start: date,
        *,
        display_name: str,
        quantity: Decimal | None,
        unit: str | None,
        checked: bool = False,
        position: int | None = None,
    ) -> GroceryItemRead:
        name = display_name.strip()
        if not name:
            raise DomainError("grocery_name_required", "Display name is required.", 422)
        with self._session_factory.begin() as session:
            grocery_list = GroceryRepository(session).get_for_week(
                owner_id, week_start, for_update=True
            )
            if position is None:
                maximum = session.scalar(
                    select(func.max(GroceryItem.position)).where(
                        GroceryItem.grocery_list_id == grocery_list.id
                    )
                )
                position = (maximum if maximum is not None else -1) + 1
            self._position_available(session, grocery_list.id, position)
            item = GroceryItem(
                grocery_list_id=grocery_list.id,
                normalized_food_name=normalize_food_name(name),
                display_name=name,
                quantity=quantity,
                unit_code=unit.strip() if unit else None,
                unit_text=unit.strip() if unit else None,
                aggregation_key=None,
                origin="manual",
                checked=checked,
                manual_quantity=quantity is not None or unit is not None,
                manual_name=True,
                needs_review=False,
                position=position,
                version=1,
            )
            session.add(item)
            grocery_list.version += 1
            session.flush()
            return self._item_read(item)

    def update(
        self,
        owner_id: UUID,
        item_id: UUID,
        values: dict[str, Any],
        *,
        expected_version: int,
    ) -> GroceryItemRead:
        with self._session_factory.begin() as session:
            item = GroceryRepository(session).get_item(owner_id, item_id, for_update=True)
            require_version(expected_version, item.version)
            if "display_name" in values:
                name = str(values["display_name"]).strip()
                if not name:
                    raise DomainError("grocery_name_required", "Display name is required.", 422)
                item.display_name = name
                item.normalized_food_name = normalize_food_name(name)
                item.manual_name = True
            if "quantity" in values:
                item.quantity = values["quantity"]
                item.manual_quantity = True
            if "unit" in values:
                unit = values["unit"]
                item.unit_code = str(unit).strip() if unit else None
                item.unit_text = str(unit).strip() if unit else None
                item.manual_quantity = True
            if "checked" in values:
                item.checked = bool(values["checked"])
            if "position" in values:
                position = int(values["position"])
                self._position_available(
                    session, item.grocery_list_id, position, exclude_id=item.id
                )
                item.position = position
            item.version += 1
            item.grocery_list.version += 1
            session.flush()
            return self._item_read(item)

    def remove(self, owner_id: UUID, item_id: UUID, *, expected_version: int) -> None:
        with self._session_factory.begin() as session:
            item = GroceryRepository(session).get_item(owner_id, item_id, for_update=True)
            require_version(expected_version, item.version)
            item.grocery_list.version += 1
            session.execute(delete(GroceryItem).where(GroceryItem.id == item.id))

    @staticmethod
    def mark_dirty(session: Session, meal_plan_id: UUID) -> None:
        grocery_list = GroceryRepository(session).find_for_plan(meal_plan_id, for_update=True)
        if grocery_list is not None and grocery_list.status != "dirty":
            grocery_list.status = "dirty"
            grocery_list.version += 1

    @staticmethod
    def _ingredients(session: Session, plan: MealPlan) -> list[GroceryIngredient]:
        values: list[GroceryIngredient] = []
        for entry in plan.entries:
            if entry.recipe_id is None:
                continue
            recipe = session.get(Recipe, entry.recipe_id)
            if recipe is None:
                continue
            for ingredient in recipe.ingredients:
                values.append(
                    GroceryIngredient(
                        meal_plan_entry_id=entry.id,
                        ingredient_id=ingredient.id,
                        original_text=ingredient.original_text,
                        food_name=ingredient.food_name or ingredient.original_text,
                        quantity=ingredient.quantity_min,
                        unit_code=ingredient.unit_code,
                        unit_text=ingredient.unit_text,
                        planned_servings=entry.servings,
                        recipe_yield=recipe.yield_quantity,
                    )
                )
        return values

    @staticmethod
    def _existing(item: GroceryItem) -> ExistingGroceryItem:
        return ExistingGroceryItem(
            id=item.id,
            normalized_food_name=item.normalized_food_name,
            display_name=item.display_name,
            quantity=item.quantity,
            unit_code=item.unit_code,
            unit_text=item.unit_text,
            aggregation_key=item.aggregation_key,
            origin=item.origin,
            checked=item.checked,
            manual_quantity=item.manual_quantity,
            manual_name=item.manual_name,
            needs_review=item.needs_review,
            position=item.position,
            version=item.version,
            sources=tuple(
                GrocerySource(
                    source.meal_plan_entry_id,
                    source.ingredient_id,
                    source.original_text,
                    source.quantity_contribution,
                )
                for source in item.sources
            ),
        )

    @staticmethod
    def _apply_reconciled(model: GroceryItem, value: ExistingGroceryItem) -> None:
        model.normalized_food_name = value.normalized_food_name
        model.display_name = value.display_name
        model.quantity = value.quantity
        model.unit_code = value.unit_code
        model.unit_text = value.unit_text
        model.aggregation_key = value.aggregation_key
        model.origin = value.origin
        model.checked = value.checked
        model.manual_quantity = value.manual_quantity
        model.manual_name = value.manual_name
        model.needs_review = value.needs_review
        model.position = value.position
        model.version = value.version

    @staticmethod
    def _position_available(
        session: Session,
        grocery_list_id: UUID,
        position: int,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        if position < 0:
            raise DomainError("position_negative", "Position cannot be negative.", 422)
        statement = select(GroceryItem.id).where(
            GroceryItem.grocery_list_id == grocery_list_id,
            GroceryItem.position == position,
        )
        if exclude_id is not None:
            statement = statement.where(GroceryItem.id != exclude_id)
        if session.scalar(statement) is not None:
            raise DomainError("grocery_position_conflict", "Position is already used.", 409)

    @classmethod
    def _item_read(cls, value: GroceryItem) -> GroceryItemRead:
        return GroceryItemRead(
            value.id,
            value.display_name,
            value.quantity,
            value.unit_text,
            value.origin,
            value.checked,
            value.needs_review,
            value.position,
            tuple(
                GrocerySourceRead(
                    source.meal_plan_entry_id,
                    source.original_text,
                    source.quantity_contribution,
                )
                for source in value.sources
            ),
            value.version,
        )

    @classmethod
    def _list_read(cls, value: GroceryList) -> GroceryListRead:
        return GroceryListRead(
            value.id,
            value.meal_plan.week_start,
            value.status,
            value.generated_at,
            tuple(
                cls._item_read(item) for item in sorted(value.items, key=lambda item: item.position)
            ),
            value.version,
        )
