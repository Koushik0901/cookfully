from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.plans import MealPlan, MealPlanEntry, UserGoal


class GoalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def effective_or_none(
        self, owner_id: UUID, on_date: date, *, for_update: bool = False
    ) -> UserGoal | None:
        statement = (
            select(UserGoal)
            .where(
                UserGoal.owner_id == owner_id,
                UserGoal.effective_from <= on_date,
                or_(UserGoal.effective_to.is_(None), UserGoal.effective_to >= on_date),
            )
            .options(selectinload(UserGoal.meal_targets))
            .order_by(UserGoal.effective_from.desc())
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def effective(self, owner_id: UUID, on_date: date, *, for_update: bool = False) -> UserGoal:
        goal = self.effective_or_none(owner_id, on_date, for_update=for_update)
        if goal is None:
            raise DomainError("goal_not_found", "No goal is effective on that date.", 404)
        return goal

    def starting(
        self, owner_id: UUID, effective_from: date, *, for_update: bool = False
    ) -> UserGoal | None:
        statement = (
            select(UserGoal)
            .where(UserGoal.owner_id == owner_id, UserGoal.effective_from == effective_from)
            .options(selectinload(UserGoal.meal_targets))
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def overlaps(
        self,
        owner_id: UUID,
        effective_from: date,
        effective_to: date | None,
        *,
        exclude_id: UUID | None = None,
    ) -> bool:
        statement = select(UserGoal.id).where(
            UserGoal.owner_id == owner_id,
            UserGoal.effective_from <= (effective_to or date.max),
            or_(UserGoal.effective_to.is_(None), UserGoal.effective_to >= effective_from),
        )
        if exclude_id is not None:
            statement = statement.where(UserGoal.id != exclude_id)
        return self.session.scalar(statement.limit(1)) is not None


class MealPlanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_week(self, owner_id: UUID, week_start: date, *, for_update: bool = False) -> MealPlan:
        statement = (
            select(MealPlan)
            .where(MealPlan.owner_id == owner_id, MealPlan.week_start == week_start)
            .options(
                selectinload(MealPlan.goal).selectinload(UserGoal.meal_targets),
                selectinload(MealPlan.entries).selectinload(MealPlanEntry.nutrition_snapshot),
                selectinload(MealPlan.grocery_list),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        plan = self.session.scalar(statement)
        if plan is None:
            raise DomainError("meal_plan_not_found", "Meal plan was not found.", 404)
        return plan

    def find_week(self, owner_id: UUID, week_start: date) -> MealPlan | None:
        return self.session.scalar(
            select(MealPlan)
            .where(MealPlan.owner_id == owner_id, MealPlan.week_start == week_start)
            .options(
                selectinload(MealPlan.goal).selectinload(UserGoal.meal_targets),
                selectinload(MealPlan.entries).selectinload(MealPlanEntry.nutrition_snapshot),
                selectinload(MealPlan.grocery_list),
            )
        )

    def get_entry(
        self, owner_id: UUID, entry_id: UUID, *, for_update: bool = False
    ) -> MealPlanEntry:
        statement = (
            select(MealPlanEntry)
            .join(MealPlanEntry.meal_plan)
            .where(MealPlan.owner_id == owner_id, MealPlanEntry.id == entry_id)
            .options(
                selectinload(MealPlanEntry.meal_plan)
                .selectinload(MealPlan.goal)
                .selectinload(UserGoal.meal_targets),
                selectinload(MealPlanEntry.nutrition_snapshot),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        entry = self.session.scalar(statement)
        if entry is None:
            raise DomainError("meal_plan_entry_not_found", "Meal plan entry was not found.", 404)
        return entry
