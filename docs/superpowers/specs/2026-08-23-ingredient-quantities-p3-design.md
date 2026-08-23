# Ingredient Quantities — P3 Design (Pint Unification + Owner-Serving Collapse)

Date: 2026-08-23
Status: Approved (design sections 1–4)
Parent: `2026-08-22-ingredient-nutrition-engine-design.md` (Engine P1)
Branch: `feature/ingredient-quantities-p3` (to be created from `main`)

## Context

After P2, normalization has one owner. Quantities still have two systems:

- `domain/units.py` — Pint `UnitRegistry` (`cookfully_teaspoon/tablespoon/cup`), `MASS_UNITS`/`VOLUME_UNITS`, `IngredientMeasure`, `GramRange`, `Coverage`, `to_grams(measure, *, density_g_per_ml, count_weight_g)`, `coverage_ratio`.
- `application/pantry.py` — hand-rolled `_UNITS` (9 aliases: `mg/g/gram/grams/kg/ml/l/count/each/ea` → `mg/g/kg/ml/l/count` with `Decimal` factors), `canonical_pantry_unit`, `convert_quantity`, `apply_quantity_deduction`/`reverse_quantity_deduction`.
- `application/corrections.py:212-230` and `application/recipes.py:678-701` duplicate the same `owner_serving` grams block: when `parsed_unit.casefold() == owner_food.typical_serving_unit.casefold()` and `typical_serving_g` is set, `grams_min/max = quantize(quantity * typical_serving_g)`.

P3 finishes the quantity layer: one Pint-backed implementation, one public entry point, no new deployable.

## Goals & Non-Goals

**Goals:** One Pint-backed quantity module; pantry's alias set expands to the full Pint set (so `tbsp`/`cup`/`oz`/`lb` deduct without translation); the two `owner_serving` blocks collapse into one helper; `IngredientEngine` is the only public import; existing tests pass without assertion edits; explicit sync coverage for the expanded aliases.

**Non-goals:** CORE nutrient codes, Atwater fallback, `coverage_ratio`/aggregation math, grocery list generation, CLI/API contract changes, or DB migrations → P4. No change to `FoodReference` or `OwnerFood` schemas.

## Architecture

```
domain/ingredient_nutrition/quantities.py   # sole owner

  Pint UnitRegistry (+ cookfully_teaspoon = 5*mL, etc.)
  alias map (comprehensive, casefold + trailing-dot stripped):
    mg/milligram → milligram/gram, g/gram/grams → gram,
    kg/kilogram → kilogram, oz/ounce/ounces → ounce, lb/pound → pound,
    ml/milliliter → milliliter, l/liter → liter,
    tsp/teaspoon → cookfully_teaspoon, tbsp/tablespoon → cookfully_tablespoon,
    cup → cookfully_cup, count/each/ea/item → item
  canonical short for pantry storage: g/kg/ml/l/count (plus mg mapping to g)
  public:
    @dataclass IngredientMeasure / GramRange / Coverage  (moved from domain/units.py)
    def to_grams(measure, *, density_g_per_ml=None, count_weight_g=None, owner_food=None) -> GramRange
    def owner_serving_grams(measure, owner_food) -> GramRange | None
    def convert_quantity(qty: Decimal, from_unit: str, to_unit: str) -> Decimal
    def canonical_pantry_unit(value: str) -> str
    def apply_quantity_deduction(pantry: PantryQuantity, grocery: PantryQuantity) -> QuantityDeduction
    def reverse_quantity_deduction(deduction, *, pantry, grocery) -> tuple[PantryQuantity, PantryQuantity]

domain/units.py                             # shim for one release
  from cookfully.domain.ingredient_nutrition.quantities import IngredientMeasure, GramRange, Coverage, to_grams, coverage_ratio

application/ingredient_engine.py            # only public import
  class IngredientEngine:
    def to_grams(self, measure: IngredientMeasure, *, owner_food=None, density_g_per_ml=None, count_weight_g=None) -> GramRange
    def convert_quantity(self, qty: Decimal, from_unit: str, to_unit: str) -> Decimal
    def canonical_pantry_unit(self, value: str) -> str
    def apply_deduction(self, pantry: PantryQuantity, grocery: PantryQuantity) -> QuantityDeduction
    def reverse_deduction(self, deduction: QuantityDeduction, *, pantry: PantryQuantity, grocery: PantryQuantity) -> tuple[PantryQuantity, PantryQuantity]

application/pantry.py                       # persistence + thin wrappers
  from cookfully.application.ingredient_engine import engine
  def canonical_pantry_unit(v): wrappers mapping unsafe_conversion → pantry_unit_unsupported
  def convert_quantity(qty, from_unit, to_unit): wrappers mapping unsafe_conversion → pantry_unit_unsupported / pantry_unit_incompatible
  def apply_quantity_deduction -> engine.apply_deduction
  def reverse_quantity_deduction -> engine.reverse_deduction
  PantryService unchanged (calls engine)

application/corrections.py + application/recipes.py
  from cookfully.application.ingredient_engine import engine
  both replace private owner_serving branch with: engine.to_grams(measure, owner_food=food, density_g_per_ml=density_for(food.description))
```

