from __future__ import annotations

import json
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.exports import (
    PortableExportService,
    stage_portable_export,
    verify_portable_export,
)
from cookfully.domain.common import DomainError
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models.grocery import (
    GroceryItem,
    GroceryItemSource,
    GroceryList,
    GroceryShoppingStop,
    RememberedGroceryPlacement,
)
from cookfully.infrastructure.models.identity import OwnerAccount, OwnerOnboardingState
from cookfully.infrastructure.models.media import MediaAsset, RecipePhotoDerivative
from cookfully.infrastructure.models.nutrition import NutritionCorrection
from cookfully.infrastructure.models.owner_foods import OwnerFood
from cookfully.infrastructure.models.pantry import PantryDeduction, PantryItem
from cookfully.infrastructure.models.plans import (
    MealNutritionSnapshot,
    MealPlan,
    MealPlanEntry,
    UserGoal,
)
from cookfully.infrastructure.models.recipes import (
    Ingredient,
    Recipe,
    RecipeCollection,
    RecipeCollectionMembership,
    RecipeInstruction,
    RecipeMealRole,
    RecipeSection,
)
from cookfully.infrastructure.models.semantic_matching import FoodMatchMemory

OWNER_ID = UUID("00000000-0000-7000-8000-000000000001")
ACTIVE_RECIPE_ID = UUID("00000000-0000-7000-8000-000000000010")
COLLECTION_ID = UUID("00000000-0000-7000-8000-000000000020")
SHOPPING_STOP_ID = UUID("00000000-0000-7000-8000-000000000021")
OWNER_FOOD_ID = UUID("00000000-0000-7000-8000-000000000022")
PANTRY_ITEM_ID = UUID("00000000-0000-7000-8000-000000000023")
SECTION_ID = UUID("00000000-0000-7000-8000-000000000024")


