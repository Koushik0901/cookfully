from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from recipe_scrapers import scrape_html

from cookfully.infrastructure.ingredient_parser import parse_ingredient_line

ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "backend" / "tests" / "fixtures" / "nutrition-corpus"
OUTPUT = CORPUS_ROOT / "derived-inputs.json"

CORE_CODES = {
    "caloriesKcal": {"1008", "2047", "2048", "208"},
    "proteinG": {"1003", "203"},
    "carbohydrateG": {"1005", "205"},
    "fatG": {"1004", "204"},
}
STOP_WORDS = {
    "and",
    "or",
    "of",
    "the",
    "for",
    "fresh",
    "finely",
    "roughly",
    "chopped",
    "sliced",
    "diced",
    "grated",
    "minced",
    "large",
    "medium",
    "small",
    "optional",
    "divided",
    "peeled",
    "trimmed",
    "halved",
    "cored",
    "melted",
    "drained",
    "seeded",
    "crushed",
    "beaten",
    "warmed",
}
ALIASES = (
    (r"\bsugar[ -]free.*syrup\b|\bzero calorie\b", "water bottled generic"),
    (r"\bice cubes?\b", "water bottled generic"),
    (r"\bcoconut cream\b", "coconut cream raw"),
    (r"\bcoconut milk\b", "coconut milk raw"),
    (r"\balmond milk\b", "almond milk unsweetened"),
    (r"\b1 milk\b|\blow fat milk\b|\bmilk\b", "milk lowfat fluid 1 milkfat"),
    (r"\bcanned pumpkin\b|\bpumpkin puree\b", "pumpkin canned without salt"),
    (r"\bblueberr", "blueberries raw"),
    (r"\bstrawberr", "strawberries raw"),
    (r"\bpineapple", "pineapple raw all varieties"),
    (r"\bchocolate chips?\b", "chocolate chips semisweet"),
    (r"\bvanilla extract\b", "vanilla extract"),
    (r"\bcornflour\b|\bcornstarch\b", "cornstarch"),
    (r"\bbreadcrumb", "bread crumbs dry grated plain"),
    (r"\bcottage cheese\b", "cheese cottage lowfat"),
    (r"\bmozzarella\b", "cheese mozzarella part skim milk"),
    (r"\bcheddar\b", "cheese cheddar"),
    (r"\bsour cream\b|\bsoured cream\b|\bcreme fraiche\b", "cream sour cultured"),
    (r"\bhummus\b", "hummus commercial"),
    (r"\bchipotle paste\b|\bsriracha\b|\bhot sauce\b", "sauce hot chile sriracha"),
    (r"\btikka masala paste\b|\bgaram masala\b", "spices curry powder"),
    (r"\bcurry powder\b", "spices curry powder"),
    (r"\bground coriander\b|\bcoriander seed\b", "spices coriander seed"),
    (r"\bcumin\b", "spices cumin seed"),
    (r"\bturmeric\b", "spices turmeric ground"),
    (r"\bpaprika\b", "spices paprika"),
    (r"\bcinnamon\b", "spices cinnamon ground"),
    (r"\bnutmeg\b", "spices nutmeg ground"),
    (r"\bblack pepper|\bpeppercorn", "spices pepper black"),
    (r"\bfresh mint\b", "spearmint fresh"),
    (r"\bfresh parsley\b|\bparsley\b", "parsley fresh"),
    (r"\bfresh dill\b|\bdill\b", "dill weed fresh"),
    (r"\bfresh coriander\b|\bcoriander leaves\b|\bcilantro\b", "coriander cilantro leaves raw"),
    (r"\bthai basil\b|\bbasil leaves\b", "basil fresh"),
    (r"\brosemary\b", "rosemary fresh"),
    (r"\byeast\b", "leavening agents yeast baker active dry"),
    (r"\bbaking powder\b", "leavening agents baking powder"),
    (r"\bbaking soda\b", "leavening agents baking soda"),
    (r"\bmustard\b|\bdijon\b", "mustard prepared yellow"),
    (r"\bbrandy\b|\bcognac\b", "alcoholic beverage distilled whiskey"),
    (r"\bcherry tomatoes?\b|\bgrape tomatoes?\b", "tomatoes red ripe raw"),
    (r"\bgreen chill", "peppers hot chili green raw"),
    (r"\bapricot", "apricots dried sulfured uncooked"),
    (r"\bpomegranate seeds?\b", "pomegranates raw"),
    (r"\bbulgur\b", "bulgur cooked"),
    (r"\blentil", "lentils mature seeds cooked boiled without salt"),
    (r"\bpeas\b", "peas green frozen unprepared"),
    (r"\bbroccoli\b", "broccoli raw"),
    (r"\bkale\b", "kale raw"),
    (r"\barugula\b", "arugula raw"),
    (r"\bcelery\b", "celery raw"),
    (r"\bmushroom", "mushrooms white raw"),
    (r"\btuna\b", "fish tuna light canned in water drained solids"),
    (r"\bextra virgin olive oil\b|\bolive oil\b", "oil olive salad or cooking"),
    (r"\b(?:neutral|vegetable|canola|rapeseed|plain) oil\b", "oil canola"),
    (r"\bcoconut oil\b", "oil coconut"),
    (
        r"\b(?:skinless )?(?:boneless )?chicken breast",
        "chicken broilers or fryers breast meat only raw",
    ),
    (r"\bchicken thigh", "chicken broilers or fryers thigh meat only raw"),
    (r"\bground chicken\b", "chicken ground raw"),
    (r"\bground turkey\b|\bturkey mince\b", "turkey ground raw"),
    (r"\bground beef\b|\bbeef mince\b", "beef ground 90 lean 10 fat raw"),
    (r"\broast beef\b", "beef roast cooked"),
    (r"\bsalmon fillet|\bsalmon\b", "salmon atlantic farmed raw"),
    (r"\bshrimp\b|\bprawn", "crustaceans shrimp raw"),
    (r"\bchorizo\b", "chorizo pork and beef"),
    (r"\bbacon\b", "pork cured bacon cooked"),
    (r"\bgreek yogurt\b", "yogurt greek plain lowfat"),
    (r"\bnatural yogurt\b|\bplain yogurt\b", "yogurt plain whole milk"),
    (r"\bheavy cream\b|\bdouble cream\b", "cream fluid heavy whipping"),
    (r"\blight mayonnaise\b", "salad dressing mayonnaise light"),
    (r"\bmayonnaise\b", "salad dressing mayonnaise regular"),
    (r"\bpeanut butter\b", "peanut butter smooth"),
    (r"\balmond butter\b", "nuts almond butter plain"),
    (r"\bwhole wheat flour\b|\bwholemeal flour\b", "wheat flour whole grain"),
    (
        r"\bpastry flour\b|\bplain flour\b|\ball purpose flour\b|\bflour\b",
        "wheat flour white all purpose",
    ),
    (r"\bbrown sugar\b", "sugars brown"),
    (r"\bsugar\b|\bcaster sugar\b", "sugars granulated"),
    (r"\bhoney\b", "honey"),
    (r"\bmaple.*syrup\b", "syrups maple"),
    (r"\brolled oats\b|\boats\b", "oats regular and quick not fortified dry"),
    (
        r"\bwhite rice\b|\bbasmati rice\b|\blong grain rice\b|\brice\b",
        "rice white long grain regular raw unenriched",
    ),
    (r"\bquinoa\b", "quinoa uncooked"),
    (r"\brisotto rice\b|\barborio rice\b", "rice white short grain raw"),
    (r"\bspaghetti\b|\bpasta\b|\bnoodles\b", "pasta dry unenriched"),
    (r"\bchickpea", "chickpeas canned drained solids"),
    (r"\bpinto beans\b", "beans pinto canned drained solids"),
    (r"\bbutter beans\b|\bcannellini\b|\bwhite beans\b", "beans white mature seeds canned"),
    (r"\bblack beans\b", "beans black mature seeds canned"),
    (r"\bchopped tomato|\bplum tomato", "tomatoes red ripe canned"),
    (r"\btomato puree|\btomato paste", "tomato products canned paste"),
    (
        r"\bwholemeal tortilla|\bwhole wheat tortilla|\btortilla",
        "tortillas ready to bake or fry flour",
    ),
    (
        r"\bwhole grain bread|\bwhole wheat bread|\bwholemeal bread|\bwholemeal bun",
        "bread whole wheat commercially prepared",
    ),
    (r"\bbread\b|\broll\b|\bbun\b|\bbagel\b", "bread white commercially prepared"),
    (r"\bavocado\b", "avocados raw all commercial varieties"),
    (r"\bbanana\b", "bananas raw"),
    (r"\bapple\b", "apples raw with skin"),
    (r"\bpear\b", "pears raw"),
    (r"\borange\b", "oranges raw all commercial varieties"),
    (r"\blemon juice\b|\blemon\b", "lemon juice raw"),
    (r"\blime juice\b|\blime\b", "lime juice raw"),
    (r"\bonion\b|\bonions\b", "onions raw"),
    (r"\bgarlic\b", "garlic raw"),
    (r"\bginger\b", "ginger root raw"),
    (r"\bcarrot", "carrots raw"),
    (r"\bred pepper|\bbell pepper", "peppers sweet red raw"),
    (r"\bcucumber", "cucumber with peel raw"),
    (r"\bsweet potato", "sweet potato raw unprepared"),
    (r"\bpotato", "potatoes flesh and skin raw"),
    (r"\bspinach", "spinach raw"),
    (r"\bromaine", "lettuce cos or romaine raw"),
    (r"\begg white", "egg white raw fresh"),
    (r"\begg\b|\beggs\b", "egg whole raw fresh"),
    (r"\bwalnut", "nuts walnuts english"),
    (r"\bpecan", "nuts pecans"),
    (r"\balmond flour\b|\balmond", "nuts almonds"),
    (r"\bdark soy\b|\blight soy\b|\bsoy sauce", "soy sauce made from soy and wheat shoyu"),
    (r"\bbutter\b", "butter without salt"),
    (r"\bfeta\b", "cheese feta"),
    (r"\bparmesan\b", "cheese parmesan hard"),
    (r"\bsalt\b", "salt table"),
    (r"\bwater\b|\bstock\b|\bbroth\b", "water bottled generic"),
)
COUNT_WEIGHTS = (
    (r"\bchicken breast", Decimal("200")),
    (r"\bchicken thigh", Decimal("110")),
    (r"\bsalmon fillet", Decimal("150")),
    (r"\begg white", Decimal("33")),
    (r"\begg\b", Decimal("50")),
    (r"\bonion", Decimal("150")),
    (r"\bgarlic", Decimal("3")),
    (r"\bcarrot", Decimal("75")),
    (r"\bpepper", Decimal("150")),
    (r"\bapple", Decimal("180")),
    (r"\bpear", Decimal("178")),
    (r"\borange", Decimal("140")),
    (r"\bbanana", Decimal("118")),
    (r"\bavocado", Decimal("150")),
    (r"\bcherry tomato", Decimal("17")),
    (r"\btomato", Decimal("123")),
    (r"\bcucumber", Decimal("300")),
    (r"\bsweet potato", Decimal("200")),
    (r"\bpotato", Decimal("213")),
    (r"\btortilla|\bwrap", Decimal("50")),
    (r"\bbread|\bslice", Decimal("35")),
    (r"\bpita", Decimal("60")),
    (r"\bdate", Decimal("24")),
    (r"\bwalnut", Decimal("4")),
    (r"\bspring onion|\bscallion", Decimal("15")),
    (r"\bbay leaf", Decimal("0.2")),
)
DENSITIES = (
    (r"\bhoney|\bsyrup", Decimal("1.40")),
    (r"\boil\b", Decimal("0.91")),
    (r"\bflour\b", Decimal("0.53")),
    (r"\bsugar\b", Decimal("0.85")),
    (r"\bbutter\b", Decimal("0.96")),
    (r"\bpeanut butter|\balmond butter", Decimal("1.08")),
    (r"\byogurt|\bcream|\bmilk", Decimal("1.03")),
    (r"\brice\b", Decimal("0.78")),
    (r"\boats\b", Decimal("0.34")),
    (
        r"\bherb|\bmint|\bparsley|\bdill|\bcoriander|\bbasil|\bkale|\bspinach",
        Decimal("0.08"),
    ),
    (r"\bcheese\b", Decimal("0.47")),
    (r"\bsalt\b", Decimal("1.20")),
    (r"\bspice|\bcinnamon|\bpaprika|\bcumin|\bturmeric|\bpepper", Decimal("0.55")),
)
VOLUME_ML = {
    "cup": Decimal("240"),
    "tablespoon": Decimal("15"),
    "teaspoon": Decimal("5"),
    "milliliter": Decimal("1"),
    "liter": Decimal("1000"),
}
UNIT_ALIASES = {
    "tbsp": "tablespoon",
    "tbsps": "tablespoon",
    "tablespoons": "tablespoon",
    "tsp": "teaspoon",
    "tsps": "teaspoon",
    "teaspoons": "teaspoon",
    "ounces": "ounce",
    "oz": "ounce",
    "pounds": "pound",
    "lb": "pound",
    "grams": "gram",
    "g": "gram",
    "kg": "kilogram",
    "ml": "milliliter",
}

