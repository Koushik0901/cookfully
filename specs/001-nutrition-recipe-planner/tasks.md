---
description: "Dependency-ordered implementation tasks for Vigor & Vine"
---

# Tasks: Gym-Focused Recipe & Nutrition Planner

**Input**: Design documents from `/specs/001-nutrition-recipe-planner/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`  
**Tests**: Required for nutrition, totals, grocery aggregation, contracts, jobs, external boundaries,
and critical user journeys by the constitution and plan. Tests are written first and observed failing
before their corresponding implementation tasks begin.  
**Release boundaries**: US1 is the MVP; US1-US3 are the core release; US4-US6 are ordered expansion.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel after its stated phase prerequisites because it uses different files
  and does not depend on another incomplete task in the same group.
- **[Story]**: Maps the task to US1-US6 from `spec.md`.
- Every task names the exact primary file or directory it creates or changes.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Close requirement-writing gaps, establish the monorepo, lock dependencies, and make all
later work reproducible.

- [X] T001 Validate every item in `specs/001-nutrition-recipe-planner/checklists/nutrition.md` against the clarified spec, model, and contracts; link evidence for resolved items, and stop to rerun clarify/plan/tasks/analyze before T002 if any answer changes a requirement
- [X] T002 Scaffold the Python 3.13 project, `uv.lock`, and package entry points in `backend/pyproject.toml` and `backend/src/vigor_vine/__init__.py`
- [X] T003 [P] Scaffold the React 19.2 TypeScript client and lockfile in `frontend/package.json`, `frontend/pnpm-lock.yaml`, and `frontend/src/main.tsx`
- [X] T004 Create the planned backend package, test, migration, frontend feature, deployment, script, and documentation directories listed in `specs/001-nutrition-recipe-planner/plan.md`
- [X] T005 [P] Configure Ruff, mypy, pytest, pytest-asyncio, Hypothesis, and coverage defaults in `backend/pyproject.toml`
- [X] T006 [P] Configure ESLint, TypeScript, Vitest, Testing Library, axe-core, and Playwright in `frontend/eslint.config.js`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, and `frontend/playwright.config.ts`
- [X] T007 [P] Translate `DESIGN.md` colors, typography, spacing, radii, and macro-status semantics into `frontend/src/styles/tokens.css` and `frontend/src/styles/globals.css`
- [X] T008 Define validated environment variables, disabled-by-default failed-import diagnostics, retention deadlines, retry schedule, and safe local defaults in `.env.example` and `backend/src/vigor_vine/infrastructure/config.py`
- [X] T009 [P] Define healthy PostgreSQL 18 and Redis development services with named volumes in `deploy/compose.yaml`
- [X] T010 [P] Add locked backend lint, type, unit, and integration jobs in `.github/workflows/backend.yml`
- [X] T011 [P] Add frontend lint, type, unit, build, accessibility, and Playwright jobs in `.github/workflows/frontend.yml`
- [X] T012 Record every adopted dependency, pinned major version, source, and license decision in `docs/dependencies-and-licenses.md`
- [X] T013 Create cross-platform aggregate verification commands in `scripts/verify.ps1` and `scripts/verify.sh`

**Checkpoint**: Dependencies lock successfully, repository checks can run, and requirement ambiguities
that would change implementation are resolved.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement shared domain primitives, persistence, authentication, errors, durable work,
and the application shell required by every story.

**⚠️ CRITICAL**: No user-story implementation begins until this phase passes its tests.

- [X] T014 Create UUIDv7, UTC/local-date, `numeric(20,6)` nutrient/quantity, `numeric(12,3)` serving, canonical decimal-string, round-half-up, optimistic-version, and domain-error primitives in `backend/src/vigor_vine/domain/common.py`
- [X] T015 Implement SQLAlchemy engine/session factories and the transaction-scoped unit-of-work port in `backend/src/vigor_vine/infrastructure/database.py` and `backend/src/vigor_vine/application/unit_of_work.py`
- [X] T016 Initialize Alembic metadata, naming conventions, and PostgreSQL extension setup in `backend/alembic.ini`, `backend/migrations/env.py`, and `backend/migrations/versions/0001_foundation.py`
- [X] T017 Create owner timezone/week-start preferences, session, hashed access-token, and encrypted expiring media-asset persistence models in `backend/src/vigor_vine/infrastructure/models/identity.py` and `backend/src/vigor_vine/infrastructure/models/media.py`
- [X] T018 [P] Write failing authentication, CSRF, session-expiry, token-hash/scope, owner timezone/week-start, and once-only-token tests in `backend/tests/integration/test_auth.py`
- [X] T019 Implement Argon2id owner bootstrap, revocable sessions, CSRF enforcement, scoped token services, and owner preference commands in `backend/src/vigor_vine/application/auth.py` and `backend/src/vigor_vine/application/owner_preferences.py`
- [X] T020 Implement login/logout and owner preference routes plus hashed scoped-bearer authentication middleware in `backend/src/vigor_vine/api/routes/auth.py`, `backend/src/vigor_vine/api/routes/owner.py`, and `backend/src/vigor_vine/api/dependencies/auth.py`
- [X] T021 [P] Define RFC 9457-style safe problem responses and field-error mapping in `backend/src/vigor_vine/api/problems.py`
- [X] T022 [P] Add request/job correlation IDs, raw-provider and personal-data redaction, retention-safe logging, and health metrics in `backend/src/vigor_vine/infrastructure/observability.py`
- [X] T023 [P] Implement content-addressed media storage, encryption and 24-hour expiry for owner-enabled failed-import diagnostics, allowlisted content types, and path traversal guards in `backend/src/vigor_vine/infrastructure/media_store.py`; implement the independent content-free hash-chained erasure ledger, continuity verification, and rotation-plus-30-day retention in `backend/src/vigor_vine/infrastructure/erasure_ledger.py`
- [X] T024 Create ProcessingJob fields for accepted/next-retry/terminal-deadline/diagnostic-retention timestamps plus OutboxEvent models and indexes in `backend/src/vigor_vine/infrastructure/models/jobs.py` and `backend/migrations/versions/0002_jobs_outbox.py`
- [X] T025 [P] Write failing job transition, duplicate-delivery, stale-input, 60-second timeout, fixed 5s/30s/2m/5m retry, five-attempt, 15-minute deadline, retention, and outbox recovery tests in `backend/tests/integration/test_job_lifecycle.py`
- [X] T026 Implement the authoritative job repository, fixed retry/terminal policy, progress DTO, and retention-reduction policy in `backend/src/vigor_vine/application/jobs.py`
- [X] T027 [P] Configure the Celery 5.6 app with 60-second task limits, Redis broker options, task redaction, and worker health signal in `backend/src/vigor_vine/jobs/app.py`
- [X] T028 Implement transactional outbox dispatch, the fixed clarified retry schedule, heartbeat/deadline reconciliation, stalled-job recovery, and 24h/30d/1y retention sweeps in `backend/src/vigor_vine/jobs/outbox.py`, `backend/src/vigor_vine/jobs/reconciler.py`, and `backend/src/vigor_vine/jobs/retention.py`
- [X] T029 Add one-second acceptance, worker-death, broker-outage, retry/deadline, reload polling, and retention contract coverage from `contracts/background-jobs.md` in `backend/tests/contract/test_background_job_contract.py`
- [X] T030 Assemble FastAPI lifespan, authentication, problem middleware, health route, and versioned router in `backend/src/vigor_vine/api/main.py`
- [X] T031 Configure OpenAPI 3.1 compatibility checks for API v0.2.0, canonical decimal-string TypeScript adapters, and committed-client generation in `scripts/generate-api-client.ps1` and `frontend/src/app/api/generated/`
- [X] T032 [P] Create the React router, authentication boundary, TanStack Query provider, and global error boundary in `frontend/src/app/App.tsx` and `frontend/src/app/providers.tsx`
- [X] T033 [P] Create accessible shared controls for exact-decimal inputs, buttons, fields, destructive confirmations, dialogs, polling status badges, skeletons, empty states, and error recovery in `frontend/src/components/`
- [X] T034 Build API, worker, outbox, and web images and complete service health/dependency wiring in `deploy/docker/` and `deploy/compose.yaml`

