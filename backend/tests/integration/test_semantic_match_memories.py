from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.corrections import CorrectionService
from cookfully.application.food_match_memories import (
    forget_food_reference,
    remember_food_reference,
    remembered_food_reference,
)
from cookfully.domain.common import uuid7
from cookfully.domain.ingredient_nutrition.matching import FoodMatcher, normalize_food
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.recipes import Ingredient, Recipe
from cookfully.infrastructure.models.reference_foods import (
    FoodNutrient,
    FoodReference,
    ReferenceDataset,
)


def build_dataset(session: Session, *, release_id: str, status: str = "active") -> ReferenceDataset:
    dataset = ReferenceDataset(
        id=uuid7(),
        provider="usda_fdc",
        dataset_type="foundation",
        release_id=release_id,
        released_on=datetime.now(UTC).date(),
        imported_at=datetime.now(UTC),
        source_url="https://fdc.nal.usda.gov/",
        license="CC0-1.0",
        status=status,
        checked_at=datetime.now(UTC),
        activated_at=datetime.now(UTC) if status == "active" else None,
        superseded_at=datetime.now(UTC) if status == "superseded" else None,
    )
    session.add(dataset)
    session.flush()
    return dataset


def build_food(
    session: Session, dataset: ReferenceDataset, *, external_id: str, name: str
) -> FoodReference:
    food = FoodReference(
        id=uuid7(),
        dataset=dataset,
        external_id=external_id,
        description=name,
        normalized_name=normalize_food(name),
        data_type="foundation",
        basis_grams=Decimal("100.000000"),
        nutrients=[
            FoodNutrient(nutrient_code="1008", amount=Decimal("100"), unit="kcal"),
            FoodNutrient(nutrient_code="1003", amount=Decimal("20"), unit="g"),
            FoodNutrient(nutrient_code="1005", amount=Decimal("5"), unit="g"),
            FoodNutrient(nutrient_code="1004", amount=Decimal("2"), unit="g"),
        ],
    )
    session.add(food)
    session.flush()
    return food


def build_owner(session: Session, *, email: str) -> OwnerAccount:
    owner = OwnerAccount(
        email=email,
        display_name="Owner",
        password_hash="not-used",
        timezone="UTC",
        week_starts_on=1,
    )
    session.add(owner)
    session.flush()
    return owner


def build_ingredient(session: Session, *, food_name: str) -> Ingredient:
    recipe = Recipe(
        title="Test recipe",
        yield_quantity=Decimal("2.000"),
        yield_unit="servings",
        status="ready",
        nutrition_state="estimated",
        input_hash="sha256:test",
    )
    session.add(recipe)
    session.flush()
    ingredient = Ingredient(
        recipe_id=recipe.id,
        position=1,
        original_text=food_name,
        food_name=food_name,
        parse_status="parsed",
        version=1,
    )
    session.add(ingredient)
    session.flush()
    return ingredient


class FoodRepositoryStub:
    def __init__(self, foods: list[FoodReference]) -> None:
        self.foods = foods

    def search_foods(self, normalized_query: str, *, limit: int = 20) -> list[FoodReference]:
        del normalized_query
        return self.foods[:limit]


def test_remembered_match_is_owner_scoped(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        owner = build_owner(session, email="owner-a@example.com")
        other = build_owner(session, email="owner-b@example.com")
        dataset = build_dataset(session, release_id="foundation-2026-04")
        food = build_food(session, dataset, external_id="1", name="Chicken breast")
        ingredient = build_ingredient(session, food_name="chicken breast")

        memory = remember_food_reference(
            session, owner_id=owner.id, ingredient=ingredient, food=food
        )

        assert memory.food_reference_id == food.id
        assert remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient) is food
        assert remembered_food_reference(session, owner_id=other.id, ingredient=ingredient) is None


def test_remembering_same_concept_updates_food_reference(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        owner = build_owner(session, email="owner-update@example.com")
        dataset = build_dataset(session, release_id="foundation-2026-04")
        first = build_food(session, dataset, external_id="1", name="Chicken breast")
        second = build_food(session, dataset, external_id="2", name="Chicken thigh")
        ingredient = build_ingredient(session, food_name="chicken breast")

        remember_food_reference(session, owner_id=owner.id, ingredient=ingredient, food=first)
        remember_food_reference(session, owner_id=owner.id, ingredient=ingredient, food=second)

        assert (
            remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient) is second
        )