# Reviewed, recipe-specific parse/conversion decisions. These never contain published macro values.
OVERRIDES: dict[tuple[str, int], dict[str, str | bool]] = {
    ("NR-002", 0): {"query": "bananas raw", "grams": "472", "assumption": "four medium bananas"},
    ("NR-002", 1): {"optional": True, "grams": "0", "assumption": "preparation fragment"},
    ("NR-003", 0): {"query": "bananas raw", "grams": "236", "assumption": "two medium bananas"},
    ("NR-005", 0): {
        "query": "dates medjool",
        "grams": "240",
        "assumption": "ten Medjool dates at 24 g each",
    },
    ("NR-005", 2): {"optional": True, "grams": "0", "assumption": "serving-count fragment"},
    ("NR-008", 0): {
        "query": "pumpkin canned without salt",
        "grams": "245",
        "assumption": "one cup canned pumpkin",
    },
    ("NR-008", 1): {"query": "bananas raw", "grams": "118", "assumption": "one small banana"},
    ("NR-008", 2): {"optional": True, "grams": "0", "assumption": "preparation fragment"},
    ("NR-008", 8): {"optional": True, "grams": "0", "assumption": "optional ice excluded"},
    ("NR-009", 1): {"optional": True, "grams": "0", "assumption": "ingredient continuation"},
    ("NR-009", 3): {"optional": True, "grams": "0", "assumption": "ingredient continuation"},
    ("NR-010", 7): {"optional": True, "grams": "0", "assumption": "source fragment without a food"},
    ("NR-011", 1): {"optional": True, "grams": "0", "assumption": "spray label fragment"},
    ("NR-011", 3): {"optional": True, "grams": "0", "assumption": "preparation fragment"},
    ("NR-011", 6): {"optional": True, "grams": "0", "assumption": "preparation fragment"},
    ("NR-011", 12): {"optional": True, "grams": "0", "assumption": "ingredient continuation"},
    ("NR-012", 3): {"optional": True, "grams": "0", "assumption": "preparation fragment"},
    ("NR-012", 7): {"optional": True, "grams": "0", "assumption": "spray label fragment"},
    ("NR-013", 0): {
        "query": "bulgur cooked",
        "grams": "182",
        "assumption": "one cup cooked bulgur",
    },
    ("NR-013", 2): {"optional": True, "grams": "0", "assumption": "preparation fragment"},
    ("NR-013", 6): {"optional": True, "grams": "0", "assumption": "preparation fragment"},
    ("NR-013", 17): {"optional": True, "grams": "0", "assumption": "spray label fragment"},
    ("NR-014", 0): {"optional": True, "grams": "0", "assumption": "non-food skewer"},
    ("NR-014", 12): {"optional": True, "grams": "0", "assumption": "ingredient continuation"},
    ("NR-015", 1): {"optional": True, "grams": "0", "assumption": "preparation fragment"},
    ("NR-015", 2): {"optional": True, "grams": "0", "assumption": "preparation fragment"},
    ("NR-015", 5): {"optional": True, "grams": "0", "assumption": "ingredient continuation"},
    ("NR-015", 11): {"optional": True, "grams": "0", "assumption": "preparation fragment"},
    ("NR-018", 0): {
        "query": "sauce hot chile sriracha",
        "grams": "5",
        "assumption": "one teaspoon chipotle paste",
    },
    ("NR-018", 4): {
        "query": "tomatoes red ripe raw",
        "grams": "119",
        "assumption": "seven cherry tomatoes at 17 g each",
    },
    ("NR-025", 5): {
        "query": "bread crumbs dry grated plain",
        "grams": "100",
        "assumption": "explicit breadcrumb mass",
    },
    ("NR-034", 0): {
        "query": "bread whole wheat commercially prepared",
        "grams": "45",
        "assumption": "one 100-calorie sandwich roll",
    },
    ("NR-037", 5): {
        "query": "mustard prepared yellow",
        "grams": "5",
        "assumption": "one teaspoon Dijon mustard",
    },
    ("NR-041", 3): {
        "query": "spices pepper black",
        "grams": "5.5",
        "assumption": "two teaspoons peppercorns",
    },
    ("NR-041", 4): {
        "query": "alcoholic beverage distilled whiskey",
        "grams": "79",
        "assumption": "one third US cup brandy",
    },
    ("NR-044", 2): {
        "query": "ginger root raw",
        "grams": "12",
        "assumption": "six thin ginger slices at 2 g each",
    },
    ("NR-044", 6): {
        "query": "basil fresh",
        "grams": "24",
        "assumption": "one lightly packed cup basil leaves",
    },
    ("NR-044", 11): {
        "optional": True,
        "grams": "0",
        "assumption": "unquantified serving rice excluded",
    },
    ("NR-045", 12): {"optional": True, "grams": "0", "assumption": "section heading"},
    ("NR-045", 13): {"optional": True, "grams": "0", "assumption": "unquantified serving option"},
    ("NR-045", 14): {"optional": True, "grams": "0", "assumption": "unquantified serving option"},
    ("NR-045", 15): {"optional": True, "grams": "0", "assumption": "unquantified serving option"},
    ("NR-048", 4): {
        "query": "cornstarch",
        "grams": "16",
        "assumption": "two tablespoons cornstarch",
    },
    ("NR-048", 5): {
        "query": "cornstarch",
        "grams": "96",
        "assumption": "three quarter cup cornstarch",
    },
    ("NR-048", 6): {
        "query": "oil canola",
        "grams": "45",
        "assumption": "estimated retained frying oil",
    },
    ("NR-048", 9): {
        "query": "cornstarch",
        "grams": "12",
        "assumption": "one and a half tablespoons cornstarch",
    },
    ("NR-048", 17): {
        "optional": True,
        "grams": "0",
        "assumption": "unquantified serving rice excluded",
    },
    ("NR-049", 3): {
        "query": "spices pepper black",
        "grams": "0.3",
        "assumption": "one pinch black pepper",
    },
    ("NR-049", 6): {
        "query": "corn sweet yellow canned drained solids",
        "grams": "240",
        "assumption": "drained 400 g can",
    },
    ("NR-049", 9): {
        "query": "milk lowfat fluid 1 milkfat",
        "grams": "732",
        "assumption": "three US cups milk",
    },
    ("NR-049", 12): {
        "query": "pasta dry unenriched",
        "grams": "150",
        "assumption": "one and a half cups broken dry pasta",
    },
    ("NR-049", 13): {
        "query": "cheese cheddar",
        "grams": "113",
        "assumption": "one cup shredded cheddar",
    },
    ("NR-049", 14): {
        "query": "kale raw",
        "grams": "60",
        "assumption": "three packed cups kale leaves",
    },
    ("NR-049", 15): {"optional": True, "grams": "0", "assumption": "unquantified garnish"},
    ("NR-049", 16): {"optional": True, "grams": "0", "assumption": "unquantified garnish"},
    ("NR-050", 6): {
        "query": "spices cumin seed",
        "grams": "2.1",
        "assumption": "one teaspoon ground cumin",
    },
    ("NR-050", 7): {
        "query": "spices turmeric ground",
        "grams": "3",
        "assumption": "one teaspoon turmeric",
    },
    ("NR-050", 10): {
        "query": "coconut cream raw",
        "grams": "400",
        "assumption": "explicit coconut cream mass",
    },
    ("NR-050", 11): {
        "query": "chickpeas canned drained solids",
        "grams": "240",
        "assumption": "drained 400 g can",
    },
    ("NR-050", 13): {
        "optional": True,
        "grams": "0",
        "assumption": "unquantified serving yogurt excluded",
    },
    ("NR-050", 14): {"optional": True, "grams": "0", "assumption": "unquantified garnish"},
    ("NR-050", 15): {
        "optional": True,
        "grams": "0",
        "assumption": "unquantified serving rice excluded",
    },
}


