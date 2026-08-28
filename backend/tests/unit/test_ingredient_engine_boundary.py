import re
from pathlib import Path

_PATTERN = re.compile(r"^\s*(from|import)\s+cookfully\.domain\.ingredient_nutrition", re.MULTILINE)


def test_only_the_engine_imports_the_domain_package() -> None:
    package_root = Path(__file__).resolve().parents[2] / "src" / "cookfully"
    violations: list[str] = []
    for path in package_root.rglob("*.py"):
        relative = path.relative_to(package_root)
        inside_domain = (
            relative.parts[:1] == ("domain",) and "ingredient_nutrition" in relative.parts
        )
        allowed_direct_importers = {
            "application/ingredient_engine.py",
            "domain/grocery.py",
            "application/pantry.py",
            "cli/reference_data.py",
            "domain/food_semantics.py",
            "application/recipes.py",
            "application/corrections.py",
            "application/food_match_propagation.py",
            "jobs/recipe_pipeline.py",
            "api/routes/foods.py",
            "domain/units.py",
        }
        is_allowed = str(relative).replace("\\", "/") in allowed_direct_importers
        if inside_domain or is_allowed:
            continue
        if _PATTERN.search(path.read_text(encoding="utf-8")):
            violations.append(str(relative))
    assert violations == []


def test_no_direct_normalize_bodies_outside_core() -> None:
    import re as _re
    from pathlib import Path

    package_root = Path(__file__).resolve().parents[2] / "src" / "cookfully"
    allowed = {
        "domain/ingredient_nutrition/normalization.py",
        "domain/grocery.py",
        "application/pantry.py",
        "cli/reference_data.py",
        "domain/food_semantics.py",
        "infrastructure/repositories/nutrition.py",
    }
    pattern = _re.compile(r"def\s+normalize(?:_food_name|_pantry_name)?\s*\(")
    offenders: list[str] = []
    for path in package_root.rglob("*.py"):
        rel = str(path.relative_to(package_root)).replace("\\", "/")
        if rel in allowed:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == []


def test_pint_imports_and_quantity_definitions_restricted() -> None:
    from pathlib import Path

    package_root = Path(__file__).resolve().parents[2] / "src" / "cookfully"
    allowed_pint = {
        "domain/ingredient_nutrition/quantities.py",
        "application/ingredient_engine.py",
        "domain/units.py",
    }
    pint_offenders: list[str] = []
    for path in package_root.rglob("*.py"):
        rel = str(path.relative_to(package_root)).replace("\\", "/")
        text = path.read_text(encoding="utf-8")
        if "import pint" in text or "from pint" in text:
            if rel not in allowed_pint:
                pint_offenders.append(rel)
    assert pint_offenders == [], f"unexpected pint imports: {pint_offenders}"

    allowed_defs = {
        "domain/ingredient_nutrition/quantities.py",
        "application/ingredient_engine.py",
        "application/pantry.py",
        "domain/units.py",
    }
    def_pattern = re.compile(r"^\s*def\s+(to_grams|convert_quantity)\s*\(", re.MULTILINE)
    def_offenders: list[str] = []
    for path in package_root.rglob("*.py"):
        rel = str(path.relative_to(package_root)).replace("\\", "/")
        if rel in allowed_defs:
            continue
        text = path.read_text(encoding="utf-8")
        if def_pattern.search(text):
            def_offenders.append(rel)
    assert def_offenders == [], f"unexpected quantity definitions: {def_offenders}"
