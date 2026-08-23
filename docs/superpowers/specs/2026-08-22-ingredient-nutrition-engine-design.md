# Ingredient & Nutrition Engine — Design

Date: 2026-08-22
Status: Approved
Supersedes: pantry-matching portion of "use neural model by default" discussion; delivers that as Phase 1.

## Problem

Ingredient-and-nutrition logic is scattered across call sites with divergent implementations:

- **Embedder selection ×3** with different cache keys and error handling: `api/routes/foods.py:56` (`_configured_search_embedder`), `jobs/recipe_pipeline.py:446` (`_embedder_for_session`), `application/food_embedding_index.py:91`.
- **Normalization ×5+**: `normalize_food` (application/food_matching.py), `normalize_pantry_name` (application/pantry.py), `normalize_food_name` (grocery), a CLI variant, `food_semantics._normalize`; singularization duplicated in SQL `_token_variants` and Python `_tokens/_singular`.
- **Two matchers with different vocabularies**: `FoodMatcher` (matched/ambiguous/unmatched) vs pantry `match_food_name` — a bare `difflib.SequenceMatcher` ratio producing matched/proposed/unmatched.
- **Owner-serving grams computation duplicated verbatim**: `application/recipe_corrections.py:211-230` vs `application/recipes.py:678-701`.
- **Two unit systems**: Pint-backed conversion vs pantry's private `_UNITS` table.
- **CORE nutrient codes + Atwater fallback live in the job layer** (`jobs/recipe_pipeline.py:100`) instead of beside nutrition math.

Every feature re-implements pieces; behavior drifts per surface.

## Goal

One authoritative Ingredient & Nutrition domain module with a strict boundary and a single facade. All features — recipe page, meal builder, import pipeline, foods picker, pantry, admin/future surfaces — consume it. Not a separately deployed microservice: an isolated in-process module.

## Architecture

### Domain package

```
backend/src/cookfully/domain/ingredient_nutrition/
    __init__.py
    matching.py        # FoodMatcher, scoring signals, thresholds, MatchDecision/FoodCandidate
    normalization.py   # normalize, tokenize, singularize, aliases, semantic profiles entry
    nutrition_data.py  # per-100g lookup contracts, CORE nutrient codes, Atwater fallback
    quantities.py      # Pint-backed unit/quantity conversion, density-to-grams estimation
    computation.py     # scaling, aggregation, coverage, label-override merge, serving math
```

### Application facade

```
backend/src/cookfully/application/ingredient_engine.py

class IngredientEngine:
    def match_ingredient(self, session, name: str, *, preferred=None) -> MatchDecision
    def search_foods(self, session, query: str, *, limit: int) -> tuple[FoodCandidate, ...]
    def normalize(self, value: str) -> NormalizedIngredient
    def to_grams(self, quantity, unit, food_description=None) -> GramsEstimate
    def scale_servings(self, nutrients, factor) -> NutrientTotals
    def aggregate(self, ingredient_results) -> NutritionComputation
```

`IngredientEngine` is the only symbol consumers import. Result dataclasses (`MatchDecision`, `NormalizedIngredient`, `GramsEstimate`, `NutrientTotals`, `NutritionComputation`) carry confidence/match metadata uniformly.

### Boundary enforcement

An architecture test asserts that outside `domain/ingredient_nutrition/` and `application/ingredient_engine.py`, no module imports `domain.ingredient_nutrition.*`. Routes, jobs, import pipeline, cook mode, MCP adapters may depend only on `IngredientEngine`.

### Embedding/model policy (internal to the engine)

- Reads the `nutrition_intelligence_settings` singleton (`backend ∈ {hashing, fastembed}`, `model_name`, `model_revision`, `last_ready_at`).
- One cached factory keyed by `(backend, model_name, revision)` replaces the three existing copies; retry-on-unavailable keeps today's 30-second cadence semantics.
- Default backend becomes `fastembed` (neural). Policy:
  - Automatic/background paths (pantry auto-match, recipe pipeline): if the model is not downloaded/ready, fall back to `HashingTextEmbedder` transparently rather than failing the operation.
  - Interactive settings-driven flows keep explicit readiness errors (409 `embedding_model_not_ready` / 503 `embedding_model_unavailable`) so the Settings page can drive download state.
- The engine exposes this via an internal `fallback: bool` parameter on its embedder resolution; call sites choose policy once, not ad hoc.

## Behavior decisions

1. **Default = neural**: migration flips `nutrition_intelligence_settings.backend` column default to `'fastembed'`, sets `model_name` default `'BAAI/bge-small-en-v1.5'`, and updates any existing row still on hashing defaults.
2. **Pantry matcher unified**: pantry `_resolve_match` calls `IngredientEngine.match_ingredient`. The SequenceMatcher implementation is deleted. Status mapping: engine `matched` → pantry `matched`; engine `ambiguous` (0.65–0.80 candidate band) → pantry `proposed`; engine `unmatched` → pantry `unmatched`; explicit user selection stays `manual` with confidence 1. Confidence shown by the Review-match chip is now the shared scorer's score.
3. **Thresholds unchanged**: ≥ 0.80 with clear runner-up margin auto-accepts; 0.65–0.80 proposes; < 0.65 unmatched.
4. **Grocery normalization** keeps its aggregation-specific wrapper but delegates tokenization to `normalization.py` (full merge evaluated in P3, not forced).
5. Exact-decimal policies (`NUTRIENT_SCALE`, `quantize_decimal`) move with the computation code into the domain package — values and serialization are unchanged.

## Phasing (each phase independently shippable, all tests green)

- **P1 – Engine skeleton + matching unification**: create package + facade with `match_ingredient`/`search_foods`; move FoodMatcher; single embedder factory; pantry onto the engine; default-flip migration; delete SequenceMatcher path and the three duplicated factories.
- **P2 – Normalization unification**: consolidate the five variants behind `normalization.py`; callers re-pointed.
- **P3 – Quantities**: pantry `_UNITS` table replaced by Pint-backed `quantities.py`; owner-serving grams duplication collapsed.
- **P4 – Computation**: CORE codes/Atwater out of the job layer into `nutrition_data.py`; aggregation/coverage/serving math exposed via `aggregate()`/`scale_servings()`.

P2–P4 get their own plans after P1 lands (each reshapes code the next touches).

## Testing strategy

- Architecture test enforcing the import boundary.
- Unit tests for the facade: embedder caching, fallback policies, settings-change cache invalidation.
- Pantry contract/unit tests updated for new confidence semantics (same thresholds as the corpus-validated matcher).
- Existing suites re-pointed at the engine without assertion changes wherever possible; corpus accuracy benchmarks must not regress (`accuracy/test_nutrition_corpus.py`, food-matching corpus test).
- Full AGENTS.md verification gate per phase.

## Rejected alternatives

- Separately deployed microservice: unnecessary for self-hosted scale; adds network/deployment complexity for zero benefit at this size.
- Big-bang consolidation of all capabilities in one change: too risky; phased delivery keeps every commit green.
