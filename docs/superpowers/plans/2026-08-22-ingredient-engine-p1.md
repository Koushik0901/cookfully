# Ingredient & Nutrition Engine — P1 Implementation Plan (Matching Unification)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the isolated `domain/ingredient_nutrition` package and the `IngredientEngine` facade, unify all food matching (pantry, foods picker, recipe pipeline) behind one settings-driven embedder policy, and make the neural model the default.

**Architecture:** Move the matching core into `domain/ingredient_nutrition/{matching,normalization}.py`; one cached settings→embedder factory replaces three divergent copies; pantry drops its `difflib.SequenceMatcher` matcher and consumes `IngredientEngine.match_ingredient`.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2 / Alembic / PostgreSQL 18; fastembed ONNX (BAAI/bge-small-en-v1.5) with hashing fallback.

**Spec:** `docs/superpowers/specs/2026-08-22-ingredient-nutrition-engine-design.md`

## Global Constraints

- No code comments (repo rule). Match existing file style.
- Exact-decimal policies unchanged (`NUTRIENT_SCALE`, `quantize_decimal`, canonical serialization).
- Matching thresholds unchanged: ≥ 0.80 auto-match with runner-up margin, 0.65–0.80 propose band, < 0.65 unmatched.
- Status mapping (pantry): engine `matched` → `matched`; `ambiguous` → `proposed`; `unmatched` → `unmatched`; explicit selection → `manual` (confidence 1).
- Gates: `uv run --directory backend ruff format --check . && uv run --directory backend ruff check . && uv run --directory backend mypy src && uv run --directory backend pytest`.
- Known environmental notes from prior work: pgvector-dependent migration test needs the vchord extension (present in the compose postgres image).

---

### Task 1: Move matching core into the domain package

Pure relocation + import re-pointing. Zero behavior change.

**Files:**
- Create: `backend/src/cookfully/domain/ingredient_nutrition/__init__.py` (empty), `matching.py`, `normalization.py`
- Modify (delete after move): `backend/src/cookfully/application/food_matching.py`
- Modify importers: `backend/src/cookfully/jobs/recipe_pipeline.py`, `backend/src/cookfully/api/routes/foods.py`, `backend/src/cookfully/application/food_embedding_index.py`, `backend/src/cookfully/application/food_match_memories.py`, any other file found by grep, plus all test files importing `application.food_matching`
- Test: existing suites only (no assertion changes)

**Interfaces:**
- Produces: `cookfully.domain.ingredient_nutrition.matching` containing `FoodMatcher`, `MatchDecision`, `FoodCandidate`, `Compatibility`, `match_food_name`-replacement none (deleted in Task 3), plus module constants/aliases; `cookfully.domain.ingredient_nutrition.normalization` containing `normalize_food`, `_rank_query`, `_tokens`, `_singular`, `ALIASES`, `_semantic_query` helper, and the `profile_from_text`/`compare_compatibility` re-exports from `application/food_semantics` (that module stays put; matching.py imports from it).

- [ ] **Step 1: Create the package and split the module**

Create `domain/ingredient_nutrition/__init__.py` empty. Move from `application/food_matching.py`:

- Everything except the module docstring goes to `matching.py` **except** `ALIASES`, `normalize_food`, `_rank_query`, `_tokens`, `_singular`, which go to `normalization.py` (keep their exact implementations). `matching.py` imports them: `from cookfully.domain.ingredient_nutrition.normalization import ALIASES, normalize_food, normalize_tokens as _tokens` — do NOT rename privates across modules; instead have `normalization.py` expose public names `aliases`, `normalize`, `rank_query`, `tokenize`, `singularize` and keep private aliases inside `matching.py` (`_rank_query = rank_query` etc.) so the moved algorithm bodies stay byte-identical.
- Fix intra-package imports (`profile_from_text`, `compare_compatibility` remain imported from `cookfully.application.food_semantics` — allowed: domain may depend on other pure-domain/application-pure modules it already depended on; do not widen dependencies).

