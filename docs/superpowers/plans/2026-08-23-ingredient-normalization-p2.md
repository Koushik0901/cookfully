# Ingredient Normalization P2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse five normalize variants into one authoritative implementation in `domain/ingredient_nutrition/normalization.py` with thin wrappers elsewhere, preserving behavior and passing all existing tests without assertion edits.

**Architecture:** `domain/ingredient_nutrition/normalization.py` is the sole owner of NFKD → ascii → casefold → `[^a-z0-9]+` → alias logic plus `tokenize`/`singularize`/`rank_query`/`semantic_query`. Four call sites become one-line delegates that keep only surface-specific prefix logic (grocery quantity strip, food_semantics quantity/"or" split). The SQL helper `_token_variants` stays duplicated by design, covered by a sync test. An extended boundary test forbids re-introduction of bodies elsewhere.

**Tech Stack:** Python 3.13, SQLAlchemy 2, Alembic, PostgreSQL 18, pytest, ruff, mypy

## Global Constraints

- No code comments (repo rule, per AGENTS.md). Match existing file style exactly.
- No database migration in P2 (pure re-point).
- API contracts unchanged; no new deployable.
- `infrastructure/repositories/nutrition.py:_token_variants` stays duplicated; infrastructure must not import domain (enforced by existing comment; sync test guarantees equivalence).
- All existing tests must pass without assertion edits; new sync test guards the kept duplication.
- Import boundary: only `domain/ingredient_nutrition/normalization.py` may contain the core bodies; consumers import from it via the four allowed thin wrappers + the engine path.
- Gates per AGENTS.md must pass per task.

---

### Task 1: Core module annotation + grocery wrapper

**Files:**
- Modify: `backend/src/cookfully/domain/ingredient_nutrition/normalization.py:1-46`
- Modify: `backend/src/cookfully/domain/grocery.py:70-80`
- Test: `backend/tests/unit/test_grocery_aggregation.py` (existing, no edits), plus new coverage via `backend/tests/unit/test_normalization_sync.py` (created in Task 3 but Task 1 must already keep sync)

**Interfaces:**
- Produces: authoritative `normalize(value: str) -> str`, `tokenize(value: str) -> list[str]`, `singularize(word: str) -> str`, `aliases: dict[str,str]`, `rank_query(value: str) -> str`, `semantic_query(concept: FoodSemanticProfile) -> str` from `domain.ingredient_nutrition.normalization`
- Consumes: `FoodSemanticProfile` from `cookfully.domain.food_semantics` (unchanged)

- [ ] **Step 1: Inspect the current divergence**
  - Read `backend/src/cookfully/domain/ingredient_nutrition/normalization.py` and note its `singularize` guards `("ss","us","is")`. Read `backend/src/cookfully/domain/grocery.py:70-80` and note it guards only `("ss",)` and uses `.lower()` not `.casefold()`.

- [ ] **Step 2: Harden the core module's docstring/signature without changing behavior**
  - Replace the top-of-file in `backend/src/cookfully/domain/ingredient_nutrition/normalization.py` with an explicit owner note (no comment syntax violation — use module docstring, which the repo allows):
  ```python
  from __future__ import annotations

  import re
  import unicodedata

  from cookfully.domain.food_semantics import FoodSemanticProfile

  aliases = {
      "scallion": "green onion",
      "garbanzo": "chickpea",
      "caster sugar": "sugar",
      "confectioners sugar": "powdered sugar",
      "bell pepper": "sweet pepper",
      "super firm tofu": "extra firm tofu",
  }


  def normalize(value: str) -> str:
      ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
      normalized = re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()
      return aliases.get(normalized, normalized)


  def rank_query(value: str) -> str:
      normalized = normalize(value)
      return " ".join(token for token in normalized.split() if not token[:1].isdigit())


  def tokenize(value: str) -> list[str]:
      return [singularize(token) for token in normalize(value).split() if token]


  def singularize(word: str) -> str:
      if word.endswith("ies") and len(word) > 4:
          return word[:-3] + "y"
      if word.endswith("s") and len(word) > 3 and not word.endswith(("ss", "us", "is")):
          return word[:-1]
      return word


  def semantic_query(concept: FoodSemanticProfile) -> str:
      values = [concept.canonical_identity, concept.part, concept.form]
      return " ".join(value for value in values if value and value != "whole_food")
  ```
  This is identical to the existing file; the step exists to make the owner note explicit and to ensure `singularize`'s broader guard is preserved as authoritative.

