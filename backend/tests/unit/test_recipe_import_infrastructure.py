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
async def test_fetch_allows_bounded_pdf_when_the_importer_explicitly_requests_it() -> None:
    content = b"%PDF" + b"x" * 16
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=content,
            request=request,
        )
    )
    fetcher = SafeFetcher(resolver=public_resolver, transport=transport, max_bytes=10)
    resource = await fetcher.fetch(
        "https://example.com/book.pdf",
        allowed_content_types=frozenset({"application/pdf"}),
        max_bytes=25,
    )
    assert resource.content == content


def test_cookbook_pdf_pages_become_separate_structured_recipes() -> None:
    pages = (
        "V E G A N   B U R G E R\n\nIngredients:\n   1 cup TVP\n   1 tsp Salt",
        "Directions:\n  1.Mix everything.\n  2.Form patties and cook.",
        "I N S T A N T   M A C   &   C H E E S E\n\nIngredients:\n"
        "Cheese Powder\n   1 cup Nutritional Yeast\nMac and Cheese\n   8 oz Macaroni",
        "Directions:\n  1.Combine the powder.\n  2.Cook the macaroni.",
    )
    recipes = RecipeImporter._recipes_from_pdf_pages(
        pages,
        "https://example.com/book.pdf",
        "https://example.com/book.pdf",
    )
    assert [item.title for item in recipes] == ["Vegan Burger", "Instant Mac & Cheese"]
    assert recipes[0].instructions == ("Mix everything.", "Form patties and cook.")
    assert recipes[1].ingredients == (
        "1 cup Nutritional Yeast",
        "8 oz Macaroni",
    )
    assert recipes[1].sections == ("Cheese Powder", "Mac and Cheese")
    assert recipes[1].ingredient_sections == (0, 1)


def test_grouped_html_ingredients_become_sections_in_source_order() -> None:
    scraper = SimpleNamespace(
        ingredients=lambda: ["1 cup Nutritional Yeast", "8 oz Macaroni", "4 cups broth"],
        ingredient_groups=lambda: [
            SimpleNamespace(purpose="For the cheese", ingredients=["1 cup Nutritional Yeast"]),
            SimpleNamespace(purpose="For the pasta", ingredients=["8 oz Macaroni"]),
            SimpleNamespace(purpose=None, ingredients=["4 cups broth"]),
        ],
    )
    ingredients, sections, titles = RecipeImporter._ingredients_with_sections(scraper)
    assert ingredients == ("1 cup Nutritional Yeast", "8 oz Macaroni", "4 cups broth")
    assert sections == (0, 1, None)
    assert titles == ("For the cheese", "For the pasta")


def test_recipe_image_candidates_are_ordered_and_deduplicated() -> None:
    html = """
      <meta property="og:image" content="/cover.jpg">
      <main><img src="/cover.jpg"><img data-src="step.jpg"><img src="/second.jpg"></main>
    """
    assert RecipeImporter.image_candidates(html, "https://example.com/recipe") == (
        "https://example.com/cover.jpg",
        "https://example.com/step.jpg",
        "https://example.com/second.jpg",
    )


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


@pytest.mark.parametrize(
    ("line", "unit"),
    [
        ("1 Tbsp tomato paste", "tablespoon"),
        ("2 tbsps nutritional yeast", "tablespoon"),
        ("1 tsp garlic powder", "teaspoon"),
        ("1/2 tsps onion powder", "teaspoon"),
    ],
)
def test_ingredient_parser_normalizes_common_spoon_abbreviations(line: str, unit: str) -> None:
    assert parse_ingredient_line(line).unit_code == unit


def test_pdf_embedded_image_becomes_a_data_uri_candidate() -> None:
    import pypdf
    from pypdf.generic import DictionaryObject, NameObject, NumberObject, StreamObject

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=72, height=72)
    jpg = BytesIO()
    Image.new("RGB", (120, 120), (180, 40, 40)).save(jpg, format="JPEG")
    jpg.seek(0)
    stream = StreamObject()
    stream.set_data(jpg.getvalue())
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Image")
    stream[NameObject("/Width")] = NumberObject(120)
    stream[NameObject("/Height")] = NumberObject(120)
    stream[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    stream[NameObject("/BitsPerComponent")] = NumberObject(8)
    stream[NameObject("/Filter")] = NameObject("/DCTDecode")
    xo = writer._add_object(stream)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): xo})}
    )
    out = BytesIO()
    writer.write(out)

    urls = RecipeImporter._pdf_image_candidates(out.getvalue())

    assert len(urls) == 1
    assert urls[0].startswith("data:image/jpeg;base64,")


def test_manual_recipe_photo_reuses_safe_normalization(tmp_path: Path) -> None:
    source = BytesIO()
    Image.new("RGB", (2200, 1100), color=(120, 80, 45)).save(source, format="PNG")
    store = MediaStore(tmp_path / "media", "secret")
    images = RecipeImageService(SafeFetcher(resolver=public_resolver), store)

    result = images.capture_bytes(source.getvalue(), "image/png")

    assert result.byte_size > 0
    with Image.open(BytesIO(store.read(result.storage_key))) as transformed:
        assert transformed.format == "WEBP"
        assert transformed.size == (1600, 800)

    with pytest.raises(DomainError, match="JPEG, PNG, or WebP"):
        images.capture_bytes(b"not an image", "image/gif")