- [ ] **Step 2: Delete `application/food_matching.py` and re-point every importer**

Run `rg -l "application.food_matching|application/food_matching"` and replace each occurrence with the new module paths (`cookfully.domain.ingredient_nutrition.matching` / `.normalization`). Known importers: `jobs/recipe_pipeline.py`, `api/routes/foods.py`, `application/food_embedding_index.py`, `application/food_match_memories.py`, tests under `backend/tests/unit/test_food_matching_corpus.py`, `unit/test_ingredient_processing.py`, `unit/test_food_semantics.py`, others surfaced by grep.

- [ ] **Step 3: Run the backend gate**

Expected: all green with zero assertion edits. If a test imports a private symbol that moved, re-point it to `normalization` — do not duplicate the symbol back.

- [ ] **Step 4: Commit**

```bash
git add -A backend/
git commit -m "refactor: move food matching core into domain package"
```

---

### Task 2: `IngredientEngine` facade + single embedder factory

**Files:**
- Create: `backend/src/cookfully/application/ingredient_engine.py`
- Modify: `backend/src/cookfully/api/routes/foods.py` (delete `_configured_search_embedder`, `_search_embedder` globals; keep `warm_search_embedder` delegating to the engine), `backend/src/cookfully/jobs/recipe_pipeline.py` (delete `_embedder_for_session`)
- Test: `backend/tests/unit/test_ingredient_engine.py` (new)

**Interfaces:**
- Produces:

```python
class IngredientEngine:
    def matcher(self, session: Session, *, fallback: bool = True) -> FoodMatcher
    def resolve_embedder(self, session: Session, *, fallback: bool = True) -> TextEmbedder
    def match_ingredient(self, session: Session, name: str, *, preferred=None, fallback: bool = True) -> MatchDecision
    def search_foods(self, session: Session, query: str, *, limit: int = 10, fallback: bool = False) -> tuple[FoodCandidate, ...]

engine = IngredientEngine()  # module-level singleton, mirrors today's globals
```

- [ ] **Step 1: Write failing unit tests**

Create `backend/tests/unit/test_ingredient_engine.py`:

```python
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from cookfully.application.ingredient_engine import IngredientEngine
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings
from cookfully.infrastructure.semantic_embeddings import HashingTextEmbedder


@pytest.fixture()
def engine() -> IngredientEngine:
    return IngredientEngine()


def _seed(session, backend: str, ready: bool) -> None:
    row = session.get(NutritionIntelligenceSettings, 1)
    if row is None:
        row = NutritionIntelligenceSettings(id=1, backend=backend, concurrency=1, version=1)
        session.add(row)
    row.backend = backend
    row.last_ready_at = __import__("datetime").datetime.now() if ready else None
    session.commit()


def test_fastembed_ready_returns_neural(engine, session_factory: sessionmaker) -> None:
    with session_factory() as session:
        _seed(session, "fastembed", ready=True)
        with patch("cookfully.application.ingredient_engine.create_text_embedder") as factory:
            factory.return_value = object()
            result = engine.resolve_embedder(session)
        factory.assert_called_once()


def test_fastembed_not_ready_falls_back_when_best_effort(engine, session_factory: sessionmaker) -> None:
    with session_factory() as session:
        _seed(session, "fastembed", ready=False)
        embedder = engine.resolve_embedder(session, fallback=True)
        assert isinstance(embedder, HashingTextEmbedder)


def test_fastembed_not_ready_strict_raises_domain_error(engine, session_factory: sessionmaker) -> None:
    from cookfully.domain.errors import DomainError

    with session_factory() as session:
        _seed(session, "fastembed", ready=False)
        with pytest.raises(DomainError) as excinfo:
            engine.resolve_embedder(session, fallback=False)
        assert excinfo.value.code == "embedding_model_not_ready"


def test_settings_change_invalidates_cache(engine, session_factory: sessionmaker) -> None:
    with session_factory() as session:
        _seed(session, "hashing", ready=True)
        first = engine.resolve_embedder(session)
        _seed(session, "fastembed", ready=False)
        second = engine.resolve_embedder(session)
        assert first is not second


def test_stale_hashing_retries_neural_after_interval(engine, session_factory: sessionmaker) -> None:
    import time

    with session_factory() as session:
        _seed(session, "fastembed", ready=True)
        engine.resolve_embedder(session, fallback=True)
        engine._checked_at = time.monotonic() - 31
        with patch("cookfully.application.ingredient_engine.create_text_embedder") as factory:
            factory.side_effect = RuntimeError("model missing")
            retried = engine.resolve_embedder(session, fallback=True)
        factory.assert_called_once()
        assert isinstance(retried, HashingTextEmbedder)
```

