from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select

from cookfully.application.import_preview import ImportPreviewCoordinator
from cookfully.domain.common import DomainError, utc_now, uuid7
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.import_preview import ImportPreviewRecord
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.recipe_importer import ImportedRecipe


def _imported(**overrides: object) -> ImportedRecipe:
    base: dict[str, object] = {
        "title": "Training Oats",
        "source_url": "https://example.com/oats",
        "canonical_url": "https://example.com/oats",
        "image_url": None,
        "yield_quantity": Decimal("2.000"),
        "yield_text": "2 servings",
        "ingredients": ("100 g oats", "1 tsp salt", "Salt to taste"),
        "ingredient_sections": (None, None, None),
        "sections": (),
        "instructions": ("Mix.", "Cook and serve."),
        "source_nutrition": {},
        "image_candidates": ("https://example.com/cover.jpg",),
    }
    base.update(overrides)
    return ImportedRecipe(**base)  # type: ignore[arg-type]


@pytest.fixture
def owned_coordinator(session_factory, tmp_path):
    created: list[tuple[object, str, UUID]] = []

    class StubImporter:
        async def import_url(self, url: str) -> ImportedRecipe:
            return _imported()

    class StubRecipes:
        def create(self, write, *, trace_id: str, owner_id: UUID):
            recipe = SimpleNamespace(id=uuid7(), title=write.title, version=1)
            created.append((write, trace_id, owner_id, recipe))
            return SimpleNamespace(
                recipe=recipe,
                job=SimpleNamespace(id=uuid7()),
            )

    class StubPhotos:
        def __init__(self) -> None:
            self.calls: list[tuple[object, str, int]] = []

        async def attach_url(self, recipe_id, image_url: str, *, expected_version: int):
            self.calls.append((recipe_id, image_url, expected_version))

    photos = StubPhotos()
    coordinator = ImportPreviewCoordinator(
        session_factory,
        StubImporter(),
        StubRecipes(),
        object(),
        photos=photos,
    )
    coordinator.created = created  # type: ignore[attr-defined]
    coordinator.photos = photos  # type: ignore[attr-defined]
    return coordinator


async def test_preview_returns_structured_sections_and_needs_quantity(
    owned_coordinator, owner_id: UUID
) -> None:
    result = await owned_coordinator.preview(
        "https://example.com/oats", owner_id=owner_id, trace_id="t"
    )
    assert result["parse_id"]
    assert result["title"] == "Training Oats"
    assert result["yield_quantity"] == "2.000"
    assert result["image_sources"] == ["https://example.com/cover.jpg"]
    assert "sections" in result
    assert result["duplicates"] == []
    section = result["sections"][0]
    assert section["title"] == ""
    assert [ing["original_text"] for ing in section["ingredients"]] == [
        "100 g oats",
        "1 tsp salt",
        "Salt to taste",
    ]
    assert [ing["needs_quantity"] for ing in section["ingredients"]] == [False, False, True]
    assert section["instructions"] == ["Mix.", "Cook and serve."]


async def test_confirm_expired_or_missing_preview_raises_410(
    owned_coordinator, owner_id: UUID
) -> None:
    with pytest.raises(DomainError) as missing:
        await owned_coordinator.confirm("nope", {}, owner_id=owner_id, trace_id="t")
    assert missing.value.code == "import_preview_expired"
    assert missing.value.status == 410

    parse_id = (
        await owned_coordinator.preview("https://example.com/oats", owner_id=owner_id, trace_id="t")
    )["parse_id"]
    with owned_coordinator._session_factory.begin() as session:
        record = session.scalar(
            select(ImportPreviewRecord).where(
                ImportPreviewRecord.owner_id == owner_id,
                ImportPreviewRecord.parse_id == parse_id,
            )
        )
        assert record is not None
        record.created_at = utc_now() - timedelta(hours=1)
        record.expires_at = utc_now() - timedelta(hours=1)
    with pytest.raises(DomainError) as expired:
        await owned_coordinator.confirm(parse_id, {}, owner_id=owner_id, trace_id="t")
    assert expired.value.code == "import_preview_expired"
    assert expired.value.status == 410


