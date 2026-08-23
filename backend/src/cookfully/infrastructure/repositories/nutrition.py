from uuid import UUID

from sqlalchemy import Text, and_, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import ARRAY, array
from sqlalchemy.orm import Session, selectinload

from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.nutrition import (
    IngredientMatch,
    NutritionCorrection,
    NutritionEstimate,
)
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.models.reference_foods import FoodReference, ReferenceDataset


def _token_variants(token: str) -> list[str]:
    """Singular/plural spellings of a query token for containment ordering.

    Mirrors domain.ingredient_nutrition.normalization.singularize — kept in
    infrastructure to avoid importing domain into the repository layer.
    Covered by tests/unit/test_normalization_sync.py
    """

    if token.endswith("ies") and len(token) > 4:
        singular = token[:-3] + "y"
    elif token.endswith("s") and len(token) > 3 and not token.endswith(("ss", "us", "is")):
        singular = token[:-1]
    else:
        singular = token
    return sorted({token, singular, token + "s"})


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
        token_array = func.string_to_array(FoodReference.normalized_name, " ")
        contains_all = and_(
            *(
                token_array.op("&&")(cast(array(_token_variants(token)), ARRAY(Text())))
                for token in tokens
            )
        )
        token_count = func.array_length(token_array, 1)
        return list(
            self.session.scalars(
                select(FoodReference)
                .join(FoodReference.dataset)
                .where(
                    ReferenceDataset.status == "active",
                    name_filter,
                )
                .order_by(
                    contains_all.desc(),
                    token_count.asc(),
                    func.char_length(FoodReference.normalized_name).asc(),
                    FoodReference.external_id.asc(),
                )
                .options(selectinload(FoodReference.nutrients), selectinload(FoodReference.dataset))
                .limit(limit)
            )
        )

    def search_foods_for_matching(
        self, normalized_query: str, *, limit: int = 256
    ) -> list[FoodReference]:
        """Return a lightweight lexical shortlist for semantic ranking.

        Interactive matching only needs the food identity and serving metadata;
        loading every nutrient relationship for the shortlist adds avoidable
        database work before the embedder can rank the candidates.
        """
        tokens = [token for token in normalized_query.split() if token]
        if not tokens:
            return []
        name_filter = or_(*(FoodReference.normalized_name.ilike(f"%{token}%") for token in tokens))
        token_array = func.string_to_array(FoodReference.normalized_name, " ")
        contains_all = and_(
            *(
                token_array.op("&&")(cast(array(_token_variants(token)), ARRAY(Text())))
                for token in tokens
            )
        )
        token_count = func.array_length(token_array, 1)
        return list(
            self.session.scalars(
                select(FoodReference)
                .join(FoodReference.dataset)
                .where(
                    ReferenceDataset.status == "active",
                    name_filter,
                )
                .order_by(
                    contains_all.desc(),
                    token_count.asc(),
                    func.char_length(FoodReference.normalized_name).asc(),
                    FoodReference.external_id.asc(),
                )
                .limit(limit)
            )
        )

    def list_active_foods(self) -> list[FoodReference]:
        return list(
            self.session.scalars(
                select(FoodReference)
                .join(FoodReference.dataset)
                .where(ReferenceDataset.status == "active")
                .options(selectinload(FoodReference.dataset))
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