Adjust fixture plumbing (`session_factory`, `DomainError` import path) to match how sibling unit tests obtain sessions — read `backend/tests/unit/test_nutrition_intelligence.py` first and mirror it exactly.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --directory backend pytest tests/unit/test_ingredient_engine.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the facade**

Create `backend/src/cookfully/application/ingredient_engine.py`:

```python
import time

from sqlalchemy.orm import Session

from cookfully.domain.errors import DomainError
from cookfully.domain.ingredient_nutrition.matching import (
    FoodCandidate,
    FoodMatcher,
    MatchDecision,
)
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.models.nutrition_intelligence import (
    NutritionIntelligenceSettings,
)
from cookfully.infrastructure.nutrition_repository import NutritionRepository
from cookfully.infrastructure.semantic_embeddings import (
    HashingTextEmbedder,
    TextEmbedder,
    create_text_embedder,
)

_RETRY_INTERVAL_SECONDS = 30
_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class IngredientEngine:
    def __init__(self) -> None:
        self._embedder: TextEmbedder | None = None
        self._embedder_key: tuple[str, str, str | None, bool] | None = None
        self._checked_at: float = 0.0

    def resolve_embedder(self, session: Session, *, fallback: bool = True) -> TextEmbedder:
        settings = session.get(NutritionIntelligenceSettings, 1)
        backend = settings.backend if settings is not None else "fastembed"
        model_name = settings.model_name if settings is not None else _DEFAULT_MODEL
        revision = settings.model_revision if settings is not None else None
        ready = bool(settings and settings.last_ready_at)
        key = (backend, model_name, revision, ready)
        stale_hashing = (
            backend == "fastembed"
            and isinstance(self._embedder, HashingTextEmbedder)
            and time.monotonic() - self._checked_at >= _RETRY_INTERVAL_SECONDS
        )
        if self._embedder is None or self._embedder_key != key or stale_hashing:
            runtime = get_settings()
            if backend == "fastembed":
                if not fallback and settings is not None and settings.last_ready_at is None:
                    raise DomainError(
                        "embedding_model_not_ready",
                        "The selected embedding model is still downloading.",
                        409,
                    )
                try:
                    self._embedder = create_text_embedder(
                        model_name=model_name,
                        cache_dir=runtime.semantic_matching_model_dir,
                        local_files_only=True,
                        allow_fallback=fallback,
                    )
                except Exception:
                    if not fallback:
                        raise DomainError(
                            "embedding_model_unavailable",
                            "The selected embedding model is not available locally. Save the model settings to retry its download.",
                            503,
                        )
                    self._embedder = HashingTextEmbedder()
            else:
                self._embedder = HashingTextEmbedder(dimensions=384)
            self._embedder_key = key
            self._checked_at = time.monotonic()
        return self._embedder

    def matcher(self, session: Session, *, fallback: bool = True) -> FoodMatcher:
        return FoodMatcher(
            NutritionRepository(session),
            embedder=self.resolve_embedder(session, fallback=fallback),
        )

    def match_ingredient(
        self,
        session: Session,
        name: str,
        *,
        preferred=None,
        fallback: bool = True,
    ) -> MatchDecision:
        return self.matcher(session, fallback=fallback).decide(name, preferred_food=preferred)

    def search_foods(
        self,
        session: Session,
        query: str,
        *,
        limit: int = 10,
        fallback: bool = False,
    ) -> tuple[FoodCandidate, ...]:
        return self.matcher(session, fallback=fallback).candidates(query, limit=limit)


engine = IngredientEngine()
```

