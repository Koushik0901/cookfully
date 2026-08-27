from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker
from tests.contract.test_export_format import (
    ACTIVE_RECIPE_ID,
    COLLECTION_ID,
    OWNER_FOOD_ID,
    OWNER_ID,
    PANTRY_ITEM_ID,
    SHOPPING_STOP_ID,
    rows,
    seed_export_graph,
)

from cookfully.application.exports import (
    PortableExportService,
    stage_portable_export,
    verify_portable_export,
)
from cookfully.infrastructure.media_store import MediaStore


def test_portable_export_keeps_the_first_kitchen_profile_graph_and_cover(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    media = MediaStore(tmp_path / "media", "portable-first-kitchen-secret")
    seed_export_graph(session_factory, media)
    archive = tmp_path / "portable-first-kitchen.zip"

    PortableExportService(session_factory, media).create_archive(
        OWNER_ID,
        archive,
        include_media=True,
        created_at=datetime(2026, 3, 12, tzinfo=UTC),
    )

    manifest = verify_portable_export(archive)
    assert manifest["ownerId"] == str(OWNER_ID)
    recipe = rows(archive, "recipes")[0]
    assert recipe["id"] == str(ACTIVE_RECIPE_ID)
    assert recipe["is_favorite"] is True
    assert rows(archive, "recipe_sections")[0]["title"] == "Lentils"
    assert rows(archive, "recipe_instructions")[0]["text"] == "Simmer the lentils until tender."
    assert rows(archive, "recipe_photo_derivatives")[0]["recipe_id"] == str(ACTIVE_RECIPE_ID)
    assert rows(archive, "owner_onboarding_states") == [
        {
            "owner_id": str(OWNER_ID),
            "state": "completed",
            "first_action": "create_recipe",
            "reference_data_choice": "later",
            "resolved_at": "2026-03-10T00:00:00Z",
            "version": 1,
        }
    ]
    assert rows(archive, "recipe_collections")[0]["id"] == str(COLLECTION_ID)
    assert rows(archive, "recipe_collection_memberships")[0]["recipe_id"] == str(ACTIVE_RECIPE_ID)
    role = rows(archive, "recipe_meal_roles")[0]
    assert role["recipe_id"] == str(ACTIVE_RECIPE_ID)
    assert role["role"] == "dinner"
    assert rows(archive, "grocery_lists")[0]["status"] == "completed"
    assert rows(archive, "grocery_shopping_stops")[0]["id"] == str(SHOPPING_STOP_ID)
    assert rows(archive, "remembered_grocery_placements")[0]["shopping_stop_id"] == str(
        SHOPPING_STOP_ID
    )
    assert rows(archive, "grocery_items")[0]["shopping_stop_id"] == str(SHOPPING_STOP_ID)
    assert rows(archive, "owner_foods")[0]["id"] == str(OWNER_FOOD_ID)
    assert rows(archive, "food_match_memories")[0]["owner_food_id"] == str(OWNER_FOOD_ID)
    assert rows(archive, "pantry_items")[0]["id"] == str(PANTRY_ITEM_ID)
    assert rows(archive, "pantry_deductions")[0]["pantry_item_id"] == str(PANTRY_ITEM_ID)

    staged = stage_portable_export(archive, tmp_path / "staged-portable-first-kitchen")
    recipe_image = rows(archive, "media_assets")[0]["storage_key"]
    assert (staged / "media" / str(recipe_image)).read_bytes() == b"safe-image-bytes"