**Checkpoint**: Authentication, errors, health, media storage, job/outbox redelivery, containers, and
the frontend shell work independently of recipe features.

---

## Phase 3: User Story 1 — Capture Recipes With Actionable Nutrition (Priority: P1) 🎯 MVP

**Goal**: Create or import a recipe, preserve source text, produce exact and honest per-serving
calories/macros, show provenance and bounded job states, retain corrections through reprocessing, and
support reversible archive plus history-safe permanent deletion.

**Independent Test**: Create a manual recipe and import a representative public recipe with an
under-one-second acknowledgement; observe polling/reload and bounded retry states; correct and rerun;
then archive, restore, and permanently delete while proving exact decimal results, retained corrections,
recoverable failures, removed recipe-owned data, and unchanged detached history.

### Tests for User Story 1

- [X] T035 [P] [US1] Write failing Recipe/Ingredient state, archive-from-state, restore-to-stale, confirmed permanent deletion, detached-history, and stale-input domain tests in `backend/tests/unit/test_recipe_domain.py`
- [X] T036 [P] [US1] Write failing ingredient range, optional line, unit/density/count-weight, unmatched-food, and lower-of-mass/count coverage tests in `backend/tests/unit/test_ingredient_processing.py`
- [X] T037 [P] [US1] Write failing six-decimal nutrient/quantity, positive three-decimal serving with zero rejection, canonical-string, round-half-up, null/zero, coverage, and correction-precedence tests in `backend/tests/unit/test_nutrition_calculation.py`
- [X] T038 [P] [US1] Write failing OpenAPI 3.1 API v0.2.0 recipe CRUD/import/archive/restore/permanent-delete/job/recalculate/correction/concurrency, positive-serving, and decimal-string contract tests in `backend/tests/contract/test_recipe_api.py`
- [X] T039 [P] [US1] Write failing duplicate-delivery, input/correction/archive change during jobs, one-second acceptance, fixed retries/deadline, diagnostic expiry, and partial-chain integration tests in `backend/tests/integration/test_recipe_jobs.py`
- [ ] T040 [P] [US1] Create SC-001/SC-002/SC-003 runners for all 50 captured public-page cases and the stable 30-recipe constitutional subset, enforcing 20% calorie and 25% protein/carbohydrate/fat median-error gates plus nutrient-specific near-zero reporting in `backend/tests/accuracy/test_nutrition_corpus.py`
- [ ] T041 [P] [US1] Write failing accessible recipe card/editor, two-second polling, reload recovery, retry timing, provenance, correction, archive/restore, and deletion-confirmation tests in `frontend/src/features/recipes/__tests__/`
- [ ] T042 [P] [US1] Write failing manual-create, URL-import, correction, bounded retry, reload, stale-yield, archive/restore, and permanent-delete-with-history journeys in `frontend/e2e/recipes.spec.ts`

### Implementation for User Story 1

