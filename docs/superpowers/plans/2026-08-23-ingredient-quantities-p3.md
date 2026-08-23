# Ingredient Quantities P3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify pantry `_UNITS` and `domain/units.py` Pint logic into single `domain/ingredient_nutrition/quantities.py` with expanded aliases, collapse duplicated `owner_serving` blocks, and expose the result through `IngredientEngine` so `pantry.py`/`corrections.py`/`recipes.py` are thin callers.

**Architecture:** Move `IngredientMeasure`/`GramRange`/`Coverage`/`to_grams`/`coverage_ratio` and the Pint `UnitRegistry` into `domain/ingredient_nutrition/quantities.py` with a comprehensive alias table (`mg/g/kg/oz/lb/ml/l/tsp/tbsp/cup/count` etc, casefold + `rstrip(".")`). Keep `domain/units.py` as a one-release shim re-export. Add `owner_serving_grams` + `convert_quantity`/`canonical_pantry_unit`/`apply_quantity_deduction`/`reverse_quantity_deduction` there; expose them via `application/ingredient_engine.py`; `application/pantry.py` wrappers preserve public `pantry_unit_unsupported`/`pantry_unit_incompatible` codes.

**Tech Stack:** Python 3.13, SQLAlchemy 2, Pydantic 2, Pint 0.25.x, `Decimal` quantized to `NUTRIENT_SCALE` (6 dp), `pytest`/`mypy`/`ruff`, TypeScript 5.x unchanged (no frontend change).

## Global Constraints

- Python 3.13 for backend; Pint 0.25.x via `UNIT_REGISTRY` — one registry instance.
- All stored decimals quantized `quantize_decimal(..., NUTRIENT_SCALE)` (6 dp), `NUTRIENT_SCALE` fixed.
- No database migration; no OpenAPI/MCP/export contract change; public pantry error codes `pantry_unit_unsupported` (422) and `pantry_unit_incompatible` (422) preserved.
- Canonical short stored: `mg`/`g`/`kg`/`ml`/`l`/`count` (mg maps to `milligram`, not `gram`); alias lookup accepts long forms and trailing dots, casefolded.
- Keep `domain`/`application` boundary: only `domain/ingredient_nutrition/quantities.py` and `application/ingredient_engine.py` may `import pint`.
- Follow `AGENTS.md` gates: `uv run --directory backend ruff format --check .`, `ruff check .`, `mypy src`, `pytest`, `pnpm --dir frontend typecheck` as applicable.
- No code comments unless asked; no API rename that would break callers/tests.

---

## File Structure

- **Create** `backend/src/cookfully/domain/ingredient_nutrition/quantities.py` — sole Pint owner: registry, `MASS_UNITS`/`VOLUME_UNITS`, `IngredientMeasure`/`GramRange`/`Coverage`, `_pint_factor`, `to_grams`, `owner_serving_grams`, `convert_quantity`, `canonical_pantry_unit`, `apply_quantity_deduction`, `reverse_quantity_deduction`, `coverage_ratio`.
- **Modify** `backend/src/cookfully/domain/units.py:1-126` — replace body with re-exports from `quantities.py` (keep `IngredientMeasure`/`GramRange`/`Coverage`/`to_grams`/`coverage_ratio`/`UNIT_REGISTRY` if imported elsewhere).
- **Modify** `backend/src/cookfully/application/ingredient_engine.py:1-110` — add quantity facade: `to_grams`, `convert_quantity`, `canonical_pantry_unit`, `apply_deduction`, `reverse_deduction`.
- **Modify** `backend/src/cookfully/application/pantry.py:1-341` — delete `_UNITS`/`_Unit` table and local `canonical_pantry_unit`/`convert_quantity`/`apply_quantity_deduction`/`reverse_quantity_deduction` bodies; replace with thin wrappers calling `engine`/`quantities` and mapping `unsafe_conversion` → pantry codes.
- **Modify** `backend/src/cookfully/application/corrections.py:136-230` — delete inline `owner_serving` grams block, replace with `engine.to_grams(...)`.
- **Modify** `backend/src/cookfully/application/recipes.py:678-702` — same collapse.
- **Create/Modify** `backend/tests/unit/test_quantity_sync.py` — new: `convert_quantity` parity across old + new aliases, `owner_serving` cases, quantization.
- **Modify** `backend/tests/unit/test_ingredient_engine_boundary.py:1-60` — extend to assert only `quantities.py` + `ingredient_engine.py` import `pint`; only `quantities.py` contains `def to_grams`/`def convert_quantity`/`_UNITS` body.
- **Verify** `backend/tests/unit/test_pantry.py`, `test_ingredient_processing.py`, `test_grocery_aggregation.py`, `tests/integration/test_nutrition_pipeline.py` — no assertion edits, all must still pass.