@dataclass(frozen=True, slots=True)
class Food:
    fdc_id: str
    dataset: str
    description: str
    normalized: str
    tokens: frozenset[str]
    macros: dict[str, Decimal]
    portions: tuple[dict[str, Any], ...]


def normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_archive(path: Path, dataset: str) -> list[Food]:
    with zipfile.ZipFile(path) as archive:
        name = next(item for item in archive.namelist() if item.casefold().endswith(".json"))
        raw = json.loads(archive.read(name))
    key = "FoundationFoods" if dataset == "foundation" else "SRLegacyFoods"
    rows = raw[key]
    foods: list[Food] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        macros: dict[str, Decimal] = {}
        for item in row.get("foodNutrients", []):
            nutrient = item.get("nutrient", {})
            code = str(nutrient.get("number") or nutrient.get("id") or "")
            unit = str(nutrient.get("unitName", "")).casefold()
            amount = item.get("amount")
            if amount is None:
                continue
            for field, codes in CORE_CODES.items():
                if code in codes and (field != "caloriesKcal" or unit == "kcal"):
                    macros.setdefault(field, Decimal(str(amount)))
        if len(macros) != 4:
            continue
        description = str(row.get("description", "")).strip()
        foods.append(
            Food(
                fdc_id=str(row["fdcId"]),
                dataset=dataset,
                description=description,
                normalized=normalize(description),
                tokens=frozenset(normalize(description).split()),
                macros=macros,
                portions=tuple(row.get("foodPortions", [])),
            )
        )
    return foods