- [ ] T043 [US1] Create Recipe archived-from-state, RecipeInstruction, six-decimal Ingredient, the recipe-to-foundational-MediaAsset association, and detached-history constraints in `backend/src/vigor_vine/infrastructure/models/recipes.py` and `backend/migrations/versions/0003_recipes.py`
- [X] T044 [US1] Create ReferenceDataset, FoodReference, and FoodNutrient tables plus search indexes in `backend/src/vigor_vine/infrastructure/models/reference_foods.py` and `backend/migrations/versions/0004_reference_foods.py`
- [X] T045 [US1] Create fixed-scale IngredientMatch, NutritionEstimate, and typed NutritionCorrection tables with canonical precision and active-record constraints in `backend/src/vigor_vine/infrastructure/models/nutrition.py` and `backend/migrations/versions/0005_nutrition.py`
- [X] T046 [US1] Implement recipe, reference-food, match, estimate, and correction repositories in `backend/src/vigor_vine/infrastructure/repositories/recipes.py` and `backend/src/vigor_vine/infrastructure/repositories/nutrition.py`
- [X] T047 [P] [US1] Implement the memory-only HTTP/HTTPS fetcher with DNS/redirect revalidation, private-address blocking, byte/time limits, content-type checks, and no successful-HTML persistence in `backend/src/vigor_vine/infrastructure/safe_fetch.py`
- [X] T048 [P] [US1] Implement the `recipe-scrapers` HTML adapter, source nutrition extraction, immediate buffer disposal, and opt-in encrypted failed-import diagnostic handoff in `backend/src/vigor_vine/infrastructure/recipe_importer.py`
- [X] T049 [P] [US1] Implement remote recipe-image validation, hashing, transformation limits, and media persistence in `backend/src/vigor_vine/infrastructure/recipe_images.py`
- [X] T050 [P] [US1] Implement deterministic `ingredient-parser-nlp` mapping to six-decimal quantities while preserving original text, confidence, parser name, and parser version in `backend/src/vigor_vine/infrastructure/ingredient_parser.py`
- [X] T051 [P] [US1] Implement six-decimal canonical units, ranges, Pint conversions, count weights, explicit density assumptions, and unsafe-conversion rejection in `backend/src/vigor_vine/domain/units.py`
- [X] T052 [P] [US1] Implement idempotent required Foundation Foods and SR Legacy bulk import, explicit release activation, release/date/license attribution, 90-day review status, no-dataset degraded-state reporting, and stale-on-explicit-reprocess behavior in `backend/src/vigor_vine/cli/reference_data.py`; prove import/activation idempotence, attribution, review status, release switching, and degraded operation in `backend/tests/integration/test_reference_data.py`
- [X] T053 [US1] Implement normalized alias search, deterministic candidate ranking, ambiguity thresholds, manual matches, release provenance, and lower-of-mass/count coverage inputs in `backend/src/vigor_vine/application/food_matching.py`
- [X] T054 [P] [US1] Define disabled-by-default structured AI ports with schema validation, data minimization, raw-request/response non-retention, safe hashes/errors, and cache keys in `backend/src/vigor_vine/application/ai_provider.py`
- [X] T055 [US1] Implement exact ingredient contribution, lower-of-mass/count coverage, six-decimal rollup, three-decimal serving normalization, provenance, and immutable estimate creation in `backend/src/vigor_vine/domain/nutrition.py`
- [X] T056 [US1] Implement fixed-scale typed correction activation/reset and resolved-value precedence across parse, match, conversion, yield, and nutrient fields in `backend/src/vigor_vine/application/corrections.py`
- [ ] T057 [US1] Implement create/update/archive/restore/confirmed-permanent-delete commands, active-job supersession, detached-history retention, stale-state detection, and current-input hashing in `backend/src/vigor_vine/application/recipes.py`
- [X] T058 [US1] Implement the import → parse → match → rollup chain with one-second acceptance, 60-second attempts, fixed retry/deadline enforcement, terminal partial/failed mapping, retention hooks, and idempotent activation in `backend/src/vigor_vine/jobs/recipe_pipeline.py`
- [X] T059 [US1] Implement OpenAPI 3.1 API v0.2.0 recipe/archive/restore/permanent-delete/import/recalculate/correction routes and canonical decimal-string DTOs in `backend/src/vigor_vine/api/routes/recipes.py` and `backend/src/vigor_vine/api/schemas/recipes.py`
- [X] T060 [US1] Implement authoritative polling DTOs with progress, next retry, terminal deadline, safe failure/recovery actions, and reload discovery in `backend/src/vigor_vine/api/routes/jobs.py`
- [ ] T061 [US1] Regenerate and commit OpenAPI 3.1 API v0.2.0 recipe/job TypeScript bindings and exact-decimal adapters in `frontend/src/app/api/generated/`
- [ ] T062 [US1] Assemble and version the approved 50 captured public-page HTML/reference cases with 15 simple/20 moderate/15 complex cases, a stable 30-recipe primary subset, source-site stratification, expected import fields, classifications, and accuracy reports in `backend/tests/fixtures/nutrition-corpus/` and `backend/src/vigor_vine/cli/nutrition_report.py`; run T040 and block T063-T065 plus all later stories until the stable 30-recipe subset passes SC-001/SC-002
- [ ] T063 [P] [US1] After the T062 constitutional gate passes, implement the searchable recipe library, nutrition-state filters, archive/restore view, and responsive RecipeCard with exact decimal display in `frontend/src/features/recipes/RecipeLibraryPage.tsx` and `frontend/src/features/recipes/RecipeCard.tsx`
- [ ] T064 [P] [US1] After the T062 constitutional gate passes, implement exact-decimal recipe editing, original/structured ingredient review, URL import, validation, two-second polling, 15-second background polling, and pending-job feedback in `frontend/src/features/recipes/RecipeEditorPage.tsx` and `frontend/src/features/recipes/RecipeImportDialog.tsx`
- [ ] T065 [US1] After the T062 constitutional gate passes, implement provenance/assumption disclosure, accessible planning-aid-not-medical-advice language, progress/retry/deadline states, reload recovery, correction/reset, stale-yield, archive/restore, and permanent-delete confirmation in `frontend/src/features/recipes/RecipeDetailPage.tsx` and `frontend/src/features/recipes/NutritionPanel.tsx`
- [ ] T066 [US1] Document reference eligibility, 20% calorie and 25% protein/carbohydrate/fat thresholds, nutrient-specific near-zero floors and absolute-error reporting, lower-of-mass/count coverage, exact decimal/rounding, correction precedence, 30+20 corpus metrics, and limitations in `docs/nutrition-methodology.md`

**Checkpoint**: US1 passes SC-001 through SC-004 plus SC-013/SC-014 and the 50-recipe P1 accuracy/import
gate. Major UI polish and later stories remain blocked if thresholds fail without a classified plan.

---

## Phase 4: User Story 2 — Plan a Week Against Personal Targets (Priority: P2)

**Goal**: Define personal daily/per-meal targets, place recipe servings into dated slots, preserve
nutrition snapshots, and compare meal/day/week totals with goals.

**Independent Test**: With seeded exact-decimal recipes, configure timezone/week start, create a goal,
fill seven days, move/copy/resize entries across a daylight-saving boundary, and prove displayed entries
sum exactly to meal/day/week totals while detached history changes only after explicit refresh.

### Tests for User Story 2

