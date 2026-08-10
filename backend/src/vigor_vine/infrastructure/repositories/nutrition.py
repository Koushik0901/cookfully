from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.models.nutrition import (
    IngredientMatch,
    NutritionCorrection,
    NutritionEstimate,
)
from vigor_vine.infrastructure.models.recipes import Recipe
from vigor_vine.infrastructure.models.reference_foods import FoodReference, ReferenceDataset


class NutritionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def active_datasets(self) -> list[ReferenceDataset]:
        return list(
            self.session.scalars(
                select(ReferenceDataset).where(ReferenceDataset.status == "active")
            )
        )

    def search_foods(self, normalized_query: str, *, limit: int = 20) -> list[FoodReference]:
        tokens = [token for token in normalized_query.split() if token]
        if not tokens:
            return []
        name_filter = or_(*(FoodReference.normalized_name.ilike(f"%{token}%") for token in tokens))
        return list(
            self.session.scalars(
                select(FoodReference)
                .join(FoodReference.dataset)
                .where(
                    ReferenceDataset.status == "active",
                    name_filter,
                )
                .options(selectinload(FoodReference.nutrients), selectinload(FoodReference.dataset))
                .limit(limit)
            )
        )

    def active_match(self, ingredient_id: UUID) -> IngredientMatch | None:
        return self.session.scalar(
            select(IngredientMatch).where(
                IngredientMatch.ingredient_id == ingredient_id,
                IngredientMatch.active.is_(True),
            )
        )

    def activate_match(self, match: IngredientMatch) -> IngredientMatch:
        self.session.execute(
            update(IngredientMatch)
            .where(
                IngredientMatch.ingredient_id == match.ingredient_id,
                IngredientMatch.active.is_(True),
            )
            .values(active=False)
        )
        self.session.add(match)
        self.session.flush()
        return match

    def active_corrections(self, recipe_id: UUID) -> list[NutritionCorrection]:
        return list(
            self.session.scalars(
                select(NutritionCorrection).where(
                    NutritionCorrection.recipe_id == recipe_id,
                    NutritionCorrection.active.is_(True),
                )
            )
        )

    def activate_correction(self, correction: NutritionCorrection) -> NutritionCorrection:
        scope = [
            NutritionCorrection.recipe_id == correction.recipe_id,
            NutritionCorrection.field == correction.field,
            NutritionCorrection.active.is_(True),
        ]
        if correction.ingredient_id is None:
            scope.append(NutritionCorrection.ingredient_id.is_(None))
        else:
            scope.append(NutritionCorrection.ingredient_id == correction.ingredient_id)
        self.session.execute(update(NutritionCorrection).where(*scope).values(active=False))
        self.session.add(correction)
        self.session.flush()
        return correction

    def activate_estimate(self, recipe: Recipe, estimate: NutritionEstimate) -> NutritionEstimate:
        if recipe.input_hash != estimate.input_hash:
            raise DomainError(
                "stale_job_input", "Recipe changed while nutrition was calculated.", 409
            )
        self.session.add(estimate)
        self.session.flush()
        recipe.active_estimate_id = estimate.id
        recipe.nutrition_state = estimate.status
        recipe.status = "partial" if estimate.status == "partial" else "ready"
        self.session.flush()
        return estimate