def canonical_query(food_name: str, line: str) -> str:
    combined = normalize(f"{food_name.split(';', 1)[0]} {line}")
    for pattern, replacement in ALIASES:
        if re.search(pattern, combined):
            return replacement
    tokens = [
        token for token in normalize(food_name.split(";", 1)[0]).split() if token not in STOP_WORDS
    ]
    return " ".join(tokens)


def match_food(query: str, food_index: dict[str, list[Food]]) -> tuple[Food, Decimal]:
    query_tokens = set(normalize(query).split())
    candidates_by_id = {
        food.fdc_id: food for token in query_tokens for food in food_index.get(token, [])
    }
    candidates = list(candidates_by_id.values())
    if not candidates:
        raise ValueError(f"no USDA candidates for {query!r}")

    def score(food: Food) -> Decimal:
        tokens = food.tokens
        coverage = Decimal(len(query_tokens & tokens)) / Decimal(len(query_tokens) or 1)
        jaccard = Decimal(len(query_tokens & tokens)) / Decimal(len(query_tokens | tokens) or 1)
        sequence = Decimal(str(SequenceMatcher(None, normalize(query), food.normalized).ratio()))
        value = coverage * Decimal("0.55") + jaccard * Decimal("0.20") + sequence * Decimal("0.25")
        if food.dataset == "foundation":
            value += Decimal("0.03")
        if re.search(r"babyfood|restaurant|fast foods|school lunch", food.normalized):
            value -= Decimal("0.20")
        return value

    ranked = sorted(
        ((score(food), food) for food in candidates), key=lambda item: (-item[0], item[1].fdc_id)
    )
    bounded_score = min(ranked[0][0], Decimal("1"))
    return ranked[0][1], bounded_score.quantize(Decimal("0.000001"))