- [ ] T067 [P] [US2] Write failing required non-null daily calorie/protein/carbohydrate/fat goal validation, effective-date overlap, macro-calorie difference, nullable meal-target, owner timezone/week-start, and daylight-saving boundary tests in `backend/tests/unit/test_goals.py`
- [ ] T068 [P] [US2] Write failing three-decimal serving, round-half-up display snapshot, exact decimal-string meal/day/week totals, signed differences, reliability, and explicit-refresh tests in `backend/tests/unit/test_meal_plan_totals.py`
- [ ] T069 [P] [US2] Write failing owner-preference, required non-null daily-goal, optional meal-target, and meal-plan CRUD/concurrency plus canonical decimal-string contract tests in `backend/tests/contract/test_meal_plan_api.py`
- [ ] T070 [P] [US2] Write failing recipe-edit/delete-versus-detached-history, display-quantized snapshot, and 50-entry performance integration tests in `backend/tests/integration/test_meal_plan_snapshots.py`
- [ ] T071 [P] [US2] Write failing target form, week calendar, day tabs, budget bars, status cues, and keyboard interaction tests in `frontend/src/features/plans/__tests__/`
- [ ] T072 [P] [US2] Write failing goal creation, seven-day planning, serving adjustment, copy/move, and snapshot-refresh journeys in `frontend/e2e/meal-planning.spec.ts`

### Implementation for User Story 2

- [ ] T073 [US2] Create fixed-scale UserGoal, MealTarget, MealPlan, three-decimal MealPlanEntry, display-quantized MealNutritionSnapshot tables, detached recipe links, and non-overlap constraints in `backend/src/vigor_vine/infrastructure/models/plans.py` and `backend/migrations/versions/0006_goals_plans.py`
- [ ] T074 [P] [US2] Implement goal effective-date, owner timezone/week-start, target/tolerance, and exact macro-derived-calorie policies in `backend/src/vigor_vine/domain/goals.py`
- [ ] T075 [P] [US2] Implement immutable whole-kcal/0.1g round-half-up snapshots, three-decimal servings, explicit refresh, detached recipe provenance, and least-reliable propagation in `backend/src/vigor_vine/domain/meal_snapshots.py`
- [ ] T076 [US2] Implement canonical decimal-string meal/day/week aggregation and signed target differences by summing display-quantized entries in `backend/src/vigor_vine/domain/plan_totals.py`
- [ ] T077 [US2] Implement goal and plan repositories plus add/move/copy/resize/remove commands with optimistic concurrency in `backend/src/vigor_vine/application/meal_plans.py`
- [ ] T078 [US2] Implement owner preference, current-goal, and weekly meal-plan routes/DTOs with canonical decimal strings matching `contracts/openapi.yaml` in `backend/src/vigor_vine/api/routes/goals.py`, `backend/src/vigor_vine/api/routes/meal_plans.py`, and `backend/src/vigor_vine/api/schemas/plans.py`
- [ ] T079 [US2] Regenerate and commit exact-decimal goal/plan/owner-preference TypeScript bindings in `frontend/src/app/api/generated/`
- [ ] T080 [P] [US2] Implement maintenance/target mode, daily macros, effective dates, optional meal targets, timezone, and week-start editing in `frontend/src/features/goals/GoalSettingsPage.tsx`
- [ ] T081 [P] [US2] Implement timezone/week-start-aware responsive week/day navigation, meal slots, recipe selection, and entry ordering in `frontend/src/features/plans/WeeklyPlannerPage.tsx` and `frontend/src/features/plans/DayTabs.tsx`
- [ ] T082 [P] [US2] Implement accessible exact-decimal macro rings, budget bars, numeric typography, reliability badges, and non-color state labels in `frontend/src/features/plans/MacroSummary.tsx`
- [ ] T083 [US2] Implement add/move/copy/resize/remove and explicit nutrition-refresh interactions with optimistic-conflict recovery in `frontend/src/features/plans/MealPlanEntry.tsx` and `frontend/src/features/plans/useMealPlanMutations.ts`
- [ ] T084 [US2] Add 50-entry exact-sum reference fixtures and automated p95/under-two-second visible-update reporting in `backend/tests/performance/test_plan_totals.py` and `frontend/e2e/meal-plan-performance.spec.ts`

**Checkpoint**: US1 and US2 work together, while US2 remains independently testable with seeded
recipe snapshots.

---

## Phase 5: User Story 3 — Turn the Plan Into a Grocery List (Priority: P3)

**Goal**: Generate a traceable grocery list from planned servings, safely aggregate compatible
ingredients, preserve manual/check state through regeneration, and support backup/export.

**Independent Test**: Generate a list from exact-decimal compatible/incompatible fixtures, create/edit/
delete/check manual items, regenerate after serving changes, permanently delete a source recipe, and
compare reconciled/exported/restored detached history plus post-backup erasure with expected results.

### Tests for User Story 3

- [ ] T085 [P] [US3] Write failing six-decimal property tests for serving scaling, normalized identities, compatible-unit aggregation, unsafe separation, and source contributions in `backend/tests/unit/test_grocery_aggregation.py`
- [ ] T086 [P] [US3] Write failing reconciliation tests for checked items, manual names/quantities, removed sources, stable ordering, and review flags in `backend/tests/unit/test_grocery_reconciliation.py`
- [ ] T087 [P] [US3] Write failing grocery generation/regeneration, manual item create requiring a non-empty display name, partial update/delete, decimal-string, concurrency, and problem-response contract tests in `backend/tests/contract/test_grocery_api.py`
- [ ] T088 [P] [US3] Write failing portable manifest, six/three/display-decimal NDJSON, erased-recipe omission/detached-history, archive traversal, checksum, staging, and merge-policy tests in `backend/tests/contract/test_export_format.py`
- [ ] T089 [P] [US3] Write failing full backup/restore entity, correction, snapshot, manual-state, media-checksum, retention exclusion, ledger cursor/hash continuity, post-backup erasure replay, zero-resurrection, and missing/discontinuous-ledger fail-closed tests in `backend/tests/integration/test_backup_restore.py`
- [ ] T090 [P] [US3] Write failing grocery traceability, edit/check, dirty-state, regeneration, and mobile shopping journeys in `frontend/e2e/grocery-list.spec.ts`

### Implementation for User Story 3

