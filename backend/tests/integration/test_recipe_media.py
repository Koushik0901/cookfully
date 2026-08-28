from __future__ import annotations

import zipfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import UUID

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.auth import AuthService
from cookfully.application.exports import PortableExportService
from cookfully.application.recipe_photos import RecipePhotoService
from cookfully.domain.common import uuid7
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models.media import MediaAsset, RecipePhotoDerivative
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.recipe_images import RecipeImageService
from cookfully.infrastructure.safe_fetch import SafeFetcher


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (320, 180), color=color)
    payload = BytesIO()
    image.save(payload, format="PNG")
    return payload.getvalue()


def _seed_recipe(session_factory: sessionmaker[Session], owner_id: UUID) -> UUID:
    recipe_id = uuid7()
    with session_factory.begin() as session:
        session.add(
            Recipe(
                id=recipe_id,
                title="Media invariant recipe",
                yield_quantity=Decimal("2.000"),
                yield_unit="servings",
                status="draft",
                nutrition_state="estimated",
                input_hash="nutrition-input-stable",
                version=1,
            )
        )
    del owner_id
    return recipe_id


async def test_recipe_photo_replacement_is_normalized_exported_and_non_destructive(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    owner = AuthService(session_factory).bootstrap_owner(
        "owner@example.com", "correct horse battery staple", "Owner"
    )
    recipe_id = _seed_recipe(session_factory, owner.id)
    media = MediaStore(tmp_path / "media", "media-test-secret")
    images = RecipeImageService(SafeFetcher(), media)
    service = RecipePhotoService(session_factory, images, media, SafeFetcher())

    first = service.replace(
        recipe_id,
        content=_png_bytes((114, 145, 92)),
        content_type="image/png",
        expected_version=1,
    )
    with session_factory() as session:
        first_detail = session.get(MediaAsset, first.image_asset_id)
        first_card = session.scalar(
            select(MediaAsset)
            .join(RecipePhotoDerivative, RecipePhotoDerivative.asset_id == MediaAsset.id)
            .where(RecipePhotoDerivative.recipe_id == recipe_id)
        )
        assert first_detail is not None and first_card is not None
        old_keys = {first_detail.storage_key, first_card.storage_key}

    second = service.replace(
        recipe_id,
        content=_png_bytes((32, 96, 140)),
        content_type="image/png",
        expected_version=2,
    )
    assert second.version == 3
    with session_factory() as session:
        stored = session.get(Recipe, recipe_id)
        assert stored is not None
        assert stored.input_hash == "nutrition-input-stable"
        assert stored.nutrition_state == "estimated"
        new_detail = session.get(MediaAsset, second.image_asset_id)
        assert new_detail is not None
        assert all(not media.resolve_key(key).exists() for key in old_keys)

    export_path = tmp_path / "exports" / "recipe.zip"
    PortableExportService(session_factory, media).create_archive(owner.id, export_path)
    with zipfile.ZipFile(export_path) as archive:
        assert f"media/{new_detail.storage_key}" in archive.namelist()
        assert archive.read(f"media/{new_detail.storage_key}")

    removed = service.remove(recipe_id, expected_version=3)
    assert removed.image_asset_id is None
    assert not media.resolve_key(new_detail.storage_key).exists()