No database migration. No API shape change. Boundary test enforces only `domain/ingredient_nutrition/quantities.py` and `application/ingredient_engine.py` import `pint`.

## Detailed Design

### 1. Core module (`domain/ingredient_nutrition/quantities.py`)

Owns the single `UnitRegistry` instance and the alias table. Helper `_normalize_alias(value)` does `value.strip().casefold().rstrip(".")` before lookup, matching pantry's current normalization. Lookup yields `(dimension, pint_name, factor)` equivalently via Pint rather than manual `Decimal` factors — the registry defines the factors, the table defines the aliases. Short canonical for storage: `milligram/gram → g`, `kilogram → kg`, `milliliter → ml`, `liter → l`, `item → count`; lookup still accepts the long forms.

Signatures:

```python
@dataclass(frozen=True, slots=True)
class IngredientMeasure: minimum, maximum, unit_code, optional=False, matched=True

@dataclass(frozen=True, slots=True)
class GramRange: minimum: Decimal; maximum: Decimal; method: str; assumption: str | None

def owner_serving_grams(measure: IngredientMeasure, owner_food: OwnerFood) -> GramRange | None:
    if owner_food.typical_serving_g is None or not owner_food.typical_serving_unit: return None
    if (measure.unit_code or "").casefold() != owner_food.typical_serving_unit.casefold(): return None
    # quantize with NUTRIENT_SCALE, mirror corrections.py logic (quantity_min/max or fallback to 1 serving)
    return GramRange(..., method="owner_serving", assumption=f"1 {unit} = {g}g ({display_name})")

def to_grams(measure: IngredientMeasure, *, density_g_per_ml=None, count_weight_g=None, owner_food=None) -> GramRange:
    if owner_food is not None:
        if (r := owner_serving_grams(measure, owner_food)) is not None: return r
    # then same Pint dispatch as today: mass → _pint_factor, volume → *density, item → count_weight, else unsafe_conversion

def convert_quantity(qty: Decimal, from_unit: str, to_unit: str) -> Decimal:
    # alias lookup → Pint factor ratio → quantize_decimal(..., NUTRIENT_SCALE)
    # raises DomainError pan-mapped by pantry wrappers

def canonical_pantry_unit(value: str) -> str: ...
def apply_quantity_deduction(...) -> QuantityDeduction: ...
def reverse_quantity_deduction(...) -> tuple[...]: ...
```

`_pint_factor` stays as `Decimal(str(UNIT_REGISTRY.Quantity(1, src).to(dst).magnitude))` for bit-identical quantized results.

### 2. Shim (`domain/units.py`)

Re-exports `IngredientMeasure`, `GramRange`, `Coverage`, `to_grams`, `coverage_ratio` from `quantities.py` so existing imports keep working for one release. No new logic.

### 3. Engine facade (`application/ingredient_engine.py`)

Adds the four quantity methods. Each delegates directly to `quantities.py` — no branching. `to_grams` is the only place `owner_serving` vs Pint dispatch lives.

### 4. Pantry wrappers (`application/pantry.py`)

Keep public names and error codes. Each wrapper calls the engine/quantities helper and maps domain errors:

- `DomainError("unsafe_conversion")` / `("quantity_unavailable")` from `convert_quantity`/`canonical_pantry_unit` → `DomainError("pantry_unit_unsupported", 422)` or `("pantry_unit_incompatible", 422)` depending on whether one or both aliases failed vs dimension mismatch.
- `apply_quantity_deduction`/`reverse_quantity_deduction` behavior is otherwise identical, including `NUTRIENT_SCALE` quantization and the `"Exact same-dimension Pint conversion"` assumption text updated to mention Pint.