- [ ] T091 [US3] Create GroceryList, six-decimal GroceryItem, detached GroceryItemSource tables, origin/lifecycle fields, and version/index constraints in `backend/src/vigor_vine/infrastructure/models/grocery.py` and `backend/migrations/versions/0007_grocery.py`
- [ ] T092 [US3] Implement six-decimal ingredient scaling, canonical aggregation keys, dimensional compatibility, and detached source-contribution calculation in `backend/src/vigor_vine/domain/grocery.py`
- [ ] T093 [US3] Implement proposed-list reconciliation that preserves manual/check state and marks material conflicts for review in `backend/src/vigor_vine/application/grocery_reconciliation.py`
- [ ] T094 [US3] Implement grocery list generation, dirty-state tracking, regeneration, and item-edit commands in `backend/src/vigor_vine/application/grocery_lists.py`
- [ ] T095 [US3] Implement grocery generation plus manual item create/update/delete routes and canonical decimal-string DTOs matching `contracts/openapi.yaml` in `backend/src/vigor_vine/api/routes/grocery.py` and `backend/src/vigor_vine/api/schemas/grocery.py`
- [ ] T096 [US3] Regenerate and commit exact-decimal grocery TypeScript bindings in `frontend/src/app/api/generated/`
- [ ] T097 [US3] Implement grouped shopping view, source disclosure, check/edit/add/remove controls, dirty/regenerating states, and narrow-mobile layout in `frontend/src/features/grocery/GroceryListPage.tsx`
- [ ] T098 [P] [US3] Implement versioned exact-decimal ZIP/NDJSON export, erased-recipe exclusion, detached-history retention, safe media inclusion, checksums, and export jobs in `backend/src/vigor_vine/application/exports.py` and `backend/src/vigor_vine/jobs/export.py`
- [ ] T099 [P] [US3] Implement consistent PostgreSQL/media backup create/verify/staged restore/compare with manifest ledger cursor/hash, independent-ledger continuity validation, idempotent post-backup erasure replay, activation gate, and replay reporting in `backend/src/vigor_vine/cli/backup.py`
- [ ] T100 [US3] Implement export job creation/status API and secure one-time archive download in `backend/src/vigor_vine/api/routes/exports.py`
- [ ] T101 [US3] Document Docker volumes, independent erasure-ledger replication and protection, scheduled backup rotation, ledger rotation-plus-30-day retention, fail-closed replay-gated staged restore, portable exports, and disaster-recovery validation in `docs/backup-restore.md`

**Checkpoint**: P1-P3 form the core release and pass SC-001 through SC-008, SC-011, and applicable
SC-012 checks before any expansion release is enabled by default.

---

## Phase 6: User Story 4 — Receive Goal-Aware Meal Suggestions (Priority: P4)

**Goal**: Generate deterministic meal/day/week suggestions that respect calorie/macro tolerances,
exclusions, required recipes, and variety, with useful infeasibility explanations and exact previews.

**Independent Test**: Run feasible and infeasible exact-nutrition fixtures through create/status/result,
validate every constraint and tolerance, partially accept a versioned suggestion, and prove canonical
decimal plan totals match the preview exactly.

### Tests for User Story 4

- [ ] T102 [P] [US4] Write failing CP-SAT scaling, inviolable exclusion/availability/positive-serving constraints, feasible tolerance, fewest-unmet-constraint ranking, normalized 4/3/1/1/2/5 weighted distance, fewer-entry and ordered-recipe-ID tie-break, timeout, determinism, and infeasibility tests in `backend/tests/unit/test_suggestion_solver.py`
- [ ] T103 [P] [US4] Write failing OpenAPI 3.1 API v0.2.0 suggestion create/status/result, exact-decimal objective components/preview, partial acceptance, stale-plan, expiry, and parity contract tests in `backend/tests/contract/test_suggestions_api.py`
- [ ] T104 [P] [US4] Write failing constraint form, feasible/infeasible explanation, preview, and acceptance component tests in `frontend/src/features/suggestions/__tests__/`
- [ ] T105 [P] [US4] Write failing daily/weekly suggestion and accepted-total parity journeys in `frontend/e2e/suggestions.spec.ts`

### Implementation for User Story 4

- [ ] T106 [US4] Create SuggestionRun and SuggestionItem tables with exact target/projected snapshots, plan version, expiry, and lifecycle states in `backend/src/vigor_vine/infrastructure/models/suggestions.py` and `backend/migrations/versions/0008_suggestions.py`
- [ ] T107 [US4] Implement canonical-decimal-to-scaled-integer OR-Tools CP-SAT variables; inviolable exclusion/availability/positive-serving constraints; feasible tolerances; deterministic infeasible ranking by fewest unmet constraints, normalized 4/3/1/1/2/5 distance, fewer entries, and ordered recipe IDs; time limit; and exact explainable result mapping in `backend/src/vigor_vine/domain/suggestion_solver.py`
- [ ] T108 [US4] Implement suggestion validation, candidate preparation, exact target snapshots, infeasibility reasons, expiry, preview parity, and selective acceptance commands in `backend/src/vigor_vine/application/suggestions.py`
- [ ] T109 [US4] Implement idempotent suggestion execution using shared fixed retry/deadline policy and stale-plan rejection in `backend/src/vigor_vine/jobs/suggestions.py`
- [ ] T110 [US4] Implement OpenAPI 3.1 API v0.2.0 suggestion create/status/result/accept routes, canonical decimal-string DTOs, unmet-constraint count, objective score/components, and deterministic ranking disclosure in `backend/src/vigor_vine/api/routes/suggestions.py` and `backend/src/vigor_vine/api/schemas/suggestions.py`
- [ ] T111 [US4] Regenerate and commit exact-decimal suggestion TypeScript bindings in `frontend/src/app/api/generated/`
- [ ] T112 [US4] Implement meal/day/week constraint editing, progress, deterministically ranked alternatives, unmet-constraint/objective explanations, projected totals, and accessible planning-aid-not-medical-advice language in `frontend/src/features/suggestions/SuggestionPage.tsx`
- [ ] T113 [US4] Implement selective suggestion acceptance through normal plan mutations with conflict recovery in `frontend/src/features/suggestions/useAcceptSuggestion.ts`
- [ ] T114 [US4] Add SC-009 feasible/infeasible corpus reporting, exclusion invariants, exact ranking/objective/tie-break evidence, preview/accepted exact-total parity, and under-ten-second solver metrics in `backend/tests/accuracy/test_suggestion_corpus.py`

**Checkpoint**: US4 is independently releasable behind an expansion feature flag and cannot modify
core nutrition estimates or invent recipes.

---

## Phase 7: User Story 5 — Use Core Data Through External Tools (Priority: P5)