def explicit_mass(line: str) -> Decimal | None:
    normalized = line.replace("½", "0.5").replace("¼", "0.25").replace("¾", "0.75")
    pack = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*g\b", normalized, re.I)
    if pack:
        return Decimal(pack.group(1)) * Decimal(pack.group(2))
    ranges = re.findall(r"(\d+(?:\.\d+)?)\s*(?:[-\u2013]\s*\d+(?:\.\d+)?)?\s*g\b", normalized, re.I)
    if ranges:
        value = Decimal(ranges[-1])
        count = re.match(r"\s*(\d+(?:\.\d+)?)\b", normalized)
        if count and "each" in normalized.casefold():
            return value * Decimal(count.group(1))
        return value
    ounces = re.search(r"(\d+(?:\.\d+)?)\s*(?:oz|ounce|ounces)\b", normalized, re.I)
    if ounces:
        return Decimal(ounces.group(1)) * Decimal("28.349523125")
    return None


def density(food_name: str, food: Food, unit: str) -> Decimal:
    normalized = normalize(food_name)
    for portion in food.portions:
        measure = portion.get("measureUnit") or {}
        raw_unit = normalize(str(measure.get("name") or measure.get("abbreviation") or ""))
        portion_unit = UNIT_ALIASES.get(raw_unit, raw_unit)
        amount = Decimal(str(portion.get("amount") or portion.get("value") or 1))
        gram_weight = portion.get("gramWeight")
        if portion_unit != unit or gram_weight is None or amount <= 0:
            continue
        candidate = Decimal(str(gram_weight)) / amount / VOLUME_ML[unit]
        if Decimal("0.01") <= candidate <= Decimal("3"):
            return candidate
    return next(
        (value for pattern, value in DENSITIES if re.search(pattern, normalized)), Decimal("0.70")
    )


