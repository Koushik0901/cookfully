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
from cookfully.domain.expiry_lifespans import resolve_expiry
from cookfully.domain.grocery import (
    GroceryIngredient,
    GrocerySource,
    aggregate_grocery_ingredients,
    normalize_food_name,
)
from cookfully.infrastructure.models.grocery import (
    GroceryItem,
    GroceryItemSource,
    GroceryList,
    GroceryShoppingStop,
    RememberedGroceryPlacement,
)
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
    shopping_stop_id: UUID | None
    shopping_stop_name: str | None
    shopping_stop_position: int | None
    shopping_stop_version: int | None
    sources: tuple[GrocerySourceRead, ...]
    version: int
    purchased_at: datetime | None = None
    expires_on: date | None = None
    expiry_source: str | None = None
    needs_expiry_date: bool = False


@dataclass(frozen=True, slots=True)
class GroceryListRead:
    id: UUID
    week_start: date
    status: str
    generated_at: datetime | None
    completed_at: datetime | None
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
                if grocery_list.status == "completed":
                    raise DomainError(
                        "grocery_list_completed",
                        "Reopen this completed shopping pass before refreshing it.",
                        409,
                    )
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
                if model.id is None:
                    remembered_stop_id = session.scalar(
                        select(RememberedGroceryPlacement.shopping_stop_id).where(
                            RememberedGroceryPlacement.owner_id == owner_id,
                            RememberedGroceryPlacement.normalized_food_name
                            == value.normalized_food_name,
                        )
                    )
                    if (
                        value.origin == "generated"
                        and not value.manual_name
                        and not value.needs_review
                        and remembered_stop_id is not None
                    ):
                        model.shopping_stop_id = remembered_stop_id
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
            grocery_list.completed_at = None
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
            self._ensure_active(grocery_list)
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
            self._ensure_active(item.grocery_list)
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
            # validate expiry range if provided
            if "expires_on" in values and values["expires_on"] is not None:
                today = utc_now().date()
                exp = values["expires_on"]
                if not (today <= exp <= date.fromordinal(today.toordinal() + 90)):
                    raise DomainError(
                        "expiry_out_of_range", "Expiry must be within 0-90 days from today.", 422
                    )
            handled_via_checked = False
            old_checked = bool(item.checked)
            new_checked: bool | None = None
            if "checked" in values:
                new_checked = bool(values["checked"])
                if new_checked and not old_checked:
                    # transitioning false -> true
                    requested = values.get("expires_on")
                    handled_via_checked = requested is not None
                    if item.expiry_source == "manual":
                        if requested is not None:
                            item.expires_on = requested
                            item.expiry_source = "manual"
                            item.purchased_at = utc_now()
                        else:
                            if item.purchased_at is None:
                                item.purchased_at = utc_now()
                    else:
                        if requested is not None:
                            # client provided date -> label on first prompt, manual on later edits
                            source_label = "label" if item.expiry_source is None else "manual"
                            item.expires_on = requested
                            item.expiry_source = source_label
                            item.purchased_at = utc_now()
                        else:
                            r_expires_on, r_source, r_purchased_at, r_needs = resolve_expiry(
                                item.display_name,
                                requested_expires_on=None,
                                today=utc_now().date(),
                            )
                            if r_expires_on is not None:
                                item.expires_on = r_expires_on
                                item.expiry_source = r_source  # auto
                                item.purchased_at = r_purchased_at
                            elif r_needs:
                                # leave null, signal via response computed field
                                item.purchased_at = utc_now()
                                item.expires_on = None
                                item.expiry_source = None
                            else:
                                if item.purchased_at is None:
                                    item.purchased_at = utc_now()
                                item.expires_on = None
                                item.expiry_source = None
                elif not new_checked and old_checked:
                    item.purchased_at = None
                    item.expires_on = None
                    item.expiry_source = None
                item.checked = new_checked
            # handle expires_on without checked transition (standalone expiry edit)
            if "expires_on" in values and values["expires_on"] is not None:
                if "checked" not in values:
                    # first time with label-required -> label, later edits -> manual
                    if item.expiry_source == "manual" or item.expiry_source == "label":
                        item.expiry_source = "manual"
                    else:
                        item.expiry_source = "label"
                    item.expires_on = values["expires_on"]
                    if item.purchased_at is None:
                        item.purchased_at = utc_now()
                elif (
                    new_checked is not None
                    and old_checked
                    and new_checked
                    and not handled_via_checked
                ):
                    # already checked, now editing expiry (manual edit while staying checked)
                    if item.expiry_source == "manual" or item.expiry_source == "label":
                        item.expiry_source = "manual"
                    else:
                        item.expiry_source = "label"
                    item.expires_on = values["expires_on"]
                    if item.purchased_at is None:
                        item.purchased_at = utc_now()
            if "position" in values:
                position = int(values["position"])
                self._position_available(
                    session, item.grocery_list_id, position, exclude_id=item.id
                )
                item.position = position
            if "shopping_stop_id" in values:
                stop_id = values["shopping_stop_id"]
                if stop_id is not None:
                    item.shopping_stop = self._require_stop(session, owner_id, stop_id)
                else:
                    item.shopping_stop = None
            if values.get("remember_placement"):
                if item.shopping_stop_id is None:
                    raise DomainError(
                        "grocery_placement_required",
                        "Choose a shopping stop before remembering it.",
                        422,
                    )
                if item.origin != "generated" or item.manual_name or item.needs_review:
                    raise DomainError(
                        "grocery_placement_not_safe",
                        "Only clear generated items can be remembered for a future stop.",
                        422,
                    )
                placement = session.scalar(
                    select(RememberedGroceryPlacement).where(
                        RememberedGroceryPlacement.owner_id == owner_id,
                        RememberedGroceryPlacement.normalized_food_name
                        == item.normalized_food_name,
                    )
                )
                if placement is None:
                    session.add(
                        RememberedGroceryPlacement(
                            owner_id=owner_id,
                            normalized_food_name=item.normalized_food_name,
                            shopping_stop_id=item.shopping_stop_id,
                        )
                    )
                else:
                    placement.shopping_stop_id = item.shopping_stop_id
            item.version += 1
            item.grocery_list.version += 1
            session.flush()
            return self._item_read(item)

    def remove(self, owner_id: UUID, item_id: UUID, *, expected_version: int) -> None:
        with self._session_factory.begin() as session:
            item = GroceryRepository(session).get_item(owner_id, item_id, for_update=True)
            self._ensure_active(item.grocery_list)
            require_version(expected_version, item.version)
            item.grocery_list.version += 1
            session.execute(delete(GroceryItem).where(GroceryItem.id == item.id))

    @staticmethod
    def mark_dirty(session: Session, meal_plan_id: UUID) -> None:
        grocery_list = GroceryRepository(session).find_for_plan(meal_plan_id, for_update=True)
        if grocery_list is not None and grocery_list.status not in {"dirty", "completed"}:
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
            shopping_stop_id=item.shopping_stop_id,
            sources=tuple(
                GrocerySource(
                    source.meal_plan_entry_id,
                    source.ingredient_id,
                    source.original_text,
                    source.quantity_contribution,
                )
                for source in item.sources
            ),
            purchased_at=item.purchased_at,
            expires_on=item.expires_on,
            expiry_source=item.expiry_source,
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
        model.shopping_stop_id = value.shopping_stop_id
        # preserve manual expiry through generate/regenerate: existing expiry survives
        model.purchased_at = value.purchased_at
        model.expires_on = value.expires_on
        model.expiry_source = value.expiry_source

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
        from cookfully.domain.expiry_lifespans import is_label_required

        needs_expiry_date = bool(
            value.checked and value.expires_on is None and is_label_required(value.display_name)
        )
        return GroceryItemRead(
            value.id,
            value.display_name,
            value.quantity,
            value.unit_text,
            value.origin,
            value.checked,
            value.needs_review,
            value.position,
            value.shopping_stop_id,
            value.shopping_stop.name if value.shopping_stop is not None else None,
            value.shopping_stop.position if value.shopping_stop is not None else None,
            value.shopping_stop.version if value.shopping_stop is not None else None,
            tuple(
                GrocerySourceRead(
                    source.meal_plan_entry_id,
                    source.original_text,
                    source.quantity_contribution,
                )
                for source in value.sources
            ),
            value.version,
            purchased_at=value.purchased_at,
            expires_on=value.expires_on,
            expiry_source=value.expiry_source,
            needs_expiry_date=needs_expiry_date,
        )

    @classmethod
    def _list_read(cls, value: GroceryList) -> GroceryListRead:
        return GroceryListRead(
            value.id,
            value.meal_plan.week_start,
            value.status,
            value.generated_at,
            value.completed_at,
            tuple(
                cls._item_read(item) for item in sorted(value.items, key=lambda item: item.position)
            ),
            value.version,
        )

    def complete(
        self, owner_id: UUID, week_start: date, *, expected_version: int
    ) -> GroceryListRead:
        with self._session_factory.begin() as session:
            grocery_list = GroceryRepository(session).get_for_week(
                owner_id, week_start, for_update=True
            )
            require_version(expected_version, grocery_list.version)
            if grocery_list.status == "completed":
                return self._list_read(grocery_list)
            if grocery_list.status != "current":
                raise DomainError(
                    "grocery_list_not_current",
                    "Refresh this list before finishing the shopping pass.",
                    409,
                )
            if any(not item.checked for item in grocery_list.items):
                raise DomainError(
                    "grocery_items_remaining",
                    "Check off every item before finishing this shopping pass.",
                    422,
                )
            grocery_list.status = "completed"
            grocery_list.completed_at = utc_now()
            grocery_list.version += 1
            session.flush()
            return self._list_read(grocery_list)

    def reopen(self, owner_id: UUID, week_start: date, *, expected_version: int) -> GroceryListRead:
        with self._session_factory.begin() as session:
            grocery_list = GroceryRepository(session).get_for_week(
                owner_id, week_start, for_update=True
            )
            require_version(expected_version, grocery_list.version)
            if grocery_list.status != "completed":
                raise DomainError(
                    "grocery_list_not_completed",
                    "Only a completed shopping pass can be reopened.",
                    409,
                )
            grocery_list.status = "current"
            grocery_list.completed_at = None
            grocery_list.version += 1
            session.flush()
            return self._list_read(grocery_list)

    @staticmethod
    def _ensure_active(grocery_list: GroceryList) -> None:
        if grocery_list.status == "completed":
            raise DomainError(
                "grocery_list_completed", "Reopen this completed shopping pass to change it.", 409
            )

    @staticmethod
    def _require_stop(session: Session, owner_id: UUID, stop_id: object) -> GroceryShoppingStop:
        stop = session.get(GroceryShoppingStop, stop_id) if isinstance(stop_id, UUID) else None
        if stop is None:
            raise DomainError("shopping_stop_not_found", "Shopping stop was not found.", 404)
        if stop.owner_id != owner_id:
            raise DomainError("shopping_stop_not_found", "Shopping stop was not found.", 404)
        return stop
