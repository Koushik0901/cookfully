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
            "jobs/recipe_pipeline.py",
            "api/routes/foods.py",
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
