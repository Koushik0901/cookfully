from __future__ import annotations

from fractions import Fraction
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from cookfully.domain.common import DomainError
from cookfully.infrastructure.ingredient_parser import parse_ingredient_line
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.recipe_images import RecipeImageService
from cookfully.infrastructure.recipe_importer import RecipeImporter
from cookfully.infrastructure.safe_fetch import SafeFetcher

RECIPE_HTML = b"""<!doctype html><html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Recipe","name":"Training Oats",
"recipeYield":"2 servings","recipeIngredient":["100 g oats","200 ml milk"],
"recipeInstructions":[{"@type":"HowToStep","text":"Mix and cook."}],
"nutrition":{"@type":"NutritionInformation","calories":"300 kcal","proteinContent":"20 g"}}
</script></head><body></body></html>"""


async def public_resolver(_: str) -> set[str]:
    return {"93.184.216.34"}


@pytest.mark.asyncio
async def test_fetch_blocks_private_addresses_and_limits_content() -> None:
    async def private(_: str) -> set[str]:
        return {"127.0.0.1"}

    with pytest.raises(DomainError, match="Private"):
        await SafeFetcher(resolver=private).fetch("http://internal.example/recipe")

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"x" * 20
        )
    )
    with pytest.raises(DomainError, match="size"):
        await SafeFetcher(resolver=public_resolver, transport=transport, max_bytes=10).fetch(
            "https://example.com/recipe"
        )


@pytest.mark.asyncio
async def test_fetch_pins_validated_address_and_rejects_malformed_length() -> None:
    seen: list[httpx.Request] = []

    def response(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": "not-a-number"},
            content=b"ok",
            request=request,
        )

    with pytest.raises(DomainError, match="content length"):
        await SafeFetcher(resolver=public_resolver, transport=httpx.MockTransport(response)).fetch(
            "https://example.com/recipe"
        )
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "example.com"


@pytest.mark.asyncio
async def test_importer_extracts_recipe_and_does_not_create_success_diagnostic(
    tmp_path: Path,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=RECIPE_HTML,
            request=request,
        )
    )
    store = MediaStore(tmp_path / "media", "secret")
    importer = RecipeImporter(
        SafeFetcher(resolver=public_resolver, transport=transport),
        store,
        diagnostics_enabled=True,
    )
    recipe = await importer.import_url("https://example.com/oats")
    assert recipe.title == "Training Oats"
    assert recipe.yield_quantity is not None and str(recipe.yield_quantity) == "2.000"
    assert recipe.ingredients == ("100 g oats", "200 ml milk")
    assert not list((tmp_path / "media").rglob("*.bin"))


@pytest.mark.asyncio
async def test_failed_import_diagnostic_is_opt_in_encrypted_and_handed_off(
    tmp_path: Path,
) -> None:
    invalid_html = b"<html><body>not a recipe and private diagnostic text</body></html>"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=invalid_html,
            request=request,
        )
    )
    store = MediaStore(tmp_path / "media", "secret")
    importer = RecipeImporter(
        SafeFetcher(resolver=public_resolver, transport=transport),
        store,
        diagnostics_enabled=True,
    )
    with pytest.raises(DomainError) as error:
        await importer.import_url("https://example.com/not-a-recipe")
    assert error.value.code == "recipe_parse_failed_with_diagnostic"
    diagnostics = list((tmp_path / "media").rglob("*.bin"))
    assert len(diagnostics) == 1
    assert diagnostics[0].read_bytes() != invalid_html
    storage_key = diagnostics[0].relative_to(tmp_path / "media").as_posix()
    assert store.read(storage_key, encrypted=True) == invalid_html


@pytest.mark.asyncio
async def test_recipe_image_is_validated_transformed_and_stored_without_metadata(
    tmp_path: Path,
) -> None:
    source = BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "private description"
    Image.new("RGB", (2400, 1200), color=(80, 120, 60)).save(
        source,
        format="JPEG",
        exif=exif,
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "image/jpeg"},
            content=source.getvalue(),
            request=request,
        )
    )
    store = MediaStore(tmp_path / "media", "secret")
    result = await RecipeImageService(
        SafeFetcher(resolver=public_resolver, transport=transport, max_bytes=5_000_000),
        store,
    ).capture("https://example.com/recipe.jpg")
    stored = store.read(result.storage_key)
    with Image.open(BytesIO(stored)) as transformed:
        assert transformed.format == "WEBP"
        assert transformed.size == (1600, 800)
        assert transformed.getexif().get(0x010E) is None


def test_ingredient_mapping_preserves_original_and_fixed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = SimpleNamespace(
        amount=[
            SimpleNamespace(
                quantity=Fraction(1, 3),
                quantity_max=Fraction(2, 3),
                unit="cup",
                confidence=0.91,
            )
        ],
        name=[SimpleNamespace(text="rolled oats", confidence=0.95)],
        preparation=SimpleNamespace(text="toasted"),
        comment=None,
        purpose=None,
    )
    monkeypatch.setattr(
        "cookfully.infrastructure.ingredient_parser.parse_ingredient",
        lambda *args, **kwargs: parsed,
    )
    result = parse_ingredient_line("1/3-2/3 cup rolled oats, toasted (optional)")
    assert str(result.quantity_min) == "0.333333"
    assert str(result.quantity_max) == "0.666667"
    assert result.original_text.startswith("1/3-2/3")
    assert result.food_name == "rolled oats" and result.optional is True
