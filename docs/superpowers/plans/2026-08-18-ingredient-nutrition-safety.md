# Ingredient-to-Nutrition Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent silent wrong ingredient matches, make nutrition coverage reflect usable quantities, and add regression coverage for the highest-risk mapping failures.

**Architecture:** Keep the existing deterministic matcher, review state, provisional estimate state, and USDA provenance model. Tighten the automatic-match eligibility gate in the domain/application layer, make `coverage_ratio` defensive about missing quantities, and encode adversarial cases in unit and integration tests rather than adding a new matching engine.

**Tech Stack:** Python 3.13, FastAPI domain/application layers, SQLAlchemy 2, PostgreSQL reference foods, pytest, Pydantic 2.

## Global Constraints

- Preserve original ingredient text, nutrition provenance, serving basis, and active correction precedence.
- Background handlers remain idempotent and reject stale input hashes.
- Use fixed-precision decimals for stored nutrition and scaled integers for solver inputs.
- Do not silently substitute a reference food when the requested identity, part, state, or form is absent.
- Keep optional ingredients outside required coverage while counting unresolved non-optional ingredients against coverage.
- Do not change the checked-in USDA releases or benchmark reference values.

---

### Task 1: Enforce Full Identity Containment

**Files:**
- Modify: `backend/src/cookfully/application/food_matching.py:239-303`
- Modify: `backend/src/cookfully/domain/food_semantics.py:164-212`
- Test: `backend/tests/unit/test_food_matching_corpus.py`
- Test: `backend/tests/unit/test_food_semantics.py`

**Interfaces:**
- `FoodMatcher.decide()` continues returning `matched`, `ambiguous`, or `unmatched` through the existing `MatchDecision` contract.
- `compare_compatibility()` continues returning `CompatibilityResult`; missing requested attributes become `REVIEW`, not a new enum value.

- [ ] **Step 1: Write failing matcher tests**

Add cases proving that a generic candidate cannot satisfy a more specific query:

```python
def test_generic_chicken_does_not_auto_match_chicken_breast() -> None:
    matcher = FoodMatcher(
        FoodRepositoryStub([food("generic", "Chicken, meat only, raw")])
    )

    decision = matcher.decide("chicken breast")

    assert decision.status in {"ambiguous", "unmatched"}
    assert decision.candidate is None


def test_partial_semantic_identity_does_not_auto_match() -> None:
    matcher = FoodMatcher(
        FoodRepositoryStub([food("generic", "Chicken, meat only, raw")])
    )

    decision = matcher.decide("chicken breast")

    assert decision.status != "matched"
```

Add semantic compatibility tests for missing requested attributes:

```python
def test_missing_requested_part_requires_review() -> None:
    result = compare_compatibility(
        profile_from_text("chicken breast"),
        profile_from_text("Chicken, meat only, raw"),
    )

    assert result.compatibility is Compatibility.REVIEW


def test_missing_requested_state_requires_review() -> None:
    result = compare_compatibility(
        profile_from_text("cooked chicken"),
        profile_from_text("Chicken, meat only"),
    )

    assert result.compatibility is Compatibility.REVIEW
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
uv run --directory backend pytest tests/unit/test_food_matching_corpus.py tests/unit/test_food_semantics.py -q
```

Expected: the new generic-chicken and missing-attribute assertions fail because the current scorer grants a semantic identity bonus to partial token matches and compatibility does not review all missing requested attributes.

- [ ] **Step 3: Remove the partial-match auto-eligibility path**

In `FoodMatcher._score`, keep partial candidates ranked for review but cap them below the automatic threshold. The branch handling `semantic_identity_bonus` must not return a score above `0.600000` when `len(intersection) < len(query_set)`. Full-token matches retain the current lead/block/head signals and penalties.

- [ ] **Step 4: Mark missing requested attributes as review-required**

In `compare_compatibility`, add review reasons for a candidate that lacks a requested query attribute:

```python
if query.part and candidate.part is None:
    review = True
    reasons.append("candidate_part_not_represented")
if query.state and candidate.state is None:
    review = True
    reasons.append("candidate_state_not_represented")
if query.form and candidate.form is None:
    review = True
    reasons.append("candidate_form_not_represented")
```

Keep hard conflicts unchanged. Because `decide()` only auto-matches `Compatibility.COMPATIBLE`, these cases remain visible alternatives without silently contributing nutrition.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run the same focused pytest command. Expected: all matcher and semantic tests pass, including the existing positive cases for Greek yogurt, brown rice, raw banana, and generic extra-firm tofu.

### Task 2: Make Coverage Require Usable Quantities

**Files:**
- Modify: `backend/src/cookfully/domain/units.py:115-124`
- Modify: `backend/src/cookfully/jobs/recipe_pipeline.py:462-475`
- Test: `backend/tests/unit/test_ingredient_processing.py`
- Test: `backend/tests/integration/test_recipe_jobs.py`
- Modify: `docs/nutrition-methodology.md:11-18`