**Goal**: Expose scoped MCP reads and idempotent plan/grocery writes that return the same values,
provenance, versions, and failures as the visual application without adding chat behavior.

**Independent Test**: Create/list/revoke separate read/write tokens, call `get_meal_plan` and every other
documented tool, compare canonical decimal output with HTTP/UI state, repeat writes, submit stale
versions, and prove revocation and once-only secret behavior.

### Tests for User Story 5

- [ ] T115 [P] [US5] Write failing HTTP/MCP parity tests for every tool/resource including `get_meal_plan`, canonical decimal strings, display snapshots, and corrections in `backend/tests/contract/test_mcp_parity.py`
- [ ] T116 [P] [US5] Write failing OpenAPI access-token create/list/revoke, once-only secret, token-scope, revocation, rate-limit, idempotency, stale-version, and redaction tests in `backend/tests/integration/test_mcp_security.py`
- [ ] T117 [P] [US5] Write failing MCP Inspector meal-plan read/write, reload, and exact cross-UI consistency journeys in `backend/tests/e2e/test_mcp_server.py`

### Implementation for User Story 5

- [ ] T118 [US5] Implement access-token create/list/revoke commands, allowlisted scopes, hashes, expiry, and once-only secret presentation in `backend/src/vigor_vine/application/access_tokens.py`
- [ ] T119 [US5] Implement canonical OpenAPI 3.1 API v0.2.0 access-token management routes and DTOs in `backend/src/vigor_vine/api/routes/access_tokens.py` and `backend/src/vigor_vine/api/schemas/access_tokens.py`
- [ ] T120 [US5] Assemble the official MCP SDK server, Streamable HTTP transport, application-service injection, and safe problem mapping in `backend/src/vigor_vine/mcp/server.py`
- [ ] T121 [P] [US5] Implement `get_current_goals`, `get_meal_plan`, `get_period_totals`, and `find_recipes` with canonical decimal strings in `backend/src/vigor_vine/mcp/read_tools.py`
- [ ] T122 [P] [US5] Implement idempotent add/update/remove plan and get/regenerate grocery tools in `backend/src/vigor_vine/mcp/write_tools.py`
- [ ] T123 [P] [US5] Implement nutrition-methodology and export-schema resources with no prompt templates in `backend/src/vigor_vine/mcp/resources.py`
- [ ] T124 [US5] Add scoped authentication, revocation checks, rate limits, audit origin, correlation IDs, and HTTP deployment wiring in `backend/src/vigor_vine/mcp/security.py` and `backend/src/vigor_vine/api/main.py`
- [ ] T125 [US5] Regenerate and commit access-token TypeScript bindings in `frontend/src/app/api/generated/`
- [ ] T126 [US5] Implement access-token scope selection, once-only copy, active-token list, and revocation UI in `frontend/src/features/settings/AgentAccessPage.tsx`
- [ ] T127 [US5] Document HTTP token management, MCP connection/scopes, `get_meal_plan`, decimal-string contracts, idempotency, planning-aid-not-medical-advice limitations, and Inspector validation in `docs/agent-integration.md`

**Checkpoint**: US5 passes SC-010 with no business logic in the MCP transport and no general chat or
prompt surface.

---

## Phase 8: User Story 6 — Plan From Available Food and Richer Nutrition (Priority: P6)

**Goal**: Track pantry quantities, search for recipes by available food, apply only safe reversible
grocery deductions, and display supported micronutrients without treating missing values as zero.

**Independent Test**: Seed six-decimal pantry quantities and complete/partial reference data, rank
fully/partially makeable recipes, apply/reverse exact safe deductions, and inspect canonical-string
complete, true-zero, and unavailable micronutrient states.

### Contract and Tests for User Story 6

- [ ] T128 [US6] Extend the OpenAPI 3.1 API v0.2.0 canonical decimal-string contract with pantry CRUD/search/deduction and exactly dietary-fiber-g, sodium/potassium/calcium/iron/magnesium/vitamin-C-mg, and vitamin-D/vitamin-B12-µg schemas in `specs/001-nutrition-recipe-planner/contracts/openapi.yaml`
- [ ] T129 [P] [US6] Write failing six-decimal pantry quantity, unit conversion, match confidence, and reversible-deduction tests in `backend/tests/unit/test_pantry.py`
- [ ] T130 [P] [US6] Write failing fully/partially makeable ranking and missing-ingredient tests in `backend/tests/unit/test_pantry_search.py`
- [ ] T131 [P] [US6] Write failing six-decimal tests for the nine canonical P6 micronutrients covering fixed units, versioned USDA mapping, null-versus-explicit-zero, provenance, lower-of-mass/count coverage, and rollup in `backend/tests/unit/test_micronutrients.py`
- [ ] T132 [P] [US6] Write failing exact-decimal pantry/search/deduction contract and responsive frontend journey tests in `backend/tests/contract/test_pantry_api.py` and `frontend/e2e/pantry.spec.ts`

### Implementation for User Story 6

- [ ] T133 [US6] Create six-decimal PantryItem and PantryDeduction tables with match and reversible-state constraints in `backend/src/vigor_vine/infrastructure/models/pantry.py` and `backend/migrations/versions/0009_pantry.py`
- [ ] T134 [P] [US6] Extend reference import and six-decimal typed nutrition records with a versioned USDA mapping manifest for dietary fiber, sodium, potassium, calcium, iron, magnesium, vitamin D, vitamin B12, and vitamin C plus unavailable-versus-explicit-zero handling in `backend/src/vigor_vine/cli/reference_data.py` and `backend/src/vigor_vine/domain/nutrition.py`
- [ ] T135 [P] [US6] Implement six-decimal pantry normalization, matching, quantity conversion, and manual correction in `backend/src/vigor_vine/application/pantry.py`
- [ ] T136 [P] [US6] Implement fully/partially makeable recipe scoring and explicit missing-ingredient results in `backend/src/vigor_vine/application/pantry_search.py`
- [ ] T137 [US6] Implement visible, safe, reversible pantry deductions through grocery reconciliation in `backend/src/vigor_vine/application/pantry_deductions.py`
- [ ] T138 [US6] Implement pantry CRUD/search/deduction routes and canonical decimal-string DTOs matching the amended contract in `backend/src/vigor_vine/api/routes/pantry.py` and `backend/src/vigor_vine/api/schemas/pantry.py`
- [ ] T139 [US6] Regenerate and commit exact-decimal pantry/micronutrient TypeScript bindings in `frontend/src/app/api/generated/`
- [ ] T140 [P] [US6] Implement pantry inventory, match review, quantity editing, and makeable-recipe search in `frontend/src/features/pantry/PantryPage.tsx`
- [ ] T141 [P] [US6] Add provenance-aware panels for the nine canonical P6 micronutrients, unavailable-versus-explicit-zero states, canonical units, and accessible planning-aid-not-medical-advice language to `frontend/src/features/recipes/NutritionPanel.tsx` and `frontend/src/features/plans/MacroSummary.tsx`

