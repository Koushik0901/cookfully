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
    created: list[tuple[object, str, UUID, object]] = []
    updated: list[tuple[object, object, int, str, UUID]] = []

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

        def update(self, recipe_id, write, *, expected_version: int, trace_id: str, owner_id: UUID):
            recipe = SimpleNamespace(id=recipe_id, title=write.title, version=expected_version + 1)
            updated.append((recipe_id, write, expected_version, trace_id, owner_id))
            return SimpleNamespace(
                recipe=recipe,
                job=SimpleNamespace(id=uuid7()),
            )

    class StubPhotos:
        def __init__(self) -> None:
            self.calls: list[tuple[object, str, int, object]] = []

        async def attach_url(self, recipe_id, image_url: str, *, expected_version: int, crop=None):
            self.calls.append((recipe_id, image_url, expected_version, crop))

    photos = StubPhotos()
    coordinator = ImportPreviewCoordinator(
        session_factory,
        StubImporter(),
        StubRecipes(),
        object(),
        photos=photos,
    )
    coordinator.created = created  # type: ignore[attr-defined]
    coordinator.updated = updated  # type: ignore[attr-defined]
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
            "thumbnailCrop": {"focalX": "0.25", "focalY": "0.75", "zoom": "1.5"},
        },
        owner_id=owner_id,
        trace_id="t",
    )
    assert owned_coordinator.photos.calls[-1][0] == owned_coordinator.created[-1][3].id
    assert owned_coordinator.photos.calls[-1][1] == thumbnail
    assert owned_coordinator.photos.calls[-1][2] == 1
    assert owned_coordinator.photos.calls[-1][3] is not None


async def test_confirm_attaches_selected_remote_url_image(
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
    assert owned_coordinator.photos.calls[-1][1] == "https://example.com/cover.jpg"


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
    assert mutation.cover_status == "failed"


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
                version=3,
            )
        )
    result = await owned_coordinator.preview(
        "https://example.com/oats", owner_id=owner_id, trace_id="t"
    )
    assert len(result["duplicates"]) == 1
    assert result["duplicates"][0]["title"] == "Training Oats"
    assert result["duplicates"][0]["version"] == 3


async def test_merge_replaces_content_but_preserves_existing_identity(
    owned_coordinator, session_factory, owner_id: UUID
) -> None:
    existing_id = uuid7()
    with session_factory.begin() as session:
        session.add(
            Recipe(
                id=existing_id,
                title="Training Oats",
                description="Hand-written notes.",
                source_url="https://example.com/old-origin",
                yield_quantity=Decimal("2.000"),
                yield_unit="servings",
                status="ready",
                nutrition_state="ready",
                input_hash="existing",
                version=1,
            )
        )
    parse_id = (
        await owned_coordinator.preview("https://example.com/oats", owner_id=owner_id, trace_id="t")
    )["parse_id"]

    owned_coordinator.merge(
        existing_id,
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
        expected_version=1,
        trace_id="t",
    )

    recipe_id, write, expected_version, _trace_id, owner_arg = owned_coordinator.updated[-1]
    assert recipe_id == existing_id
    assert expected_version == 1
    assert owner_arg == owner_id
    assert write.title == "Spiced Oats"
    assert write.yield_quantity == Decimal("3.000")
    # Identity fields are preserved from the existing recipe, not overwritten by the import.
    assert write.description == "Hand-written notes."
    assert write.source_url == "https://example.com/old-origin"
    assert [item.original_text for item in write.ingredients] == ["150 g oats", "1 tsp salt"]


async def test_merge_does_not_attach_pdf_thumbnail(
    owned_coordinator, session_factory, owner_id: UUID
) -> None:
    existing_id = uuid7()
    with session_factory.begin() as session:
        session.add(
            Recipe(
                id=existing_id,
                title="Training Oats",
                yield_quantity=Decimal("2.000"),
                yield_unit="servings",
                status="ready",
                nutrition_state="ready",
                input_hash="existing",
                version=1,
            )
        )
    parse_id = (
        await owned_coordinator.preview("https://example.com/oats", owner_id=owner_id, trace_id="t")
    )["parse_id"]
    owned_coordinator.merge(
        existing_id,
        parse_id,
        {
            "title": "Spiced Oats",
            "imageSource": "data:image/jpeg;base64,c2FtcGxl",
            "imageSourceKind": "pdf_thumbnail",
        },
        owner_id=owner_id,
        expected_version=1,
        trace_id="t",
    )
    assert owned_coordinator.photos.calls == []


async def test_merge_expired_preview_raises_410(owned_coordinator, owner_id: UUID) -> None:
    with pytest.raises(DomainError) as missing:
        owned_coordinator.merge(
            uuid7(),
            "nope",
            {"title": "Spiced Oats"},
            owner_id=owner_id,
            expected_version=1,
            trace_id="t",
        )
    assert missing.value.code == "import_preview_expired"
    assert missing.value.status == 410


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