**Interfaces:**
- `coverage_ratio(ingredients)` keeps returning `Coverage`; missing required quantities count as unresolved rather than being treated as matched.
- Recipe rollup continues storing `grams_min` and `grams_max`, while coverage is based on the usable minimum quantity and active food resolution.

- [ ] **Step 1: Write failing coverage tests**

Add a unit case:

```python
def test_unquantified_required_match_does_not_count_as_resolved() -> None:
    coverage = coverage_ratio(
        [
            IngredientMeasure(Decimal("100"), None, "gram", matched=True),
            IngredientMeasure(None, None, None, matched=True),
        ]
    )

    assert coverage.mass == Decimal("1.000000")
    assert coverage.required_count == Decimal("0.500000")
    assert coverage.overall == Decimal("0.500000")
```

Add an integration case using the existing recipe-job fixture helpers: a quantified matched ingredient plus a required `to taste` ingredient that resolves to a food reference must produce `coverage_ratio == Decimal("0.500000")`, not `1.000000`.

- [ ] **Step 2: Run the focused coverage tests and verify they fail**

Run:

```powershell
uv run --directory backend pytest tests/unit/test_ingredient_processing.py tests/integration/test_recipe_jobs.py -q
```

Expected: the new count-coverage assertion fails because the current count numerator includes matched ingredients with no minimum quantity.

- [ ] **Step 3: Correct the domain coverage calculation**

In `coverage_ratio`, keep every required ingredient in the count denominator, but count an ingredient as resolved only when both `item.matched` and `item.minimum is not None` are true:

```python
count = Decimal(
    sum(1 for item in required if item.matched and item.minimum is not None)
) / Decimal(len(required) or 1)
```

This preserves the conservative denominator while preventing a no-quantity match from inflating coverage.

- [ ] **Step 4: Make the pipeline pass the defensive match flag**

In `_rollup`, set `matched` only when the active match has a food reference or owner food and `grams is not None`. A reference match with no convertible quantity must remain visible in the match record and assumptions, but must not be treated as a nutrition-resolved contribution.

- [ ] **Step 5: Update the methodology contract**

Clarify that required count coverage means resolved identity **and** usable quantity. State that matched-but-unquantified ingredients remain unresolved for nutrition coverage and cannot make a recipe complete.

- [ ] **Step 6: Run the focused tests and verify they pass**

Run the unit and integration command from Step 2. Expected: all existing coverage, source-provided estimate, partial-rollup, and recipe-job tests pass.

### Task 3: Add Safety Evaluation Coverage

**Files:**
- Modify: `backend/tests/unit/test_food_matching_corpus.py`
- Modify: `backend/tests/unit/test_ingredient_processing.py`
- Modify: `backend/tests/integration/test_recipe_jobs.py`
- Modify: `docs/nutrition-methodology.md:40-57`

**Interfaces:**
- No production API changes.
- The evaluation suite documents false-auto-match prevention as a release requirement alongside macro-error and completeness thresholds.

- [ ] **Step 1: Add a table-driven adversarial matching set**

Cover these expected non-auto-match cases: generic chicken for chicken breast, generic chicken for cooked chicken, raw banana for banana powder, whole milk for buttermilk, raw rice for rice flour, and lemon grass for lemon juice. Each case must assert `candidate is None` whenever the candidate lacks the requested identity or attribute.

- [ ] **Step 2: Add coverage integrity assertions**

Cover required ingredients with no quantity, failed density conversion, unmatched food identity, optional missing ingredients, and fully resolved mass/count inputs. Assert both mass and count coverage so a single aggregate score cannot hide which basis failed.

- [ ] **Step 3: Run the complete backend suite and inspect failures**

Run:

```powershell
uv run --directory backend pytest
```

Expected: all tests pass. Any changed expected coverage must be limited to cases that previously counted an unusable quantity as resolved.

- [ ] **Step 4: Document the release gate**

Update the methodology error-gate section to require zero known critical false-auto-match cases in the adversarial suite, while retaining the existing 90% completeness and median nutrient-error thresholds.

### Task 4: Full Verification and Delivery

**Files:**
- No additional production files unless verification exposes a failure from Tasks 1-3.

- [ ] **Step 1: Run backend quality checks**

```powershell
uv run --directory backend ruff format --check .
uv run --directory backend ruff check .
uv run --directory backend mypy src
```

- [ ] **Step 2: Run frontend checks for regression safety**

```powershell
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
```

- [ ] **Step 3: Inspect the final diff**

Run `git diff --check`, `git status --short`, and `git diff --stat`. Confirm no secrets, generated archives, or unrelated files are staged.

- [ ] **Step 4: Commit only after verification**

Use a concise commit message such as:

```powershell
git add backend frontend docs/nutrition-methodology.md
git commit -m "fix: harden ingredient nutrition resolution"
```

- [ ] **Step 5: Push and verify the remote**

```powershell
git push origin main
git status --short
git rev-parse HEAD
git rev-parse origin/main
```

Expected: the worktree is clean and the two commit hashes match.
