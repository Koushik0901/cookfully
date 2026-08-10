from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from recipe_scrapers import scrape_html

ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "backend" / "tests" / "fixtures" / "nutrition-corpus"
SNAPSHOT_ROOT = CORPUS_ROOT / "html"
CAPTURED_AT = "2026-08-10"
USER_AGENT = "VigorVineNutritionBenchmark/1.0 (+local reproducible test capture)"


@dataclass(frozen=True, slots=True)
class Seed:
    slug: str
    url: str
    complexity: str
    primary: bool
    cuisine: str
    dietary_pattern: str


def seed(
    site: str,
    slug: str,
    complexity: str,
    primary: bool,
    cuisine: str,
    dietary_pattern: str,
) -> Seed:
    bases = {
        "diabetes": "https://diabetesfoodhub.org/recipes/",
        "bbc": "https://www.bbcgoodfood.com/recipes/",
        "skinnytaste": "https://www.skinnytaste.com/",
        "recipetineats": "https://www.recipetineats.com/",
    }
    suffix = f"{slug}/" if site in {"skinnytaste", "recipetineats"} else slug
    return Seed(
        f"{site}-{slug}", bases[site] + suffix, complexity, primary, cuisine, dietary_pattern
    )


SEEDS = (
    # Diabetes Food Hub: 5 simple, 5 moderate, 5 complex; 9 primary.
    seed(
        "diabetes",
        "greek-yogurt-vanilla-mousse-blueberries",
        "simple",
        True,
        "American",
        "vegetarian",
    ),
    seed("diabetes", "banana-pineapple-nice-cream", "simple", True, "American", "vegan"),
    seed("diabetes", "banana-popsicles", "simple", True, "American", "vegetarian"),
    seed("diabetes", "baked-apples", "simple", False, "American", "vegan"),
    seed(
        "diabetes",
        "honey-and-walnut-stuffed-dates",
        "simple",
        False,
        "Middle Eastern",
        "vegetarian",
    ),
    seed("diabetes", "roasted-pears-oat-crumble", "moderate", True, "American", "vegetarian"),
    seed("diabetes", "spiced-glazed-oranges", "moderate", True, "Mediterranean", "vegetarian"),
    seed("diabetes", "pumpkin-almond-smoothie", "moderate", True, "American", "vegan"),
    seed(
        "diabetes",
        "frozen-greek-yogurt-bark-strawberries-and-dark-chocolate",
        "moderate",
        False,
        "American",
        "vegetarian",
    ),
    seed("diabetes", "lemon-poppyseed-power-balls", "moderate", False, "American", "vegetarian"),
    seed(
        "diabetes",
        "salmon-and-spring-veggie-breakfast-casserole",
        "complex",
        True,
        "American",
        "pescatarian",
    ),
    seed(
        "diabetes",
        "cold-cucumber-soup-and-grilled-shrimp-open-face-sandwich",
        "complex",
        True,
        "Mediterranean",
        "pescatarian",
    ),
    seed("diabetes", "chicken-kofta-tabbouleh", "complex", True, "Middle Eastern", "omnivore"),
    seed(
        "diabetes", "chicken-skewers-peanut-sauce", "complex", False, "Southeast Asian", "omnivore"
    ),
    seed("diabetes", "apple-squares", "complex", False, "American", "vegetarian"),
    # BBC Good Food: 3 simple, 7 moderate, 5 complex; 9 primary.
    seed("bbc", "white-sourdough", "simple", True, "European", "vegan"),
    seed("bbc", "focaccia", "simple", True, "Italian", "vegan"),
    seed("bbc", "breakfast-burrito", "simple", False, "Mexican inspired", "vegetarian"),
    seed("bbc", "chicken-chorizo-jambalaya", "moderate", True, "Cajun inspired", "omnivore"),
    seed("bbc", "bean-enchiladas", "moderate", True, "Mexican inspired", "vegetarian"),
    seed(
        "bbc", "crispy-chilli-turkey-noodles", "moderate", True, "East Asian inspired", "omnivore"
    ),
    seed("bbc", "chicken-stroganoff", "moderate", True, "Eastern European inspired", "omnivore"),
    seed("bbc", "salmon-risotto", "moderate", False, "Italian", "pescatarian"),
    seed("bbc", "spicy-cajun-chicken-quinoa", "moderate", False, "Cajun inspired", "omnivore"),
    seed("bbc", "chickpea-coriander-burgers", "moderate", False, "Global", "vegetarian"),
    seed(
        "bbc", "mexican-chicken-stew-quinoa-beans", "complex", True, "Mexican inspired", "omnivore"
    ),
    seed("bbc", "chicken-satay-curry", "complex", True, "Southeast Asian inspired", "omnivore"),
    seed(
        "bbc",
        "vegan-chickpea-curry-jacket-potato",
        "complex",
        True,
        "South Asian inspired",
        "vegan",
    ),
    seed("bbc", "fruity-lamb-tagine", "complex", False, "North African", "omnivore"),
    seed(
        "bbc", "slow-cooker-spaghetti-bolognese", "complex", False, "Italian inspired", "omnivore"
    ),
    # Skinnytaste: 6 simple, 4 moderate; 6 primary.
    seed(
        "skinnytaste",
        "high-protein-bread-oat-sandwich-rolls",
        "simple",
        True,
        "American",
        "vegetarian",
    ),
    seed("skinnytaste", "easy-bagel-recipe", "simple", True, "American", "vegetarian"),
    seed("skinnytaste", "classic-egg-salad", "simple", True, "American", "vegetarian"),
    seed(
        "skinnytaste", "egg-tomato-and-scallion-sandwich", "simple", False, "American", "vegetarian"
    ),
    seed("skinnytaste", "tuna-salad-wraps-25-pts", "simple", False, "American", "pescatarian"),
    seed("skinnytaste", "garlic-lovers-roast-beef", "simple", False, "American", "omnivore"),
    seed(
        "skinnytaste",
        "weight-watchers-chicken-salad-3-pts",
        "moderate",
        True,
        "American",
        "omnivore",
    ),
    seed(
        "skinnytaste",
        "bacon-egg-and-avocado-breakfast-sandwich",
        "moderate",
        True,
        "American",
        "omnivore",
    ),
    seed(
        "skinnytaste",
        "healthy-avocado-egg-salad-and-salmon",
        "moderate",
        True,
        "American",
        "pescatarian",
    ),
    seed(
        "skinnytaste",
        "greek-salad-sandwich",
        "moderate",
        False,
        "Mediterranean inspired",
        "vegetarian",
    ),
    # RecipeTin Eats: 1 simple, 4 moderate, 5 complex; 6 primary.
    seed("recipetineats", "french-chicken-au-poivre-sauce", "simple", True, "French", "omnivore"),
    seed("recipetineats", "oven-baked-chicken-breast", "moderate", True, "American", "omnivore"),
    seed(
        "recipetineats", "honey-garlic-chicken", "moderate", True, "East Asian inspired", "omnivore"
    ),
    seed(
        "recipetineats", "taiwanese-three-cup-chicken", "moderate", False, "Taiwanese", "omnivore"
    ),
    seed(
        "recipetineats",
        "charcoal-chicken-shop-chicken-skewers",
        "moderate",
        False,
        "Middle Eastern inspired",
        "omnivore",
    ),
    seed(
        "recipetineats",
        "oven-baked-chicken-and-rice",
        "complex",
        True,
        "Mediterranean inspired",
        "omnivore",
    ),
    seed("recipetineats", "tuscan-chicken-stew", "complex", True, "Italian inspired", "omnivore"),
    seed("recipetineats", "orange-chicken", "complex", True, "Chinese American", "omnivore"),
    seed(
        "recipetineats",
        "chicken-and-sweet-corn-soup-with-noodles",
        "complex",
        False,
        "Chinese inspired",
        "omnivore",
    ),
    seed(
        "recipetineats",
        "coconut-chicken-curry-quick-easy",
        "complex",
        False,
        "South Asian inspired",
        "omnivore",
    ),
)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def nutrient(values: dict[str, Any], *names: str) -> str:
    normalized = {
        re.sub(r"[^a-z]", "", key.casefold()): str(value) for key, value in values.items()
    }
    raw = next((normalized[name] for name in names if name in normalized), None)
    if raw is None:
        raise ValueError(f"missing reference nutrient: {names[0]}")
    match = re.search(r"-?\d+(?:[.,]\d+)?", raw.replace(",", ""))
    if match is None:
        raise ValueError(f"invalid reference nutrient: {raw}")
    value = Decimal(match.group())
    if value < 0:
        raise ValueError(f"negative reference nutrient: {raw}")
    return format(value, "f")


