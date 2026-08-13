from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.grocery import GroceryItem, GroceryList
from cookfully.infrastructure.models.plans import MealPlan


class GroceryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_for_plan(self, meal_plan_id: UUID, *, for_update: bool = False) -> GroceryList | None:
        statement = (
            select(GroceryList)
            .where(GroceryList.meal_plan_id == meal_plan_id)
            .options(
                selectinload(GroceryList.items).selectinload(GroceryItem.sources),
                selectinload(GroceryList.items).selectinload(GroceryItem.shopping_stop),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def get_for_week(
        self, owner_id: UUID, week_start: date, *, for_update: bool = False
    ) -> GroceryList:
        statement = (
            select(GroceryList)
            .join(GroceryList.meal_plan)
            .where(MealPlan.owner_id == owner_id, MealPlan.week_start == week_start)
            .options(
                selectinload(GroceryList.items).selectinload(GroceryItem.sources),
                selectinload(GroceryList.items).selectinload(GroceryItem.shopping_stop),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        value = self.session.scalar(statement)
        if value is None:
            raise DomainError("grocery_list_not_found", "Grocery list was not found.", 404)
        return value

    def get_item(self, owner_id: UUID, item_id: UUID, *, for_update: bool = False) -> GroceryItem:
        statement = (
            select(GroceryItem)
            .join(GroceryItem.grocery_list)
            .join(GroceryList.meal_plan)
            .where(MealPlan.owner_id == owner_id, GroceryItem.id == item_id)
            .options(
                selectinload(GroceryItem.sources),
                selectinload(GroceryItem.grocery_list).selectinload(GroceryList.items),
                selectinload(GroceryItem.shopping_stop),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        value = self.session.scalar(statement)
        if value is None:
            raise DomainError("grocery_item_not_found", "Grocery item was not found.", 404)
        return value