async def test_confirm_applies_title_yield_and_quantity_overrides_and_persists(
    owned_coordinator, owner_id: UUID
) -> None:
    parse_id = (
        await owned_coordinator.preview("https://example.com/oats", owner_id=owner_id, trace_id="t")
    )["parse_id"]
    await owned_coordinator.confirm(
        parse_id,
        {
            "title": "Spiced Oats",
            "yieldQuantity": "3",
            "components": [
                {
                    "ingredients": [{"quantityOverride": "150 g"}, None, {"remove": True}],
                }
            ],
        },
        owner_id=owner_id,
        trace_id="t",
    )
    write, _trace_id, owner_arg, _recipe = owned_coordinator.created[-1]
    assert owner_arg == owner_id
    assert write.title == "Spiced Oats"
    assert write.yield_quantity == Decimal("3.000")
    assert write.source_url == "https://example.com/oats"
    assert [item.original_text for item in write.ingredients] == ["150 g oats", "1 tsp salt"]
    assert [item.optional for item in write.ingredients] == [False, False]
    assert write.ingredients[0].section_index == 0
    assert len(write.instructions) == 2


async def test_confirm_attaches_pdf_thumbnail_best_effort(
    owned_coordinator, owner_id: UUID
) -> None:
    parse_id = (
        await owned_coordinator.preview("https://example.com/oats", owner_id=owner_id, trace_id="t")
    )["parse_id"]
    thumbnail = "data:image/jpeg;base64,c2FtcGxl"
    await owned_coordinator.confirm(
        parse_id,
        {
            "title": "Spiced Oats",
            "imageSource": thumbnail,
            "imageSourceKind": "pdf_thumbnail",
        },
        owner_id=owner_id,
        trace_id="t",
    )
    assert owned_coordinator.photos.calls[-1][0] == owned_coordinator.created[-1][3].id
    assert owned_coordinator.photos.calls[-1][1] == thumbnail
    assert owned_coordinator.photos.calls[-1][2] == 1


async def test_confirm_skips_attach_for_remote_url_images(
    owned_coordinator, owner_id: UUID
) -> None:
    parse_id = (
        await owned_coordinator.preview("https://example.com/oats", owner_id=owner_id, trace_id="t")
    )["parse_id"]
    await owned_coordinator.confirm(
        parse_id,
        {
            "title": "Spiced Oats",
            "imageSource": "https://example.com/cover.jpg",
            "imageSourceKind": "url",
        },
        owner_id=owner_id,
        trace_id="t",
    )
    assert owned_coordinator.photos.calls == []


async def test_confirm_attach_failure_does_not_fail_confirmation(
    owned_coordinator, owner_id: UUID
) -> None:
    async def fail_attach(*args, **kwargs):
        raise RuntimeError("media backend offline")

    owned_coordinator.photos.attach_url = fail_attach  # type: ignore[attr-defined]
    parse_id = (
        await owned_coordinator.preview("https://example.com/oats", owner_id=owner_id, trace_id="t")
    )["parse_id"]
    mutation = await owned_coordinator.confirm(
        parse_id,
        {
            "title": "Spiced Oats",
            "imageSource": "data:image/jpeg;base64,c2FtcGxl",
            "imageSourceKind": "pdf_thumbnail",
        },
        owner_id=owner_id,
        trace_id="t",
    )
    assert mutation.recipe.title == "Spiced Oats"


async def test_duplicate_detection_matches_same_normalized_title(
    owned_coordinator, session_factory, owner_id: UUID
) -> None:
    with session_factory.begin() as session:
        session.add(
            Recipe(
                id=uuid7(),
                title="Training Oats",
                yield_quantity=Decimal("2.000"),
                yield_unit="servings",
                status="ready",
                nutrition_state="ready",
                input_hash="existing",
                version=1,
            )
        )
    result = await owned_coordinator.preview(
        "https://example.com/oats", owner_id=owner_id, trace_id="t"
    )
    assert len(result["duplicates"]) == 1
    assert result["duplicates"][0]["title"] == "Training Oats"


@pytest.fixture
def owner_id(session_factory) -> UUID:
    owner = OwnerAccount(
        id=uuid7(),
        email="owner@example.com",
        display_name="Owner",
        password_hash="unused",
    )
    with session_factory.begin() as session:
        session.add(owner)
    return owner.id