def seed_export_graph(factory: sessionmaker[Session], media: MediaStore) -> None:
    stored = media.put(b"safe-image-bytes", "image/png", kind="recipe_image")
    now = datetime(2026, 3, 10, tzinfo=UTC)
    with factory.begin() as session:
        owner = OwnerAccount(
            id=OWNER_ID,
            email="export@example.com",
            display_name="Export",
            password_hash="not-exported-secret",
            timezone="America/Vancouver",
            week_starts_on=1,
        )
        recipe = Recipe(
            id=ACTIVE_RECIPE_ID,
            title="Active bowl",
            yield_quantity=Decimal("2.000"),
            yield_unit="servings",
            status="ready",
            nutrition_state="manual",
            input_hash="sha256:active",
            is_favorite=True,
        )
        session.add_all([owner, recipe])
        session.flush()
        session.add_all(
            [
                OwnerOnboardingState(
                    owner_id=OWNER_ID,
                    state="completed",
                    first_action="create_recipe",
                    reference_data_choice="later",
                    resolved_at=now,
                    version=1,
                ),
                RecipeCollection(
                    id=COLLECTION_ID,
                    owner_id=OWNER_ID,
                    name="Weeknight favourites",
                    position=0,
                    version=1,
                ),
                RecipeCollectionMembership(collection_id=COLLECTION_ID, recipe_id=ACTIVE_RECIPE_ID),
                RecipeMealRole(recipe_id=ACTIVE_RECIPE_ID, role="dinner"),
                GroceryShoppingStop(
                    id=SHOPPING_STOP_ID,
                    owner_id=OWNER_ID,
                    name="Market",
                    position=0,
                    version=1,
                ),
                RememberedGroceryPlacement(
                    owner_id=OWNER_ID,
                    normalized_food_name="tofu",
                    shopping_stop_id=SHOPPING_STOP_ID,
                ),
                OwnerFood(
                    id=OWNER_FOOD_ID,
                    owner_id=OWNER_ID,
                    display_name="House protein blend",
                    normalized_name="house protein blend",
                    brand="Cookfully Pantry",
                    calories_kcal=Decimal("400.000000"),
                    protein_g=Decimal("75.000000"),
                    carbohydrate_g=Decimal("10.000000"),
                    fat_g=Decimal("8.000000"),
                    basis_grams=Decimal("100.000000"),
                    typical_serving_g=Decimal("30.000000"),
                    typical_serving_unit="scoop",
                    is_active=True,
                    version=1,
                    created_at=now,
                    updated_at=now,
                ),
                FoodMatchMemory(
                    owner_id=OWNER_ID,
                    signature_hash="f" * 64,
                    signature={"food": "house protein blend"},
                    owner_food_id=OWNER_FOOD_ID,
                    food_reference_id=None,
                    source_release_id=None,
                    active=True,
                    use_count=3,
                    last_used_at=now,
                ),
                RecipeSection(
                    id=SECTION_ID,
                    recipe_id=ACTIVE_RECIPE_ID,
                    position=0,
                    title="Lentils",
                ),
            ]
        )
        ingredient = Ingredient(
            recipe_id=recipe.id,
            position=0,
            original_text="200 g tofu",
            section_id=SECTION_ID,
            quantity_min=Decimal("200.000000"),
            quantity_max=Decimal("200.000000"),
            unit_code="g",
            unit_text="g",
            food_name="tofu",
            optional=False,
            parse_status="parsed",
            version=1,
        )
        session.add(ingredient)
        session.flush()
        session.add(
            RecipeInstruction(
                recipe_id=recipe.id,
                position=0,
                text="Simmer the lentils until tender.",
                section_id=SECTION_ID,
            )
        )
        session.add(
            NutritionCorrection(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                field="quantity",
                decimal_value=Decimal("210.000000"),
                reason="weighed",
                active=True,
                created_by=owner.id,
            )
        )
        asset = MediaAsset(
            recipe_id=recipe.id,
            kind="recipe_image",
            storage_key=stored.storage_key,
            content_type="image/png",
            byte_size=stored.byte_size,
            sha256=stored.sha256,
            encrypted=False,
        )
        session.add(asset)
        session.flush()
        recipe.image_asset_id = asset.id
        session.add(RecipePhotoDerivative(recipe_id=recipe.id, asset_id=asset.id, role="card"))
        goal = UserGoal(
            owner_id=owner.id,
            mode="maintain",
            maintenance_kcal=Decimal("2200.000000"),
            target_kcal=Decimal("2200.000000"),
            protein_g=Decimal("180.000000"),
            carbohydrate_g=Decimal("220.000000"),
            fat_g=Decimal("65.000000"),
            effective_from=date(2026, 3, 1),
            version=1,
        )
        session.add(goal)
        session.flush()
        plan = MealPlan(
            owner_id=owner.id,
            week_start=date(2026, 3, 9),
            timezone="America/Vancouver",
            goal_id=goal.id,
            version=2,
        )
        snapshot = MealNutritionSnapshot(
            recipe_id=None,
            estimate_id=None,
            basis_servings=Decimal("1.500"),
            calories_kcal=Decimal("752"),
            protein_g=Decimal("60.1"),
            carbohydrate_g=Decimal("90.1"),
            fat_g=Decimal("16.7"),
            nutrition_state="estimated",
            coverage_ratio=Decimal("0.950000"),
        )
        session.add_all([plan, snapshot])
        session.flush()
        entry = MealPlanEntry(
            meal_plan_id=plan.id,
            local_date=date(2026, 3, 9),
            meal_slot="breakfast",
            position=0,
            recipe_id=None,
            recipe_title_snapshot="Deleted protein bowl",
            servings=Decimal("1.500"),
            nutrition_snapshot_id=snapshot.id,
            origin="manual",
            version=1,
        )
        session.add(entry)
        session.flush()
        grocery_list = GroceryList(
            meal_plan_id=plan.id,
            status="completed",
            source_plan_version=plan.version,
            generated_at=now,
            completed_at=now,
            version=1,
        )
        session.add(grocery_list)
        session.flush()
        item = GroceryItem(
            grocery_list_id=grocery_list.id,
            normalized_food_name="tofu",
            display_name="Tofu",
            quantity=Decimal("150.000000"),
            unit_code="g",
            unit_text="g",
            aggregation_key="tofu|mass:g",
            origin="generated",
            checked=True,
            manual_quantity=False,
            manual_name=True,
            needs_review=False,
            position=0,
            version=1,
            shopping_stop_id=SHOPPING_STOP_ID,
        )
        session.add(item)
        session.flush()
        session.add_all(
            [
                GroceryItemSource(
                    grocery_item_id=item.id,
                    meal_plan_entry_id=entry.id,
                    ingredient_id=None,
                    quantity_contribution=Decimal("150.000000"),
                    original_text="200 g tofu from deleted recipe",
                ),
                PantryItem(
                    id=PANTRY_ITEM_ID,
                    owner_id=OWNER_ID,
                    display_name="House protein blend",
                    normalized_food_name="house protein blend",
                    quantity=Decimal("450.000000"),
                    unit_code="g",
                    owner_food_id=OWNER_FOOD_ID,
                    food_reference_id=None,
                    match_status="manual",
                    match_confidence=Decimal("1.000000"),
                    version=1,
                ),
                PantryDeduction(
                    pantry_item_id=PANTRY_ITEM_ID,
                    grocery_item_id=item.id,
                    pantry_quantity=Decimal("50.000000"),
                    pantry_unit="g",
                    grocery_quantity=Decimal("50.000000"),
                    grocery_unit="g",
                    assumption="Cookfully used the owner-confirmed gram equivalent.",
                    status="applied",
                    pantry_version_after=1,
                    grocery_version_after=1,
                    applied_at=now,
                    version=1,
                ),
            ]
        )