def source_site(url: str) -> str:
    return httpx.URL(url).host or "unknown"


def unit_systems(ingredients: list[str]) -> list[str]:
    joined = " ".join(ingredients).casefold()
    systems: set[str] = set()
    if re.search(r"\b(?:g|kg|ml|litre|liter)s?\b", joined):
        systems.add("metric")
    if re.search(r"\b(?:oz|ounce|ounces|lb|pound|pounds|cup|cups|tbsp|tsp)\b", joined):
        systems.add("imperial-or-us-volume")
    if not systems:
        systems.add("count-or-unspecified")
    return sorted(systems)


def risk_tags(ingredients: list[str]) -> list[str]:
    joined = " ".join(ingredients).casefold()
    risks: set[str] = set()
    if re.search(r"\b(?:cup|tbsp|tsp|ml|litre|liter)\b", joined):
        risks.add("density-conversion")
    if re.search(r"\b(?:can|package|packet|bunch|clove|slice|piece|fillet|breast|egg)s?\b", joined):
        risks.add("count-or-package-weight")
    if re.search(
        r"\b(?:to taste|as needed|optional|handful|pinch|sprig|juice of|zest of)\b", joined
    ):
        risks.add("ambiguous-quantity")
    if re.search(r"\b(?:cooked|drained|divided|chopped|grated|melted|peeled)\b", joined):
        risks.add("preparation-state")
    return sorted(risks or {"straightforward-mass-or-count"})