def count_weight(food_name: str, food: Food) -> Decimal:
    normalized = normalize(food_name)
    configured = next(
        (value for pattern, value in COUNT_WEIGHTS if re.search(pattern, normalized)), None
    )
    if configured is not None:
        return configured
    portions = [
        Decimal(str(item["gramWeight"]))
        / Decimal(str(item.get("amount") or item.get("value") or 1))
        for item in food.portions
        if item.get("gramWeight") and Decimal(str(item.get("amount") or item.get("value") or 1)) > 0
    ]
    return (
        min(portions, key=lambda value: abs(value - Decimal("100"))) if portions else Decimal("30")
    )


def ingredient_grams(line: str, food_name: str, food: Food) -> tuple[Decimal, str, str]:
    direct = explicit_mass(line)
    if direct is not None:
        if "drained" in line.casefold() and re.search(r"bean|chickpea|corn", food_name, re.I):
            direct *= Decimal("0.60")
            return direct, "mass", "explicit can mass with 60% drained-solids assumption"
        return direct, "mass", "explicit mass in captured ingredient text"
    parsed = parse_ingredient_line(line)
    quantity = parsed.quantity_min
    unit = UNIT_ALIASES.get(parsed.unit_code or "", parsed.unit_code)
    if quantity is None:
        if re.search(
            r"to serve|to taste|garnish|optional|spray|thermometer|sauce options|"
            r"^white rice|^cooked rice|^flatbreads|^seasoned rice|^naan|^plain yogurt|"
            r"^coriander leaves|^lime wedges",
            line,
            re.I,
        ):
            return Decimal("0"), "optional", "unquantified optional or service-only line"
        return (
            count_weight(food_name, food),
            "count_weight",
            "one implicit item using reference portion",
        )
    if unit in {"gram", "kilogram", "ounce", "pound"}:
        factors = {
            "gram": Decimal("1"),
            "kilogram": Decimal("1000"),
            "ounce": Decimal("28.349523125"),
            "pound": Decimal("453.59237"),
        }
        return quantity * factors[unit], "mass", f"canonical {unit} conversion"
    if unit in VOLUME_ML:
        applied_density = density(food_name, food, unit)
        return (
            quantity * VOLUME_ML[unit] * applied_density,
            "density",
            f"density {applied_density} g/mL",
        )
    weight = count_weight(food_name, food)
    return quantity * weight, "count_weight", f"count weight {weight} g"