def test_memory_does_not_generalize_across_concept_signature(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        owner = build_owner(session, email="owner-scope@example.com")
        dataset = build_dataset(session, release_id="foundation-2026-04")
        plain = build_food(session, dataset, external_id="1", name="Chicken breast")
        tandoori = build_food(session, dataset, external_id="2", name="Chicken breast, roasted")
        plain_ingredient = build_ingredient(session, food_name="chicken")
        tandoori_ingredient = build_ingredient(session, food_name="tandoori chicken")

        remember_food_reference(session, owner_id=owner.id, ingredient=plain_ingredient, food=plain)

        assert (
            remembered_food_reference(session, owner_id=owner.id, ingredient=plain_ingredient)
            is plain
        )
        assert (
            remembered_food_reference(session, owner_id=owner.id, ingredient=tandoori_ingredient)
            is None
        )

        remember_food_reference(
            session, owner_id=owner.id, ingredient=tandoori_ingredient, food=tandoori
        )

        assert (
            remembered_food_reference(session, owner_id=owner.id, ingredient=tandoori_ingredient)
            is tandoori
        )
        assert (
            remembered_food_reference(session, owner_id=owner.id, ingredient=plain_ingredient)
            is plain
        )


def test_memory_is_revalidated_against_active_dataset_release(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        owner = build_owner(session, email="owner-release@example.com")
        old_release = build_dataset(session, release_id="foundation-2026-04")
        food = build_food(session, old_release, external_id="1", name="Chicken breast")
        ingredient = build_ingredient(session, food_name="chicken breast")

        remember_food_reference(session, owner_id=owner.id, ingredient=ingredient, food=food)
        assert remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient) is food

        old_release.status = "superseded"
        old_release.activated_at = None
        old_release.superseded_at = datetime.now(UTC)
        new_release = build_dataset(session, release_id="foundation-2026-10")

        assert remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient) is None
        assert new_release.status == "active"


def test_remembered_match_never_overrides_hard_contradiction(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        owner = build_owner(session, email="owner-contradiction@example.com")
        dataset = build_dataset(session, release_id="foundation-2026-04")
        tofu = build_food(session, dataset, external_id="1", name="Tofu, firm")
        chicken = build_food(session, dataset, external_id="2", name="Chicken breast")
        ingredient = build_ingredient(session, food_name="chicken")

        remember_food_reference(session, owner_id=owner.id, ingredient=ingredient, food=tofu)
        remembered = remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient)
        assert remembered is tofu

        matcher = FoodMatcher(FoodRepositoryStub([chicken, tofu]))  # type: ignore[arg-type]
        decision = matcher.decide("chicken", preferred_food=tofu)

        assert not (decision.status == "matched" and decision.method == "memory")
        assert decision.method != "memory"


def test_remembering_bumps_use_count(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        owner = build_owner(session, email="owner-count@example.com")
        dataset = build_dataset(session, release_id="foundation-2026-04")
        food = build_food(session, dataset, external_id="1", name="Chicken breast")
        ingredient = build_ingredient(session, food_name="chicken breast")

        remember_food_reference(session, owner_id=owner.id, ingredient=ingredient, food=food)
        remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient)
        remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient)

        from sqlalchemy import select

        from cookfully.infrastructure.models.semantic_matching import FoodMatchMemory

        memory = session.scalar(select(FoodMatchMemory).where(FoodMatchMemory.owner_id == owner.id))
        assert memory is not None
        assert memory.use_count == 2


def test_forget_deactivates_memory_for_owner(session_factory: sessionmaker[Session]) -> None:
    with session_factory.begin() as session:
        owner = build_owner(session, email="owner-forget@example.com")
        dataset = build_dataset(session, release_id="foundation-2026-04")
        food = build_food(session, dataset, external_id="1", name="Chicken breast")
        ingredient = build_ingredient(session, food_name="chicken breast")

        remember_food_reference(session, owner_id=owner.id, ingredient=ingredient, food=food)
        assert remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient) is food

        forget_food_reference(session, owner_id=owner.id, ingredient=ingredient)

        assert remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient) is None


def test_correction_without_remember_match_is_one_off(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        owner = build_owner(session, email="owner-once@example.com")
        dataset = build_dataset(session, release_id="foundation-2026-04")
        food = build_food(session, dataset, external_id="1", name="Chicken breast")
        ingredient = build_ingredient(session, food_name="chicken breast")
        recipe_id = ingredient.recipe_id

    service = CorrectionService(session_factory)
    service.activate(
        recipe_id=recipe_id,
        ingredient_id=ingredient.id,
        field="food_reference",
        created_by=owner.id,
        reference_id_value=food.id,
        remember_match=False,
    )

    with session_factory() as session:
        assert remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient) is None


def test_correction_with_remember_match_creates_memory(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        owner = build_owner(session, email="owner-remember@example.com")
        dataset = build_dataset(session, release_id="foundation-2026-04")
        food = build_food(session, dataset, external_id="1", name="Chicken breast")
        ingredient = build_ingredient(session, food_name="chicken breast")
        recipe_id = ingredient.recipe_id

    service = CorrectionService(session_factory)
    service.activate(
        recipe_id=recipe_id,
        ingredient_id=ingredient.id,
        field="food_reference",
        created_by=owner.id,
        reference_id_value=food.id,
        remember_match=True,
    )

    with session_factory() as session:
        remembered = remembered_food_reference(session, owner_id=owner.id, ingredient=ingredient)
        assert remembered is not None and remembered.id == food.id