**Checkpoint**: US6 remains an optional expansion and does not change the core P1-P3 grocery result
unless pantry subtraction is explicitly enabled.

---

## Phase 9: Polish & Cross-Cutting Release Gates

**Purpose**: Prove contract compatibility, security, performance, accessibility, provider-independent
manual operation, full-owner erasure, recoverability, documentation, and scope discipline across the
selected release boundary.

- [ ] T142 Verify the implementation-generated OpenAPI 3.1 document for API v0.2.0, decimal-string schemas, lifecycle/token/suggestion routes, planning-aid descriptions, and MCP tools against `specs/001-nutrition-recipe-planner/contracts/` and fail CI on drift in `backend/tests/contract/test_openapi_compatibility.py`
- [ ] T143 [P] Complete SSRF, redirect rebinding, diagnostic encryption/expiry, raw-provider non-retention, archive traversal, CSRF, token-scope, secret-redaction, and dependency vulnerability coverage in `backend/tests/security/`
- [ ] T144 [P] On the Linux x86-64 4-vCPU/8-GiB/SSD colocated reference profile, seed the documented dataset, warm each path with 10 unmeasured requests, profile 10,000-recipe reads/search, 50-entry plan mutations, under-one-second job acknowledgement, polling load, grocery generation, and suggestion limits for three runs of at least 100 measured requests, and record p50/p95/max plus budgets in `docs/performance.md`
- [ ] T145 [P] Complete keyboard, focus, contrast, reduced-motion, polling/status announcements, destructive confirmation, screen-reader, desktop, and 390x844 overflow checks in `frontend/e2e/accessibility.spec.ts` and `frontend/e2e/responsive.spec.ts`
- [ ] T146 [P] Prove SC-015 with provider-disabled, timeout, invalid-structured-output, and failure substitutes while exercising manual recipe editing/nutrition, goals, plans, groceries, backup, and export plus affected partial/failed recovery states in `backend/tests/integration/test_provider_degraded_workflows.py` and `frontend/e2e/provider-degraded.spec.ts`
- [ ] T147 [P] Write failing offline full-owner-erasure tests for stopped-service enforcement, exact confirmation, unavailable-ledger fail-closed behavior, same-volume quarantine rollback, post-ledger resumability with maintenance lock, complete core/expansion/token/session/job/media/export removal, single owner-owned ledger append, bootstrap state, and older-backup zero-resurrection replay in `backend/tests/integration/test_owner_erasure.py`
- [ ] T148 Implement the maintenance-locked offline `vigor-vine owner erase` command with exact confirmation, ledger preflight, same-volume managed-file quarantine, ledger-first append, idempotent owner-scope database deletion, post-ledger resumability, verified bootstrap reset, quarantine removal, and safe recovery in `backend/src/vigor_vine/application/owner_erasure.py` and `backend/src/vigor_vine/cli/owner.py`
- [ ] T149 Document the offline full-owner-erasure preconditions, disposable validation, exact confirmation, managed scope, ledger dependency, staged-file recovery, bootstrap result, backup replay, and emergency failure handling in `docs/owner-erasure.md`, `docs/backup-restore.md`, and `docs/operations-runbook.md`
- [ ] T150 Run a clean-instance exact-decimal backup/export/restore comparison including media, detached history, excluded diagnostics, backup/current ledger cursors, verified recipe-owned and owner-owned erasure replay, bootstrap-state restoration after owner erasure, zero resurrection, and fail-closed evidence in `artifacts/restore-report.md`
- [ ] T151 [P] Complete production Compose, TLS/reverse-proxy, trusted-header, retention scheduling, diagnostic encryption, independently preserved erasure-ledger volume/replication, backup rotation, upgrade, volume, and health guidance in `docs/self-hosting.md`
- [ ] T152 [P] Generate the software bill of materials, verify pinned licenses against `research.md`, and document update policy in `artifacts/sbom.json` and `docs/dependencies-and-licenses.md`
- [ ] T153 [P] Document fixed job timeout/retry/deadline behavior, polling, failure codes, queue/broker/database recovery, provider degradation, offline owner erasure, 24h/30d/1y retention, correlation IDs, and operator diagnostics in `docs/operations-runbook.md`
- [ ] T154 Execute every command and scenario in `specs/001-nutrition-recipe-planner/quickstart.md` and record deviations or corrections in that file
- [ ] T155 Close all applicable items in `specs/001-nutrition-recipe-planner/checklists/requirements.md` and `specs/001-nutrition-recipe-planner/checklists/nutrition.md` with links to final evidence
- [ ] T156 Audit routes, UI, dependencies, and documentation for prohibited chatbot, photo recognition, social, subscription-only, medical-advice presentation, and unapproved multi-user scope and record the result in `artifacts/scope-audit.md`
- [ ] T157 Conduct the SC-008 study with at least 20 product-naive participants, including at least five novice and five experienced gym-focused meal planners plus at least eight narrow-mobile and eight desktop completions; require every unaided step within five minutes, apply ceiling-based 90% pass rounding, and record exclusions and anonymized evidence in `artifacts/usability-report.md`
- [ ] T158 Run the complete backend/frontend format, lint, type, unit, integration, contract, provider-degraded, owner-erasure, retention, erasure-ledger restore, 50-public-page recipe accuracy/import, performance, build, Playwright, and Docker smoke gates through `scripts/verify.ps1` and archive results in `artifacts/release-gates.md`

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 Setup
    -> Phase 2 Foundation
        -> US1 Recipe + Nutrition (MVP)
            -> US2 Goals + Planning
                -> US3 Grocery + Backup (Core release)
            -> US4 Suggestions (after US2 and P1 accuracy gate)
            -> US5 External Tools (after the application services each tool exposes)
            -> US6 Pantry + Micronutrients (after US1; deductions also require US3)