## Data Flow

```
recipe ingredient (quantity_min/max, unit_code, original_text)
  → IngredientMeasure(+ optional/matched)
  → engine.to_grams(measure, owner_food=food|None, density_g_per_ml=density_for(food.description), count_weight_g=...)
      1. owner_serving_grams if unit matches owner_food.typical_serving_unit → GramRange(owner_serving)
      2. else MASS_UNITS via Pint → gram
      3. else VOLUME_UNITS via Pint(milliliter) * density
      4. else item via count_weight
      else → DomainError(unsafe_conversion)
  → grams_min/max (+ method/assumption) stored on IngredientMatch

pantry deduction:
  PantryItemRead (short canonical g/kg/ml/l/count) + grocery PantryQuantity
    → engine.apply_deduction(pantry, grocery)
      convert_quantity via Pint alias table (tbsp→ml 15, cup→ml 240, oz→g 28.3495…)
      quantize NUTRIENT_SCALE → QuantityDeduction(before/after, amounts)
```

## Error Handling

Domain errors are `DomainError` at 422: `quantity_unavailable`, `negative_quantity`, `invalid_range`, `density_required`, `count_weight_required`, `unsafe_conversion`, `pantry_deduction_state_changed` (409 for reverse). Pantry wrappers preserve the public codes `pantry_unit_unsupported` / `pantry_unit_incompatible` / `pantry_quantity_negative` so frontend/clients see no change. Empty/None quantity or unit → `quantity_unavailable`. Cross-dimension `g → ml` → `unsafe_conversion` mapped to `pantry_unit_incompatible`. Truly unknown aliases (`"scoop"` without owner_serving context where handler not involved) remain unsupported when passed to pure `convert_quantity`.

## Testing

- **Behavioral equivalence:** `tests/unit/test_pantry.py`, `test_ingredient_processing.py`, `test_grocery_aggregation.py`, and the owner-food flows in `application/corrections.py` / `recipes.py` must pass without assertion edits. Existing deduction factors must stay identical at `NUTRIENT_SCALE`.
- **New sync/parity test** `tests/unit/test_quantity_sync.py` — parametrize `convert_quantity` across old aliases (`mg↔g`, `g↔kg`, `ml↔l`, `count↔count`) and new aliases (`tbsp→ml` 15, `tsp→ml` 5, `cup→ml` 240, `oz→g` 28.349523125, `lb→g` 453.59237) asserting engine result equals `Decimal(str(Pint factor))` * qty quantized to `NUTRIENT_SCALE`; plus `owner_serving` cases: matching unit (`scoop`/`Scoop` casefold), non-matching unit, `None` quantity, inactive owner food.
- **Boundary test extension:** `tests/unit/test_ingredient_engine_boundary.py` already forbids outside imports of `domain.ingredient_nutrition`; extend to assert only `quantities.py` and `ingredient_engine.py` import `pint`, and the only `def to_grams`/`def convert_quantity`/`_UNITS` bodies live in `quantities.py` (+ wrappers). Wrapper bodies must be ≤ 3 lines and delegate.
- Gates per `AGENTS.md`: `ruff format --check` / `ruff check` / `mypy src` / `pytest` / `pnpm --dir frontend typecheck` as applicable.

## Alternatives Considered

- **Swap _UNITS in place** — replace factors inside `pantry.py` only; no new domain file. Prolongs two Pint owners. Rejected.
- **Engine shim with fallback** — try Pint then fall back to old `_UNITS`. Preserves exact old factors but leaves two truth tables. Rejected.
- **Import domain into infrastructure** — rejected in P2; same layering argument applies.

## Risks

- Pint factor string rounding vs hand-rolled `Decimal("0.001")` — mitigated by parity tests and `Decimal(str(magnitude))` quantization.
- Short canonical drift (`gram` vs `g`) — shim `canonical_pantry_unit` returns short form; storage stays `g/kg/ml/l/count`.
- Missed `owner_serving` casefold or `None` quantity — covered by sync tests.
- Expanding pantry to `tbsp`/`cup`/`oz` without UI changes — reads/writes still accept the aliases; display keeps short canonical, no migration needed.

## Phasing

This spec covers P3 only. P4 will move `coverage_ratio`, aggregation, CORE codes, and Atwater fallback into `domain/ingredient_nutrition/{nutrition_data,computation}.py` and expose them via `IngredientEngine.aggregate` / `scale_servings`.