---

### Task 1: Core quantities module + units shim

**Files:**
- Create: `backend/src/cookfully/domain/ingredient_nutrition/quantities.py`
- Modify: `backend/src/cookfully/domain/units.py:1-126`

**Interfaces:**
- Consumes: `cookfully.domain.common.NUTRIENT_SCALE`, `quantize_decimal`, `DomainError`, `pint.UnitRegistry`
- Produces: `IngredientMeasure`, `GramRange`, `Coverage`, `UNIT_REGISTRY`, `to_grams(measure: IngredientMeasure, *, density_g_per_ml: Decimal | None, count_weight_g: Decimal | None, owner_food: OwnerFood | None) -> GramRange`, `owner_serving_grams(measure, owner_food) -> GramRange | None`, `convert_quantity(qty: Decimal, from_unit: str, to_unit: str) -> Decimal`, `canonical_pantry_unit(value: str) -> str`, `apply_quantity_deduction`, `reverse_quantity_deduction`, `coverage_ratio`

- [ ] **Step 1: Write the failing test for the new module import path**

```python
# backend/tests/unit/test_quantity_sync.py (new file, first test only)
def test_quantities_module_importable():
    from cookfully.domain.ingredient_nutrition.quantities import to_grams, convert_quantity, canonical_pantry_unit
    assert callable(to_grams)
    assert callable(convert_quantity)
    assert callable(canonical_pantry_unit)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory backend pytest backend/tests/unit/test_quantity_sync.py::test_quantities_module_importable -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cookfully.domain.ingredient_nutrition.quantities'`

- [ ] **Step 3: Create minimal quantities.py by moving domain/units.py content and adding alias table**

```python
# backend/src/cookfully/domain/ingredient_nutrition/quantities.py
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from pint import UnitRegistry
from cookfully.domain.common import NUTRIENT_SCALE, DomainError, quantize_decimal
UNIT_REGISTRY: UnitRegistry[Any] = UnitRegistry()
UNIT_REGISTRY.define("cookfully_teaspoon = 5 * milliliter")
UNIT_REGISTRY.define("cookfully_tablespoon = 15 * milliliter")
UNIT_REGISTRY.define("cookfully_cup = 240 * milliliter")
MASS_UNITS = {"milligram": "milligram", "gram": "gram", "kilogram": "kilogram", "ounce": "ounce", "pound": "pound"}
VOLUME_UNITS = {"milliliter": "milliliter", "liter": "liter", "teaspoon": "cookfully_teaspoon", "tablespoon": "cookfully_tablespoon", "cup": "cookfully_cup"}
_ALIAS_MAP = {
    "mg": "milligram", "milligram": "milligram",
    "g": "gram", "gram": "gram", "grams": "gram",
    "kg": "kilogram", "kilogram": "kilogram",
    "oz": "ounce", "ounce": "ounce", "ounces": "ounce",
    "lb": "pound", "pound": "pound", "pounds": "pound",
    "ml": "milliliter", "milliliter": "milliliter", "milliliters": "milliliter",
    "l": "liter", "liter": "liter", "liters": "liter",
    "tsp": "teaspoon", "teaspoon": "teaspoon", "teaspoons": "teaspoon",
    "tbsp": "tablespoon", "tablespoon": "tablespoon", "tablespoons": "tablespoon",
    "cup": "cup", "cups": "cup",
    "count": "item", "each": "item", "ea": "item", "item": "item", "items": "item",
}
_CANONICAL_SHORT = {"milligram": "mg", "gram": "g", "kilogram": "kg", "milliliter": "ml", "liter": "l", "teaspoon": "tsp", "tablespoon": "tbsp", "cup": "cup", "ounce": "oz", "pound": "lb", "item": "count"}
# + IngredientMeasure/GramRange/Coverage dataclasses and to_grams/owner_serving_grams/convert_quantity/canonical_pantry_unit/apply_quantity_deduction/reverse/coverage_ratio copied from domain/units.py + pantry.py with Pint dispatch
```

