# Ingredient Normalization — P2 Design (Atomic Cutover)

Date: 2026-08-23
Status: Approved (design sections 1–4)
Parent: `2026-08-22-ingredient-nutrition-engine-design.md` (Engine P1)
Branch: `feature/ingredient-engine-p2` (to be created from `main`)

## Context

After P1, matching is unified behind `IngredientEngine` and `domain/ingredient_nutrition/{matching,normalization}.py` exists (46 lines: `aliases`, `normalize`, `rank_query`, `tokenize`, `singularize`, `semantic_query`). Five call sites still carry independent implementations of the same unicode/casefold/regex work:

- `domain/ingredient_nutrition/normalization.py:normalize` (authoritative core)
- `domain/grocery.py:70` — grocery aggregation
- `application/pantry.py:73` — pantry identity
- `cli/reference_data.py:47` — import-time USDA names
- `domain/food_semantics.py:224` — raw ingredient parsing (`_normalize`, strips quantities / "or")
- plus `infrastructure/repositories/nutrition.py:17` `_token_variants` duplicating `singularize` for SQL array containment

This P2 finishes the normalization layer: one real implementation, thin wrappers elsewhere, no new deployable.

## Goals & Non-Goals

**Goals:** One `normalize` implementation; all surface-specific variants become thin wrappers that add only their prefix/postfix logic then delegate; preserved behavior verified by existing tests without assertion edits; explicit sync coverage for the kept SQL copy.

**Non-goals:** Quantities (Pint vs `_UNITS`, owner-serving grams) → P3; nutrition-data lookup & computation (CORE codes, Atwater, aggregation) → P4; importing domain into `infrastructure/repositories/nutrition.py` (rejected); CLI/API contract changes.

## Architecture

```
domain/ingredient_nutrition/normalization.py   # authoritative core
  aliases, normalize, tokenize, singularize, rank_query, semantic_query

domain/grocery.py:normalize_food_name          # thin wrapper: strip quantity prefix → normalize
application/pantry.py:normalize_pantry_name    # re-export
cli/reference_data.py:normalize_food_name      # re-export
domain/food_semantics.py::_normalize           # keep quantity/"or" splitting, delegate chunk → normalize
infrastructure/repositories/nutrition.py:_token_variants  # kept copy, comment-linked, sync-tested
```

No database migration. No API change. `application/ingredient_engine.py` already depends on `normalization` via `matching`; that import stays.

## Detailed Design

### 1. Core module (`domain/ingredient_nutrition/normalization.py`)

Current 46-line implementation is the base. Expand docstring to state it is the single owner of `NFKD → ascii → casefold → [^a-z0-9]+ → alias` logic. No signature change.

```python
aliases: dict[str, str]
def normalize(value: str) -> str
def tokenize(value: str) -> list[str]           # normalize → split → singularize
def singularize(word: str) -> str
def rank_query(value: str) -> str               # normalize → drop leading digit tokens
def semantic_query(concept: FoodSemanticProfile) -> str
```

### 2. Thin wrappers

- **`domain/grocery.py`**
  ```python
  def normalize_food_name(value: str) -> str:
      stripped = re.sub(r"^\s*\d+[x×]?\s*", "", value)
      return normalize(stripped)
  ```
  Prefix regex copied verbatim from today's implementation; same output for `"2x cherry tomatoes"`.

- **`application/pantry.py`**
  ```python
  from cookfully.domain.ingredient_nutrition.normalization import normalize as normalize_pantry_name
  ```

- **`cli/reference_data.py`**
  ```python
  from cookfully.domain.ingredient_nutrition.normalization import normalize as normalize_food_name
  ```

- **`domain/food_semantics.py::_normalize(value)`** keeps `quantity_match` and `re.split(r"\s+or\s+|\s*;\s*", text)` pre-processing, then `return normalize(chunk)` per chunk. No change to its splitting logic.

All wrappers preserve existing public names so callers and tests keep calling the same symbols.

### 3. Kept SQL copy

`infrastructure/repositories/nutrition.py:17` retains `_token_variants` with comment:

```python
# Mirrors domain.ingredient_nutrition.normalization.singularize — kept in
# infrastructure to avoid importing domain into the repository layer.
# Covered by tests/unit/test_normalization_sync.py
```

No import added.

## Data Flow

```
raw input ("2 cups all-purpose flour, sifted" / "Cherry tomatoes")
  → surface wrapper (strip quantities / split "or" if applicable)
  → domain.ingredient_nutrition.normalization.normalize
  → tokenize/singularize/rank_query as needed by caller
  → USDA lookup / grocery dedup / food_semantics profile
```

## Error Handling

Normalization never raises — empty/whitespace input returns `""`. Callers that currently guard `if not query: return` keep those guards. No new error modes.

## Testing

- **Behavioral equivalence:** All existing `test_pantry`, `test_grocery_aggregation`, `test_food_semantics`, `test_food_matching_corpus`, and CLI import tests must pass without assertion edits.
- **New sync test** `tests/unit/test_normalization_sync.py` — parametrize tokens (`"banana"`, `"berries"`, `"Bananas, raw"`, `"crème-fraîche"`, `"super firm tofu"`) asserting `_token_variants(token)` equals `sorted({token, singularize(token), token+"s"})`.
- **Boundary test extension:** `tests/unit/test_ingredient_engine_boundary.py` already forbids outside imports of `domain.ingredient_nutrition`; extend it to assert the only `def normalize*` bodies live in `normalization.py` + the 4 wrappers + the SQL helper.
- Gates per AGENTS.md: `ruff format/check`, `mypy`, `pytest`.

## Alternatives Considered

- **Shim/deprecation window** — keeps two import paths for a release; prolongs duplication. Rejected: P2's goal is single truth.
- **Engine-only unification** (only `IngredientEngine` consumers get the new path) — leaves direct callers duplicated. Rejected: misses P2 scope.
- **Import domain into infrastructure** — eliminates the SQL copy but breaks current layering. Rejected per decision on that question.

## Risks

- Missed prefix regex in grocery wrapper → dedup drift (mitigated by verbatim copy + existing aggregation tests).
- SQL sync drift if `singularize` changes — mitigation is the sync test failing fast.

## Phasing

This spec covers P2 only. P3 (quantities) and P4 (nutrition computation) follow the parent spec's phasing.