All selected stories -> Phase 9 release gates
```

- **Phase 1** has no prerequisite. T001 is a documentation gate; T002/T003 can start after it.
- **Phase 2** depends on Phase 1 and blocks all stories.
- **US1** depends only on Phase 2 and is the suggested MVP.
- **US2** uses the recipe/nutrition aggregate created in US1; its tests can use seeded snapshots.
- **US3** uses US2 plan entries and US1 ingredient quantities; completing US1-US3 defines the core
  release.
- **US4** depends on US1 resolved nutrition, US2 goals/plans, and the P1 accuracy gate.
- **US5** can build transport/authentication after Phase 2, but each tool waits for its corresponding
  US1-US3 application command/query. It does not depend on US4 or US6.
- **US6** recipe search depends on US1; grocery deductions depend on US3. It does not depend on US4 or
  US5.
- **Phase 9** applies only to stories selected for the release, but core security, provider-degraded
  manual operation, full-owner erasure, backup, usability, accessibility, checklist, scope, and full-
  gate tasks are mandatory for the core release. T147 precedes T148; T148 and T149 precede the T150
  restore comparison; T158 is always last.

### Entity and Contract Ownership

- **Foundation**: exact-decimal primitives, OwnerAccount preferences, Session, AccessToken, encrypted
  expiring MediaAsset, bounded ProcessingJob, OutboxEvent, retention sweeps, health, auth, and errors.
- **US1**: Recipe lifecycle, RecipeInstruction, Ingredient, ReferenceDataset, FoodReference,
  FoodNutrient, IngredientMatch, NutritionEstimate, NutritionCorrection, and recipe/job endpoints.
- **US2**: UserGoal, MealTarget, MealPlan, MealPlanEntry, MealNutritionSnapshot, goal/plan endpoints.
- **US3**: GroceryList, GroceryItem, GroceryItemSource, export/backup contracts.
- **US4**: SuggestionRun, SuggestionItem, suggestion endpoint and job.
- **US5**: Access-token management behavior, MCP tools/resources/transport over existing services.
- **US6**: PantryItem, PantryDeduction, pantry/search endpoints, micronutrient expansion.

### Within Each Story

1. Write the listed tests and observe the intended failure.
2. Create migrations/models and domain policies.
3. Implement repositories/application services and background handlers.
4. Implement transport DTOs/routes and regenerate bindings.
5. Implement UI and journey integration.
6. Run the independent test and story checkpoint before beginning a dependent story.

## Parallel Opportunities

- Phase 1 backend, frontend, design-token, Compose, and CI tasks marked `[P]` use distinct files.
- Foundation auth tests, errors, observability, media, job tests, Celery configuration, and frontend
  shell tasks marked `[P]` can proceed once their shared scaffolding exists.
- Test files marked `[P]` within each story can be authored concurrently before implementation.
- US4, US5, and the non-grocery portion of US6 can proceed in parallel after US1/US2 service contracts
  stabilize.
- Files under `frontend/src/features/recipes`, `goals`, `plans`, `grocery`, `suggestions`, `settings`,
  and `pantry` are deliberately separated to reduce conflicts.

### Parallel Example: US1

```text
T035 Recipe domain tests
T036 Ingredient processing tests
T037 Nutrition calculation tests
T038 Recipe API contract tests
T039 Job integration tests
T040 Accuracy harness
T041 Frontend component tests
T042 Playwright journeys
```

After the persistence models are stable, T047-T052 and T054 can proceed in parallel before T053,
T055, T056, and T058 integrate the pipeline.

### Parallel Example: US2

```text
T067 Goal tests
T068 Snapshot/total tests
T069 API contract tests
T070 Snapshot integration tests
T071 Frontend component tests
T072 Playwright journeys
```

After T073, goal policy (T074) and snapshot policy (T075) can proceed in parallel.

### Parallel Example: US3

```text
T085 Aggregation property tests
T086 Reconciliation tests
T087 Grocery API contract tests
T088 Export contract tests
T089 Backup/restore tests
T090 Grocery Playwright journey
```

Export (T098) and backup CLI (T099) can proceed in parallel with grocery UI work after their tests.

### Parallel Example: US4-US6

- US4 test tasks T102-T105 run in parallel; UI T112 can begin once result DTOs stabilize.
- US5 parity/security/end-to-end tests T115-T117 run in parallel; read tools T121, write tools T122,
  and resources T123 use separate files.
- US6 tests T129-T132 run in parallel after contract task T128; reference nutrients T134, pantry
  matching T135, and search T136 then use separate modules.

## Implementation Strategy

### MVP First

1. Complete T001-T034 (requirements closure, setup, and foundation).
2. Complete T035-T066 (US1).
3. Stop and run the independent P1 journey plus SC-001/SC-002/SC-003/SC-013/SC-014 gates over 30+20 cases.
4. Demonstrate exact decimals, lifecycle erasure, honest uncertainty, durable corrections, bounded
   retries, retention, and degraded manual operation before expanding scope.

### Core Release

1. Add US2 (T067-T084) only after P1 meets the accuracy gate.
2. Add US3 (T085-T101) after goal/plan snapshots and totals are stable.
3. Run applicable Phase 9 gates, especially provider-degraded operation, offline owner erasure,
   backup/restore, SC-008 usability, accessibility, scope, retention, and T158 full verification.
4. Release P1-P3 without waiting for suggestions, MCP, pantry, or micronutrients.

### Expansion Releases

1. Release US4, US5, and US6 independently behind disabled-by-default feature flags.
2. Do not couple an expansion migration or route to the availability of another expansion.
3. Re-run Phase 9 gates for each enabled expansion and preserve the core P1-P3 results.

## Notes

- `[P]` means parallelizable only after all earlier phase and explicit task dependencies are satisfied.
- Story labels map directly to the six user stories in `spec.md`.
- Tasks that amend contracts precede tests and implementation that depend on the amended contract.
- Generated clients are committed and CI rejects uncommitted or incompatible regeneration.
- Each task should be committed alone or with its directly coupled failing test/implementation pair.
- No task may add an in-app chatbot, photo nutrition recognition, social/community scope, a required
  subscription, or broad multi-user administration without a separately approved specification and
  constitution amendment.