Verify against reality while implementing: `NutritionRepository` import path, `DomainError` location, whether `create_text_embedder`'s `allow_fallback` alone covers the strict 409-vs-503 distinction (the explicit pre-check preserves today's messages), and the candidate-pool-limit parameter that `foods.py` passes (`_SEARCH_CANDIDATE_POOL_LIMIT`) — if needed add an optional `candidate_pool_limit` argument to `matcher()` and thread it through both call sites so no behavior is lost.

- [ ] **Step 4: Run engine tests**

Run: `uv run --directory backend pytest tests/unit/test_ingredient_engine.py -v`
Expected: PASS. Fix implementation, never weaken assertions.

- [ ] **Step 5: Re-point consumers and delete duplicates**

- `api/routes/foods.py`: delete `_configured_search_embedder` and its module globals; `_configured_search_matcher` becomes `engine.matcher(session, fallback=False)` (preserving pool limit); `warm_search_embedder` calls `engine.resolve_embedder(session, fallback=False)` guarded the same way it is today.
- `jobs/recipe_pipeline.py`: replace `self._embedder_for_session(session)` with `engine.resolve_embedder(session, fallback=True)`; keep the injected-test-embedder escape hatch (`self._embedder is not None and self._embedder_key is None`) by short-circuiting before the engine call; delete `_embedder_for_session`.
- Grep `rg -n "_configured_search_embedder|_embedder_for_session"` → zero hits outside history.

- [ ] **Step 6: Backend gate**

All four commands green. Existing foods/pipeline tests must pass unchanged; if they monkeypatched the old private functions, re-point patches to the engine module.

- [ ] **Step 7: Commit**

```bash
git add -A backend/
git commit -m "feat: unify nutrition matching behind IngredientEngine facade"
```

---

### Task 3: Pantry on the engine + neural default migration

**Files:**
- Modify: `backend/src/cookfully/application/pantry.py` (`_resolve_match`, delete `match_food_name` + `FoodNameMatch`), wherever `PantryService` is constructed (`app.state.pantry`) — no constructor change needed since `engine` is a module singleton
- Create: `backend/migrations/versions/0027_default_neural_matching.py` (header conventions copied from 0026)
- Test updates: `backend/tests/unit/test_pantry.py`, `contract/test_pantry_api.py`, any fixture asserting `SequenceMatcher` confidences

**Interfaces:**
- Pantry `_resolve_match` returns the same tuple shape `(reference_id | None, status, confidence | None)` with statuses mapped from `MatchDecision.status` per Global Constraints.

- [ ] **Step 1: Update pantry tests first**

In `backend/tests/unit/test_pantry.py`, update/extend cases covering: proposed-band item yields status `proposed` with the candidate score as confidence; strong match yields `matched`; no candidate yields `unmatched` with `None`; manual reference id yields `manual` with `Decimal("1.000000")`. Mirror the matcher fixtures used by `test_food_matching_corpus.py` (seed minimal FoodReference rows) rather than mocking internals. Expected: FAIL (old SequenceMatcher confidences differ).

- [ ] **Step 2: Implement**

Replace `_resolve_match` body:

```python
    @staticmethod
    def _resolve_match(
        session: Session,
        display_name: str,
        requested_reference_id: UUID | None,
    ) -> tuple[UUID | None, str, Decimal | None]:
        if requested_reference_id is not None:
            if session.get(FoodReference, requested_reference_id) is None:
                raise DomainError("food_reference_not_found", "Food reference was not found.", 404)
            return requested_reference_id, "manual", Decimal("1.000000")
        decision = engine.match_ingredient(session, display_name)
        candidate = decision.candidate
        status_map = {"matched": "matched", "ambiguous": "proposed", "unmatched": "unmatched"}
        reference_id = UUID(str(candidate.food.id)) if candidate is not None else None
        return (
            reference_id,
            status_map.get(decision.status, "unmatched"),
            candidate.score if candidate is not None else None,
        )
```

Delete `match_food_name` and `FoodNameMatch`; remove now-unused imports (`difflib` usage, `SequenceMatcher`). Confirm `FoodMatcher.decide`'s literal status strings while implementing and align `status_map` keys with them (assert via a unit test on the mapping itself if they differ from `matched/ambiguous/unmatched`).

- [ ] **Step 3: Migration 0027**

Create `backend/migrations/versions/0027_default_neural_matching.py` (copy header/import conventions from 0026):

```python
def upgrade() -> None:
    op.alter_column(
        "nutrition_intelligence_settings",
        "backend",
        existing_type=sa.String(16),
        server_default=sa.text("'fastembed'"),
    )
    op.alter_column(
        "nutrition_intelligence_settings",
        "model_name",
        existing_type=sa.String(120),
        server_default=sa.text("'BAAI/bge-small-en-v1.5'"),
    )
    op.execute(
        "UPDATE nutrition_intelligence_settings "
        "SET backend = 'fastembed', model_name = 'BAAI/bge-small-en-v1.5' "
        "WHERE backend = 'hashing'"
    )


def downgrade() -> None:
    op.alter_column(
        "nutrition_intelligence_settings",
        "backend",
        existing_type=sa.String(16),
        server_default=sa.text("'hashing'"),
    )
```

Check the actual `String` lengths and column names in `infrastructure/models/nutrition_intelligence.py` and use those values. If the settings row is bootstrapped anywhere in code (grep `NutritionIntelligenceSettings(` for creations), set its defaults to fastembed/model too.

- [ ] **Step 4: Gate + commit**

Backend gate green including updated pantry tests.

```bash
git add -A backend/
git commit -m "feat: pantry matches through IngredientEngine with neural default"
```

---

### Task 4: Boundary enforcement + docs

**Files:**
- Create: `backend/tests/unit/test_ingredient_engine_boundary.py`
- Modify: `docs/inspiration-review.md` (short entry: scattered matching logic problem, adopted single-facade domain-module pattern, why not a deployed microservice)

- [ ] **Step 1: Write the architecture test**

```python
import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "src" / "cookfully"
_PATTERN = re.compile(r"^\s*(from|import)\s+cookfully\.domain\.ingredient_nutrition", re.MULTILINE)


def test_only_the_engine_imports_the_domain_package() -> None:
    violations = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(PACKAGE_ROOT)
        inside_domain = relative.parts[:1] == ("domain",) and "ingredient_nutrition" in relative.parts
        is_facade = str(relative).replace("\\", "/") == "application/ingredient_engine.py"
        if inside_domain or is_facade:
            continue
        if _PATTERN.search(path.read_text(encoding="utf-8")):
            violations.append(str(relative))
    assert violations == []
```

- [ ] **Step 2: Run gate**

Full backend gate green (the boundary test must pass because Task 1 re-pointed everything).

- [ ] **Step 3: Docs entry + commit**

Append the inspiration-review entry per repo format, then:

```bash
git add -A backend/ docs/inspiration-review.md
git commit -m "test: enforce ingredient engine import boundary and record review"
```

---

## Post-P1 (separate plans, not in this document)

- P2 normalization consolidation, P3 quantities, P4 computation per the spec.
- Docker smoke: rebuild api/worker, add a pantry item, verify Review-match chip shows shared-scorer confidence.
