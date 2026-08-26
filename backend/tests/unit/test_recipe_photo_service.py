from __future__ import annotations

import base64
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from cookfully.application.recipe_photos import RecipePhotoService
from cookfully.domain.common import DomainError, uuid7
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.media import RecipePhotoDerivative, RecipePhotoStage
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.recipe_images import RecipeImageService
from cookfully.infrastructure.repositories.recipes import RecipeRepository
from cookfully.infrastructure.safe_fetch import SafeFetcher


async def public_resolver(_: str) -> set[str]:
    return {"93.184.216.34"}


def _png_bytes() -> bytes:
    image = Image.new("RGB", (320, 180), color=(114, 145, 92))
    payload = BytesIO()
    image.save(payload, format="PNG")
    return payload.getvalue()


def _png_data_uri() -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes()).decode("ascii")


def _seed_recipe(session_factory, title: str = "Photo target") -> UUID:
    recipe_id = uuid7()
    with session_factory.begin() as session:
        session.add(
            Recipe(
                id=recipe_id,
                title=title,
                yield_quantity=Decimal("2.000"),
                yield_unit="servings",
                status="draft",
                nutrition_state="pending",
                input_hash="seed",
                version=1,
            )
        )
    return recipe_id


def _build_service(
    session_factory,
    tmp_path: Path,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> RecipePhotoService:
    store = MediaStore(tmp_path / "media", "secret")
    images = RecipeImageService(SafeFetcher(resolver=public_resolver, transport=transport), store)
    return RecipePhotoService(
        session_factory,
        images,
        store,
        SafeFetcher(resolver=public_resolver, transport=transport),
    )


async def test_attach_url_persists_pdf_data_uri_thumbnail(session_factory, tmp_path: Path) -> None:
    service = _build_service(session_factory, tmp_path)
    recipe_id = _seed_recipe(session_factory)

    recipe = await service.attach_url(recipe_id, _png_data_uri(), expected_version=1)

    assert recipe.image_asset_id is not None
    assert recipe.version == 2
    with session_factory() as session:
        stored = RecipeRepository(session).get(recipe_id)
        assert stored.image_asset_id == recipe.image_asset_id
        assert stored.version == 2


async def test_attach_url_fetches_remote_url(session_factory, tmp_path: Path) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=_png_bytes(),
            request=request,
        )
    )
    service = _build_service(session_factory, tmp_path, transport=transport)
    recipe_id = _seed_recipe(session_factory)

    recipe = await service.attach_url(
        recipe_id, "https://example.com/cover.png", expected_version=1
    )

    assert recipe.image_asset_id is not None
    assert recipe.version == 2


async def test_attach_url_rejects_malformed_data_uri(session_factory, tmp_path: Path) -> None:
    service = _build_service(session_factory, tmp_path)
    recipe_id = _seed_recipe(session_factory)

    with pytest.raises(DomainError, match="image"):
        await service.attach_url(
            recipe_id, "data:image/png;base64,@@@not-base64@@@", expected_version=1
        )


async def test_attach_url_rejects_stale_version(session_factory, tmp_path: Path) -> None:
    service = _build_service(session_factory, tmp_path)
    recipe_id = _seed_recipe(session_factory)

    with pytest.raises(DomainError) as stale:
        await service.attach_url(recipe_id, _png_data_uri(), expected_version=99)
    assert stale.value.code == "stale_version"
    assert stale.value.status == 409


async def test_staged_photo_claims_responsive_variants_without_reprocessing_on_save(
    session_factory, tmp_path: Path
) -> None:
    service = _build_service(session_factory, tmp_path)
    owner = OwnerAccount(
        email="stage@example.com",
        display_name="Stage owner",
        password_hash="not-used-by-this-test",
    )
    with session_factory.begin() as session:
        session.add(owner)
        session.flush()
    recipe_id = _seed_recipe(session_factory, "Prepared photo")

    stage = service.stage(owner_id=owner.id, content=_png_bytes(), content_type="image/png")
    with session_factory() as session:
        pending = session.get(RecipePhotoStage, stage.id)
        assert pending is not None and pending.detail_asset_id != pending.card_asset_id

    claimed = service.claim_stage(
        recipe_id,
        stage.id,
        owner_id=owner.id,
        expected_version=1,
    )

    assert claimed.image_asset_id is not None
    assert claimed.version == 2
    with session_factory() as session:
        assert session.get(RecipePhotoStage, stage.id) is None
        card = session.scalar(
            select(RecipePhotoDerivative).where(
                RecipePhotoDerivative.recipe_id == recipe_id,
                RecipePhotoDerivative.role == "card",
            )
        )
        assert card is not None and card.asset_id != claimed.image_asset_id