def build(foundation: Path, legacy: Path) -> None:
    foods = load_archive(foundation, "foundation") + load_archive(legacy, "sr_legacy")
    food_index: dict[str, list[Food]] = {}
    for food in foods:
        for token in food.tokens:
            food_index.setdefault(token, []).append(food)
    manifest = json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))
    used_foods: dict[str, Food] = {}
    cases: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        html = (CORPUS_ROOT / case["snapshot"]).read_text(encoding="utf-8")
        scraper = scrape_html(html, case["canonicalUrl"], supported_only=False)
        decisions: list[dict[str, Any]] = []
        for position, line in enumerate(scraper.ingredients()):
            parsed = parse_ingredient_line(line)
            food_name = parsed.food_name or line
            override = OVERRIDES.get((case["id"], position), {})
            query = str(override.get("query") or canonical_query(food_name, line))
            if override.get("optional") is True and "query" not in override:
                decisions.append(
                    {
                        "position": position,
                        "originalText": line,
                        "parsedFoodName": food_name,
                        "query": query,
                        "foodFdcId": None,
                        "matchScore": None,
                        "grams": "0.000000",
                        "conversionMethod": "optional",
                        "assumption": str(override["assumption"]),
                        "optional": True,
                    }
                )
                continue
            if not query:
                decisions.append(
                    {
                        "position": position,
                        "originalText": line,
                        "parsedFoodName": food_name,
                        "query": query,
                        "foodFdcId": None,
                        "matchScore": None,
                        "grams": "0.000000",
                        "conversionMethod": "optional",
                        "assumption": "non-food preparation fragment excluded",
                        "optional": True,
                    }
                )
                continue
            try:
                food, score = match_food(query, food_index)
            except ValueError:
                decisions.append(
                    {
                        "position": position,
                        "originalText": line,
                        "parsedFoodName": food_name,
                        "query": query,
                        "foodFdcId": None,
                        "matchScore": None,
                        "grams": "0.000000",
                        "conversionMethod": "unresolved",
                        "assumption": "no USDA candidate was selected",
                        "optional": parsed.optional,
                    }
                )
                continue
            if "grams" in override:
                grams = Decimal(str(override["grams"]))
                method = "manual"
                assumption = str(override["assumption"])
            else:
                grams, method, assumption = ingredient_grams(line, food_name, food)
            used_foods[food.fdc_id] = food
            decisions.append(
                {
                    "position": position,
                    "originalText": line,
                    "parsedFoodName": food_name,
                    "query": query,
                    "foodFdcId": food.fdc_id,
                    "matchScore": str(score),
                    "grams": str(grams.quantize(Decimal("0.000001"))),
                    "conversionMethod": method,
                    "assumption": assumption,
                    "optional": bool(
                        override.get("optional", method == "optional" or parsed.optional)
                    ),
                }
            )
        cases.append(
            {"caseId": case["id"], "yieldText": scraper.yields(), "ingredients": decisions}
        )
        print(f"[{case['id']}] {case['slug']}: {len(decisions)} ingredients")
    output = {
        "schemaVersion": 1,
        "corpusVersion": manifest["corpusVersion"],
        "referenceReleases": [
            {
                "datasetType": "foundation",
                "releaseId": "2026-04-30",
                "sourceUrl": "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_json_2026-04-30.zip",
                "archiveSha256": sha256(foundation),
                "license": "CC0-1.0",
            },
            {
                "datasetType": "sr_legacy",
                "releaseId": "2018-04",
                "sourceUrl": "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_json_2018-04.zip",
                "archiveSha256": sha256(legacy),
                "license": "CC0-1.0",
            },
        ],
        "foods": [
            {
                "fdcId": food.fdc_id,
                "datasetType": food.dataset,
                "description": food.description,
                "basisGrams": "100.000000",
                "macros": {key: str(value) for key, value in food.macros.items()},
            }
            for food in sorted(used_foods.values(), key=lambda item: int(item.fdc_id))
        ],
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} cases and {len(used_foods)} USDA foods to {OUTPUT}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation", type=Path, required=True)
    parser.add_argument("--sr-legacy", type=Path, required=True)
    arguments = parser.parse_args()
    build(arguments.foundation, arguments.sr_legacy)


if __name__ == "__main__":
    main()