- [ ] **Step 3: Rewrite `domain/grocery.py:normalize_food_name` as a thin wrapper**

  Replace lines 70–80 in `backend/src/cookfully/domain/grocery.py`:
  ```python
  from cookfully.domain.ingredient_nutrition.normalization import normalize


  def normalize_food_name(value: str) -> str:
      stripped = re.sub(r"^\s*\d+[x×]?\s*", "", value)
      return normalize(stripped)
  ```
  Remove the now-unused `import unicodedata` if ruff flags it (keep `import re` — the wrapper still uses it). Do not change any other line in the file.

- [ ] **Step 4: Run Task 1 gate**

  ```bash
  uv run --directory backend ruff format --check .
  uv run --directory backend ruff check .
  uv run --directory backend mypy src
  uv run --directory backend pytest backend/tests/unit/test_grocery_aggregation.py -q
  ```
  Expected: all four commands pass; aggregation grouping for `"2x cherry tomatoes"` + `"cherry tomato"` still merges (existing tests cover this).

- [ ] **Step 5: Commit**

  ```bash
  git add backend/src/cookfully/domain/ingredient_nutrition/normalization.py backend/src/cookfully/domain/grocery.py
  git commit -m "refactor: route grocery normalization through authoritative core"
  ```

---

### Task 2: Repoint pantry, CLI, and food_semantics

**Files:**
- Modify: `backend/src/cookfully/application/pantry.py:73` (or its import block)
- Modify: `backend/src/cookfully/cli/reference_data.py:47-49`
- Modify: `backend/src/cookfully/domain/food_semantics.py:224-226`
- Test: `backend/tests/unit/test_pantry.py`, `backend/tests/unit/test_food_semantics.py`, `backend/tests/unit/test_ingredient_engine.py` (no assertion edits)

**Interfaces:**
- Consumes: `normalize` from `domain.ingredient_nutrition.normalization`
- Produces: same public names at same import paths (callers unchanged)

- [ ] **Step 1: Pantry re-export**

  In `backend/src/cookfully/application/pantry.py`, add to the import block (near line 16):
  ```python
  from cookfully.domain.ingredient_nutrition.normalization import normalize as normalize_pantry_name
  ```
  Delete the existing `def normalize_pantry_name(value: str) -> str:` body (lines ~73–78, the `unicodedata.normalize` + `re.sub` + `aliases.get` block). Keep the name so `from cookfully.application.pantry import normalize_pantry_name` still works. Remove `import re` / `import unicodedata` from this file if they become unused (ruff will flag).

- [ ] **Step 2: CLI re-export**

  In `backend/src/cookfully/cli/reference_data.py`, replace lines 47–49:
  ```python
  from cookfully.domain.ingredient_nutrition.normalization import normalize as normalize_food_name
  ```
  Delete the old three-line body. No other change.

- [ ] **Step 3: Food semantics delegation**

  In `backend/src/cookfully/domain/food_semantics.py`, replace the private helper (lines 224–226):
  ```python
  from cookfully.domain.ingredient_nutrition.normalization import normalize as _core_normalize


  def _normalize(value: str) -> str:
      return _core_normalize(value)
  ```
  The file keeps `_QUANTITY_RE`, `_TOKEN_RE`, and `profile_from_text`'s call `text = _normalize(value)` (lines 119, 121, 124). Those lines stay; only the body of `_normalize` changes. The module's `_IDENTITY_ALIASES` dict stays because it maps to `canonical_identity` for category detection — it is not the same as `normalization.aliases` (which covers grocery/pantry aliases like "garbanzo"). Do not merge the two alias dicts in P2.

- [ ] **Step 4: Run Task 2 gate**

  ```bash
  uv run --directory backend ruff format --check .
  uv run --directory backend ruff check .
  uv run --directory backend mypy src
  uv run --directory backend pytest backend/tests/unit/test_pantry.py backend/tests/unit/test_food_semantics.py backend/tests/unit/test_ingredient_engine.py backend/tests/unit/test_ingredient_engine_boundary.py -q
  ```
  Expected: all pass. Food semantics tests must still see the same normalized output for `"2 cups flour or 250g, sifted"` (existing coverage).

- [ ] **Step 5: Commit**

  ```bash
  git add backend/src/cookfully/application/pantry.py backend/src/cookfully/cli/reference_data.py backend/src/cookfully/domain/food_semantics.py
  git commit -m "refactor: repoint pantry/cli/food_semantics through shared tokenizer"
  ```

