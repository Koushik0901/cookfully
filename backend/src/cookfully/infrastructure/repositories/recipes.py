from uuid import UUID

from sqlalchemy import Select, and_, delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.recipes import (
    Ingredient,
    Recipe,
    RecipeCollectionMembership,
    RecipeInstruction,
    RecipeMealRole,
)


class RecipeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, recipe: Recipe) -> Recipe:
        self.session.add(recipe)
        self.session.flush()
        return recipe

    def get(self, recipe_id: UUID, *, for_update: bool = False) -> Recipe:
        statement = (
            select(Recipe)
            .where(Recipe.id == recipe_id)
            .options(
                selectinload(Recipe.ingredients),
                selectinload(Recipe.instructions),
                selectinload(Recipe.collection_memberships).selectinload(
                    RecipeCollectionMembership.collection
                ),
                selectinload(Recipe.meal_roles),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        recipe = self.session.scalar(statement)
        if recipe is None:
            raise DomainError("recipe_not_found", "Recipe was not found.", 404)
        return recipe

    def list_recipes(
        self,
        *,
        query: str | None = None,
        nutrition_state: str | None = None,
        favorite: bool | None = None,
        collection_id: UUID | None = None,
        meal_role: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        after: tuple[str, UUID] | None = None,
    ) -> list[Recipe]:
        statement: Select[tuple[Recipe]] = select(Recipe).options(
            selectinload(Recipe.ingredients),
            selectinload(Recipe.instructions),
            selectinload(Recipe.collection_memberships).selectinload(
                RecipeCollectionMembership.collection
            ),
            selectinload(Recipe.meal_roles),
        )
        # Import placeholders are workflow state, not recipes. Keep both new
        # import_failed rows and legacy failed placeholders out of every library view.
        statement = statement.where(
            ~and_(
                Recipe.title == "Importing recipe",
                Recipe.status.in_(("failed", "import_failed")),
            )
        )
        if not include_archived:
            statement = statement.where(Recipe.status != "archived")
        if query:
            statement = statement.where(Recipe.title.ilike(f"%{query.strip()}%"))
        if nutrition_state:
            statement = statement.where(Recipe.nutrition_state == nutrition_state)
        if favorite is not None:
            statement = statement.where(Recipe.is_favorite.is_(favorite))
        if collection_id is not None:
            statement = statement.join(Recipe.collection_memberships).where(
                RecipeCollectionMembership.collection_id == collection_id
            )
        if meal_role is not None:
            statement = statement.join(Recipe.meal_roles).where(RecipeMealRole.role == meal_role)
        if after is not None:
            after_title, after_id = after
            statement = statement.where(
                or_(
                    func.lower(Recipe.title) > after_title,
                    and_(func.lower(Recipe.title) == after_title, Recipe.id > after_id),
                )
            )
        return list(
            self.session.scalars(
                statement.order_by(func.lower(Recipe.title), Recipe.id).limit(limit)
            )
        )

    def replace_content(
        self,
        recipe: Recipe,
        ingredients: list[Ingredient],
        instructions: list[RecipeInstruction],
    ) -> None:
        recipe.ingredients.clear()
        recipe.instructions.clear()
        # Ordered children have a unique (recipe_id, position) key. Flush orphan
        # deletions before inserting replacements so a same-position edit cannot
        # collide with the row it replaces.
        self.session.flush()
        recipe.ingredients.extend(ingredients)
        recipe.instructions.extend(instructions)
        self.session.flush()

    def permanently_delete(self, recipe: Recipe) -> None:
        self.session.execute(delete(Recipe).where(Recipe.id == recipe.id))