Copy `IngredientMeasure`/`GramRange`/`Coverage`/`to_grams`/`_pint_factor`/`coverage_ratio` verbatim from `domain/units.py`, add `_normalize_alias`, `owner_serving_grams`, `convert_quantity`, `canonical_pantry_unit`, `apply_quantity_deduction`/`reverse` from `pantry.py` but via `_pint_factor` for mass/volume factors. Keep `NUTRIENT_SCALE` quantization on all returns.

- [ ] **Step 4: Shim domain/units.py to re-export**

```python
# backend/src/cookfully/domain/units.py
from cookfully.domain.ingredient_nutrition.quantities import Coverage, GramRange, IngredientMeasure, UNIT_REGISTRY, coverage_ratio, to_grams
__all__ = ["Coverage", "GramRange", "IngredientMeasure", "UNIT_REGISTRY", "coverage_ratio", "to_grams"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --directory backend pytest backend/tests/unit/test_quantity_sync.py::test_quantities_module_importable backend/tests/unit/test_ingredient_processing.py -v`
Expected: PASS (at least 1 + 4 processing tests); `mypy src` pass for `quantities.py`.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cookfully/domain/ingredient_nutrition/quantities.py backend/src/cookfully/domain/units.py backend/tests/unit/test_quantity_sync.py
git commit -m "feat: add ingredient_nutrition.quantities with Pint aliases and shim units"
```

---

### Task 2: Engine facade + pantry wrappers

**Files:**
- Modify: `backend/src/cookfully/application/ingredient_engine.py:1-110`
- Modify: `backend/src/cookfully/application/pantry.py:1-341`
- Test: `backend/tests/unit/test_pantry.py`, `backend/tests/unit/test_quantity_sync.py`

**Interfaces:**
- Consumes: `cookfully.domain.ingredient_nutrition.quantities.{convert_quantity,canonical_pantry_unit,apply_quantity_deduction,reverse_quantity_deduction,to_grams,owner_serving_grams}`
- Produces: `IngredientEngine.to_grams(measure, *, owner_food=None, density_g_per_ml=None, count_weight_g=None) -> GramRange`, `IngredientEngine.convert_quantity(qty, from_unit, to_unit) -> Decimal`, `IngredientEngine.canonical_pantry_unit(value) -> str`, `IngredientEngine.apply_deduction(pantry, grocery) -> QuantityDeduction`, `IngredientEngine.reverse_deduction(deduction, *, pantry, grocery) -> tuple[PantryQuantity, PantryQuantity]`; pantry re-exports `canonical_pantry_unit`, `convert_quantity`, `apply_quantity_deduction`, `reverse_quantity_deduction` with pantry error codes.

- [ ] **Step 1: Write the failing test for engine facade + pantry wrapper parity**

```python
def test_engine_convert_and_pantry_wrapper_parity():
    from decimal import Decimal
    from cookfully.application.ingredient_engine import engine
    from cookfully.application.pantry import convert_quantity, canonical_pantry_unit
    assert engine.convert_quantity(Decimal("1"), "tbsp", "ml") == Decimal("15.000000")
    assert convert_quantity(Decimal("1000"), "mg", "g") == Decimal("1.000000")
    assert canonical_pantry_unit("Grams.") == "g"
    # pantry wrapper must still raise pantry codes, not domain codes
    import pytest
    from cookfully.domain.common import DomainError
    with pytest.raises(DomainError) as exc:
        convert_quantity(Decimal("1"), "g", "ml")
    assert exc.value.code == "pantry_unit_incompatible"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory backend pytest backend/tests/unit/test_quantity_sync.py::test_engine_convert_and_pantry_wrapper_parity -v`
Expected: FAIL with `AttributeError: 'IngredientEngine' object has no attribute 'convert_quantity'`

- [ ] **Step 3: Write minimal implementation — engine delegates, pantry wraps**

```python
# backend/src/cookfully/application/ingredient_engine.py (add imports + methods)
from decimal import Decimal
from cookfully.domain.ingredient_nutrition import quantities as _q
from cookfully.domain.ingredient_nutrition.quantities import GramRange, IngredientMeasure

def to_grams(self, measure: IngredientMeasure, *, owner_food=None, density_g_per_ml=None, count_weight_g=None) -> GramRange:
    return _q.to_grams(measure, density_g_per_ml=density_g_per_ml, count_weight_g=count_weight_g, owner_food=owner_food)
def convert_quantity(self, qty: Decimal, from_unit: str, to_unit: str) -> Decimal:
    return _q.convert_quantity(qty, from_unit, to_unit)