def rows(archive: Path, table: str) -> list[dict[str, object]]:
    with zipfile.ZipFile(archive) as bundle:
        payload = bundle.read(f"data/{table}.ndjson").decode("utf-8")
    return [json.loads(line) for line in payload.splitlines() if line]


def test_portable_manifest_decimal_ndjson_detached_history_media_and_staging(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    media = MediaStore(tmp_path / "media", "export-test-secret")
    seed_export_graph(session_factory, media)
    archive = tmp_path / "portable.zip"
    PortableExportService(session_factory, media).create_archive(
        OWNER_ID,
        archive,
        include_media=True,
        created_at=datetime(2026, 3, 12, tzinfo=UTC),
    )
    manifest = verify_portable_export(archive)
    assert manifest["schemaVersion"] == 1
    assert manifest["kind"] == "cookfully-portable-export"
    assert manifest["decimalPolicy"] == {
        "stored": 6,
        "servings": 3,
        "displayCalories": 0,
        "displayMacros": 1,
    }
    assert rows(archive, "recipes")[0]["yield_quantity"] == "2.000"
    assert rows(archive, "ingredients")[0]["quantity_min"] == "200.000000"
    assert rows(archive, "meal_nutrition_snapshots")[0]["protein_g"] == "60.1"
    assert rows(archive, "meal_plan_entries")[0]["recipe_id"] is None
    assert rows(archive, "meal_plan_entries")[0]["recipe_title_snapshot"] == (
        "Deleted protein bowl"
    )
    assert rows(archive, "grocery_item_sources")[0]["original_text"] == (
        "200 g tofu from deleted recipe"
    )
    with zipfile.ZipFile(archive) as bundle:
        media_member = next(name for name in bundle.namelist() if name.startswith("media/"))
        assert bundle.read(media_member) == b"safe-image-bytes"

    staged = stage_portable_export(archive, tmp_path / "stage")
    assert (staged / "manifest.json").is_file()
    with pytest.raises(DomainError, match="already exists"):
        stage_portable_export(archive, tmp_path / "stage")


def test_verifier_rejects_traversal_checksum_tampering_and_merge_policy(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as bundle:
        bundle.writestr("../outside", "bad")
        bundle.writestr("manifest.json", "{}")
    with pytest.raises(DomainError, match="unsafe archive member"):
        verify_portable_export(traversal)

    archive = tmp_path / "tampered.zip"
    manifest = {
        "schemaVersion": 1,
        "kind": "cookfully-portable-export",
        "mergePolicy": "owner-scoped-upsert",
        "files": [{"path": "data/recipes.ndjson", "sha256": "0" * 64, "bytes": 3}],
    }
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("data/recipes.ndjson", "bad")
        bundle.writestr("manifest.json", json.dumps(manifest))
    with pytest.raises(DomainError, match="checksum"):
        verify_portable_export(archive)