def recipe_document(
    *,
    title: str,
    yields: str,
    ingredients: list[str],
    instructions: list[str],
    nutrition: dict[str, Any],
    canonical_url: str,
) -> bytes:
    payload = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": title,
        "recipeYield": yields,
        "recipeIngredient": ingredients,
        "recipeInstructions": [
            {"@type": "HowToStep", "text": instruction} for instruction in instructions
        ],
        "nutrition": {"@type": "NutritionInformation", **nutrition},
        "url": canonical_url,
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<link rel="canonical" href={json.dumps(canonical_url)}>'
        f'<script type="application/ld+json">{serialized}</script>'
        "</head><body><p>Sanitized public-page recipe capture for deterministic testing.</p>"
        "</body></html>\n"
    )
    return html.encode("utf-8")


def validate_seed_distribution() -> None:
    counts = {
        level: sum(item.complexity == level for item in SEEDS)
        for level in ("simple", "moderate", "complex")
    }
    primary = {
        level: sum(item.primary and item.complexity == level for item in SEEDS) for level in counts
    }
    if len(SEEDS) != 50 or counts != {"simple": 15, "moderate": 20, "complex": 15}:
        raise RuntimeError(f"invalid 50-case distribution: {counts}")
    if sum(item.primary for item in SEEDS) != 30 or primary != {
        "simple": 9,
        "moderate": 12,
        "complex": 9,
    }:
        raise RuntimeError(f"invalid primary distribution: {primary}")


def capture() -> None:
    validate_seed_distribution()
    SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "corpusVersion": "2026-08-10.1",
        "capturedAt": CAPTURED_AT,
        "capturePolicy": (
            "Only structured recipe fields required for interoperability testing are retained; "
            "advertising, account, tracking, comments, images, and unrelated prose are discarded."
        ),
        "referencePolicy": (
            "Published per-serving calories, protein, carbohydrate, and fat are independent "
            "comparison values and must never be used as ingredient-derived estimates."
        ),
        "cases": [],
    }
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(30),
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for index, item in enumerate(SEEDS, start=1):
            response = client.get(item.url)
            response.raise_for_status()
            scraper = scrape_html(response.text, str(response.url), supported_only=False)
            title = scraper.title().strip()
            yields = scraper.yields().strip()
            ingredients = [line.strip() for line in scraper.ingredients() if line.strip()]
            instructions = [
                line.strip() for line in scraper.instructions().splitlines() if line.strip()
            ]
            nutrition = {str(key): str(value) for key, value in scraper.nutrients().items()}
            if not title or not yields or not ingredients or not instructions:
                raise ValueError(f"incomplete capture for {item.url}")
            reference = {
                "basis": "per-serving",
                "yieldText": yields,
                "caloriesKcal": nutrient(nutrition, "calories", "caloriecontent", "energy"),
                "proteinG": nutrient(nutrition, "protein", "proteincontent"),
                "carbohydrateG": nutrient(
                    nutrition, "carbohydrates", "carbohydratecontent", "carbs"
                ),
                "fatG": nutrient(nutrition, "fat", "fatcontent"),
            }
            canonical_url = str(response.url)
            document = recipe_document(
                title=title,
                yields=yields,
                ingredients=ingredients,
                instructions=instructions,
                nutrition=nutrition,
                canonical_url=canonical_url,
            )
            snapshot_name = f"{index:02d}-{item.slug}.html"
            snapshot_path = SNAPSHOT_ROOT / snapshot_name
            snapshot_path.write_bytes(document)
            case = {
                "id": f"NR-{index:03d}",
                **asdict(item),
                "sourceSite": source_site(canonical_url),
                "canonicalUrl": canonical_url,
                "snapshot": f"html/{snapshot_name}",
                "sourceHtmlSha256": sha256(response.content),
                "snapshotSha256": sha256(document),
                "expectedImport": {
                    "title": title,
                    "yieldText": yields,
                    "ingredientCount": len(ingredients),
                    "instructionCount": len(instructions),
                },
                "reference": reference,
                "classification": {
                    "unitSystems": unit_systems(ingredients),
                    "riskTags": risk_tags(ingredients),
                },
            }
            manifest["cases"].append(case)
            print(f"[{index:02d}/50] {item.slug}")
    (CORPUS_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    capture()