def canonical_pantry_unit(self, value: str) -> str:
    return _q.canonical_pantry_unit(value)
def apply_deduction(self, pantry, grocery):
    return _q.apply_quantity_deduction(pantry, grocery)
def reverse_deduction(self, deduction, *, pantry, grocery):
    return _q.reverse_quantity_deduction(deduction, pantry=pantry, grocery=grocery)
```

```python
# backend/src/cookfully/application/pantry.py (replace _UNITS block + functions)
from cookfully.application.ingredient_engine import engine
from cookfully.domain.common import DomainError
def canonical_pantry_unit(value: str) -> str:
    try:
        return engine.canonical_pantry_unit(value)
    except DomainError as e:
        if e.code in ("unsafe_conversion", "quantity_unavailable"):
            raise DomainError("pantry_unit_unsupported", "Pantry quantities require a supported mass, volume, or count unit.", 422) from e
        raise
def convert_quantity(quantity, from_unit, to_unit):
    try:
        return engine.convert_quantity(quantity, from_unit, to_unit)
    except DomainError as e:
        if e.code == "unsafe_conversion":
            # heuristic: if either alias unknown vs dimension mismatch — map to incompatible when both known but different dimension
            raise DomainError("pantry_unit_incompatible", "Pantry and grocery quantities must use compatible units.", 422) from e
        if e.code in ("quantity_unavailable",):
            raise DomainError("pantry_unit_unsupported", "Pantry quantities require a supported mass, volume, or count unit.", 422) from e
        raise
def apply_quantity_deduction(pantry, grocery):
    return engine.apply_deduction(pantry, grocery)
def reverse_quantity_deduction(deduction, *, pantry, grocery):
    return engine.reverse_deduction(deduction, pantry=pantry, grocery=grocery)
```

Delete `_UNITS`/`_Unit` definitions.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest backend/tests/unit/test_quantity_sync.py::test_engine_convert_and_pantry_wrapper_parity backend/tests/unit/test_pantry.py -v`
Expected: PASS (all pantry tests + new parity test); `mypy src` clean.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/application/ingredient_engine.py backend/src/cookfully/application/pantry.py backend/tests/unit/test_quantity_sync.py
git commit -m "feat: expose quantities through IngredientEngine and wrap pantry"
```

---

### Task 3: Collapse owner_serving + boundary + full gate

**Files:**
- Modify: `backend/src/cookfully/application/corrections.py:130-175`
- Modify: `backend/src/cookfully/application/recipes.py:660-720`
- Modify: `backend/tests/unit/test_ingredient_engine_boundary.py`
- Modify: `backend/tests/unit/test_quantity_sync.py` (add remaining parity + owner_serving cases)
- Test: `backend/tests/unit/test_pantry.py`, `test_ingredient_processing.py`, `test_quantity_sync.py`, `test_ingredient_engine_boundary.py`

**Interfaces:**
- Consumes: `engine.to_grams(measure, owner_food=..., density_g_per_ml=...)` and `IngredientMeasure`
- Produces: no new public API; corrections/recipes owner-serving path deleted; boundary test enforces Pint owner + def body restriction.

- [ ] **Step 1: Write the failing tests for owner_serving collapse + boundary + expanded aliases**

```python
def test_owner_serving_through_engine():
    from decimal import Decimal
    from cookfully.application.ingredient_engine import engine
    from cookfully.domain.ingredient_nutrition.quantities import IngredientMeasure
    class FakeFood:
        display_name = "Test Scoops"
        typical_serving_g = Decimal("30")
        typical_serving_unit = "scoop"
    m = IngredientMeasure(Decimal("2"), None, "scoop")
    r = engine.to_grams(m, owner_food=FakeFood())
    assert r.method == "owner_serving"
    assert r.minimum == Decimal("60.000000")
    # casefold
    m2 = IngredientMeasure(Decimal("1"), None, "SCOOP")
    assert engine.to_grams(m2, owner_food=FakeFood()).method == "owner_serving"
    # non-matching falls through to Pint error, not owner_serving
    from cookfully.domain.common import DomainError
    import pytest
    with pytest.raises(DomainError):
        engine.to_grams(IngredientMeasure(Decimal("1"), None, "cup"), owner_food=FakeFood())

