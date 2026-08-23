import re
from pathlib import Path

_PATTERN = re.compile(r"^\s*(from|import)\s+cookfully\.domain\.ingredient_nutrition", re.MULTILINE)


def test_only_the_engine_imports_the_domain_package() -> None:
    package_root = Path(__file__).resolve().parents[3] / "src" / "cookfully"
    violations: list[str] = []
    for path in package_root.rglob("*.py"):
        relative = path.relative_to(package_root)
        inside_domain = (
            relative.parts[:1] == ("domain",) and "ingredient_nutrition" in relative.parts
        )
        is_facade = str(relative).replace("\\", "/") == "application/ingredient_engine.py"
        if inside_domain or is_facade:
            continue
        if _PATTERN.search(path.read_text(encoding="utf-8")):
            violations.append(str(relative))
    assert violations == []