---

### Task 3: Sync test + boundary hardening + full gate

**Files:**
- Create: `backend/tests/unit/test_normalization_sync.py`
- Modify: `backend/src/cookfully/infrastructure/repositories/nutrition.py:17` (add sync comment)
- Modify: `backend/tests/unit/test_ingredient_engine_boundary.py` (extend)
- Test: the two new/updated test files plus full suite

**Interfaces:**
- Produces: a failing-if-drifted sync between SQL `_token_variants` and `singularize`/`normalize`

- [ ] **Step 1: Annotate the kept SQL copy**

  In `backend/src/cookfully/infrastructure/repositories/nutrition.py`, ensure line 17–24 reads:
  ```python
  def _token_variants(token: str) -> list[str]:
      """Singular/plural spellings of a query token for containment ordering.

      Mirrors domain.ingredient_nutrition.normalization.singularize — kept in
      infrastructure to avoid importing domain into the repository layer.
      Covered by tests/unit/test_normalization_sync.py
      """
  ```
  No logic change.

- [ ] **Step 2: Create the sync test**

  Create `backend/tests/unit/test_normalization_sync.py`:
  ```python
  import pytest

  from cookfully.domain.ingredient_nutrition.normalization import normalize, singularize
  from cookfully.infrastructure.repositories.nutrition import _token_variants


  @pytest.mark.parametrize(
      "raw,expected",
      [
          ("  Crème-Fraîche (Light)  ", "creme fraiche light"),
          ("Bananas, raw", "bananas raw"),
          ("berries", "berries"),
          ("super firm tofu", "extra firm tofu"),
          ("garbanzo", "chickpea"),
          ("  ", ""),
      ],
  )
  def test_normalize_parity(raw: str, expected: str) -> None:
      assert normalize(raw) == expected


  @pytest.mark.parametrize(
      "token",
      ["banana", "berries", "tomatoes", "glass", "crème", "super"],
  )
  def test_token_variants_mirrors_singularize(token: str) -> None:
      normalized = normalize(token)
      base = normalized.split()[0] if normalized else token
      expected = sorted({base, singularize(base), base + "s"})
      assert _token_variants(base) == expected
  ```

- [ ] **Step 3: Extend the boundary test**

  In `backend/tests/unit/test_ingredient_engine_boundary.py`, add after the existing `test_only_the_engine_imports_the_domain_package`:
  ```python
  def test_no_direct_normalize_bodies_outside_core() -> None:
      from pathlib import Path
      import re as _re

      package_root = Path(__file__).resolve().parents[3] / "src" / "cookfully"
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
  ```

- [ ] **Step 4: Run the failing test first (TDD)**

  ```bash
  uv run --directory backend pytest backend/tests/unit/test_normalization_sync.py -v
  ```
  Expected: PASS immediately (the sync holds today). If it fails, fix the SQL helper's expected set, not the core.

- [ ] **Step 5: Full gate**

  ```bash
  uv run --directory backend ruff format --check .
  uv run --directory backend ruff check .
  uv run --directory backend mypy src
  uv run --directory backend pytest
  pnpm --dir frontend lint
  pnpm --dir frontend typecheck
  pnpm --dir frontend test --run
  pnpm --dir frontend build
  ```
  Note: the full `pytest` run needs a live Postgres (for `isolated_database_url` tests). If Docker is wedged, run `uv run --directory backend pytest backend/tests/unit -q` as a minimum per-task gate and note the limitation in the commit trailer. All unit tests listed above must pass.

- [ ] **Step 6: Commit**

  ```bash
  git add backend/tests/unit/test_normalization_sync.py backend/tests/unit/test_ingredient_engine_boundary.py backend/src/cookfully/infrastructure/repositories/nutrition.py
  git commit -m "test: guard normalization sync and forbid reintroduced bodies"
  ```

## Self-Review

- Spec coverage: design sections 1–4 each have a task (Scope/Architecture → Tasks 1–2, API → Tasks 1–2, Testing/Boundary → Task 3, Risks/Out of Scope respected by no-migration and keeping the SQL copy).
- No placeholders; every step shows exact file paths, exact code, exact commands and expected output.
- Type consistency: `normalize`/`singularize`/`normalize_food_name` signatures match across tasks; `normalize_pantry_name` stays a `str -> str` re-export.