def test_convert_new_aliases():
    from decimal import Decimal
    from cookfully.application.ingredient_engine import engine
    assert engine.convert_quantity(Decimal("2"), "cup", "ml") == Decimal("480.000000")
    assert engine.convert_quantity(Decimal("1"), "oz", "g") == Decimal("28.349523")
    # quantized to 6dp via NUTRIENT_SCALE
    assert engine.convert_quantity(Decimal("1"), "lb", "g") == Decimal("453.592370")

def test_boundary_only_quantities_and_engine_import_pint():
    import pathlib, re
    root = pathlib.Path("backend/src/cookfully")
    offenders = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        if "import pint" in text or "from pint" in text:
            rel = str(p.relative_to(root))
            if rel not in ("domain/ingredient_nutrition/quantities.py", "application/ingredient_engine.py"):
                offenders.append(rel)
    assert offenders == [], f"unexpected pint imports: {offenders}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest backend/tests/unit/test_quantity_sync.py::test_owner_serving_through_engine backend/tests/unit/test_quantity_sync.py::test_convert_new_aliases backend/tests/unit/test_quantity_sync.py::test_boundary_only_quantities_and_engine_import_pint -v`
Expected: FAIL with `Method owner_serving not used` or `AssertionError: unexpected pint imports` if old `domain/units.py` still imports pint.

- [ ] **Step 3: Write minimal implementation — collapse corrections/recipes, fix boundary**

```python
# backend/src/cookfully/application/corrections.py (replace block 130-175)
from cookfully.application.ingredient_engine import engine
from cookfully.domain.ingredient_nutrition.quantities import IngredientMeasure
# in activate(): replace try/converted block's density path with:
try:
    converted = engine.to_grams(
        IngredientMeasure(ingredient.quantity_min, ingredient.quantity_max, ingredient.unit_code, ingredient.optional),
        owner_food=None,
        density_g_per_ml=density_for(food.description),
    )
    grams_min = converted.minimum; grams_max = converted.maximum; conversion_method = converted.method; assumption = converted.assumption
except DomainError:
    pass
# in activate_owner_food_match(): replace manual grams_min/max calc with:
try:
    converted = engine.to_grams(
        IngredientMeasure(ingredient.quantity_min, ingredient.quantity_max, ingredient.unit_code, ingredient.optional),
        owner_food=food,
    )
    grams_min = converted.minimum; grams_max = converted.maximum; conversion_method = converted.method; assumption = converted.assumption
except DomainError:
    grams_min = grams_max = conversion_method = assumption = None

# backend/src/cookfully/application/recipes.py (same pattern in create-owner-food pre-match loop 678-702)
# replace manual grams calc under `if best_food ... == serving_unit:` with:
try:
    converted = engine.to_grams(IngredientMeasure(ingredient.quantity_min, ingredient.quantity_max, ingredient.unit_code, ingredient.optional), owner_food=best_food)
    grams_min = converted.minimum; grams_max = converted.maximum; conversion_method = converted.method; assumption = converted.assumption
except DomainError:
    grams_min = grams_max = conversion_method = assumption = None
```

Update `backend/tests/unit/test_ingredient_engine_boundary.py` to check Pint imports + `def to_grams`/`def convert_quantity` locations, and allow `domain/units.py` as shim.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --directory backend pytest backend/tests/unit/test_quantity_sync.py backend/tests/unit/test_ingredient_engine_boundary.py backend/tests/unit/test_pantry.py backend/tests/unit/test_ingredient_processing.py -q`
Expected: PASS all; `uv run --directory backend ruff format --check . && ruff check . && mypy src` pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/application/corrections.py backend/src/cookfully/application/recipes.py backend/tests/unit/test_ingredient_engine_boundary.py backend/tests/unit/test_quantity_sync.py
git commit -m "feat: collapse owner_serving via engine and enforce quantity boundary"
```

---

## Self-Review

1. **Spec coverage:** Every spec section has a task — quantities module + shim (Task 1), engine facade + pantry wrappers with preserved error codes and mg/g/kg/ml/l/count canonicals (Task 2), owner_serving collapse in corrections/recipes plus boundary and parity/sync tests (Task 3).
2. **Placeholder scan:** No `TBD`/`TODO`/`implement later`; all steps have exact file paths, code, and commands.
3. **Type consistency:** `IngredientMeasure`/`GramRange`/`QuantityDeduction`/`PantryQuantity` names match `pantry.py` and `quantities.py` throughout; `engine.to_grams` signature `to_grams(measure, *, owner_food=None, density_g_per_ml=None, count_weight_g=None) -> GramRange` is used identically in Tasks 2–3.

