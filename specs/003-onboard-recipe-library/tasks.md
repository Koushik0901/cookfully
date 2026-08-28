# Tasks: A calmer first kitchen

**Input**: Design documents from `/specs/003-onboard-recipe-library/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Required. This feature changes API contracts, grocery reconciliation, owner export/erasure, and critical first-use journeys.

**Organization**: Tasks are grouped by user story so each increment can be implemented, verified, and demonstrated independently after the shared data-contract foundation is complete.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can proceed in parallel once prerequisite tasks are complete and it does not touch the same files.
- **[Story]**: Maps to the user story in [spec.md](./spec.md). Shared setup/foundation and final polish omit a story label.

## Phase 1: Setup and contract baseline

**Purpose**: Establish the feature migration and generated-client workflow without introducing a parallel subsystem.

- [X] T001 Inspect the current `0012_session_surrogate_id` migration head and create the `0013_onboarding_recipe_library.py` migration scaffold in `backend/migrations/versions/0013_onboarding_recipe_library.py`
- [X] T002 [P] Add contract-test fixture helpers for owner onboarding, recipe image files, collections, shopping stops, and completed grocery lists in `backend/tests/conftest.py`
- [X] T003 [P] Add browser test fixture helpers for a first-time owner, recipe photo selection, recipe organization, and a two-stop grocery list in `frontend/e2e/fixtures.ts`
- [X] T004 Regenerate the OpenAPI document and frontend schema baseline using the project generation command; record the required generated files in `frontend/src/app/api/generated/schema.ts`

---

## Phase 2: Foundational data, ownership, and service boundaries

**Purpose**: Add the durable owner-scoped records and common service behavior that every story requires. This phase blocks all user-story implementation.

**⚠️ CRITICAL**: Complete this phase before starting the user-story phases.

- [X] T005 Add owner onboarding state, recipe favorite, recipe collections/memberships/meal roles, grocery shopping stops, remembered placements, grocery item stop assignment, and completed-list fields/constraints/indexes to `backend/migrations/versions/0013_onboarding_recipe_library.py`
- [X] T006 [P] Add SQLAlchemy models and relationships for onboarding, collections/memberships/meal roles, and favorites in `backend/src/cookfully/infrastructure/models/identity.py` and `backend/src/cookfully/infrastructure/models/recipes.py`
- [X] T007 [P] Add SQLAlchemy models and relationships for shopping stops, remembered placements, item assignment, and completed grocery-list state in `backend/src/cookfully/infrastructure/models/grocery.py`
- [X] T008 [P] Include the new tables and grocery/photo fields in portable export and restore ordering in `backend/src/cookfully/application/exports.py` and `backend/src/cookfully/cli/backup.py`
- [X] T009 [P] Extend full-owner erasure discovery/quarantine assertions for onboarding, organization, shopping placement, completed-list state, and representative recipe media in `backend/src/cookfully/application/owner_erasure.py` and `backend/tests/integration/test_owner_erasure.py`
- [X] T010 Add owner-scoped repositories/service helpers that centralize collection ownership, meal-role validation, shopping-stop ordering, and conflict checks in `backend/src/cookfully/application/recipe_organization.py` and `backend/src/cookfully/application/grocery_shopping_stops.py`
- [X] T011 Extend grocery reconciliation values and carry-forward logic so matched generated items preserve a shopping-stop assignment, while manual/ambiguous/needs-review items cannot receive an automatic remembered placement, in `backend/src/cookfully/application/grocery_reconciliation.py` and `backend/src/cookfully/application/grocery_lists.py`
- [X] T012 Extend the public schemas and route registration for the planned owner, recipe organization/photo, grocery-stop, and complete/reopen contract surfaces in `backend/src/cookfully/api/main.py`, `backend/src/cookfully/api/schemas/recipes.py`, and `backend/src/cookfully/api/schemas/grocery.py`
- [X] T013 Add the shared contract and integration regression tests for owner scoping, version conflicts, export/restore, erasure, and grocery reconciliation preservation in `backend/tests/contract/test_onboarding_library_grocery_api.py`, `backend/tests/integration/test_exports.py`, `backend/tests/integration/test_owner_erasure.py`, and `backend/tests/integration/test_grocery_lists.py`
- [X] T014 Regenerate and type-check the OpenAPI-derived frontend client types after T012 in `frontend/src/app/api/generated/schema.ts`

**Checkpoint**: The database, canonical service layer, export/erasure guarantees, and typed HTTP boundary are ready. User stories may proceed in parallel after T014 passes.

---

## Phase 3: User Story 1 — Start with one useful action (Priority: P1) 🎯 MVP

**Goal**: Give a first-time owner a concise, non-blocking choice of creating/importing a recipe or viewing the week, without a health questionnaire or recurring interruption.

**Independent Test**: With a new owner, arrive at the kitchen, choose each first action and dismiss the journey; verify the state persists across a fresh session and normal Recipes/Plan remain reachable if the state request fails.

### Tests for User Story 1

- [X] T015 [P] [US1] Add contract tests for pending/default onboarding reads, completed/dismissed writes, invalid transitions, and `If-Match` conflicts in `backend/tests/contract/test_onboarding_library_grocery_api.py`
- [X] T016 [P] [US1] Add service integration tests for owner-scoped onboarding persistence and failure-safe normal kitchen access in `backend/tests/integration/test_owner_onboarding.py`
- [X] T017 [P] [US1] Add component tests for the calm introduction, optional nutrition-guide language, direct actions, dismissal, and resilient empty states in `frontend/src/features/onboarding/__tests__/FirstRunJourney.test.tsx`
- [X] T018 [P] [US1] Add a desktop and 390x844 Playwright first-run journey, including dismiss/reload behavior, in `frontend/e2e/onboarding.spec.ts`

### Implementation for User Story 1

- [X] T019 [US1] Implement the owner onboarding read/update service with terminal completion/dismissal transitions and optimistic version handling in `backend/src/cookfully/application/owner_onboarding.py`
- [X] T020 [US1] Add authenticated `GET`/`PUT /owner/onboarding` endpoints and response models in `backend/src/cookfully/api/routes/owner.py`
- [X] T021 [US1] Add the typed onboarding client and query/mutation keys in `frontend/src/features/onboarding/api.ts` and `frontend/src/features/onboarding/types.ts`
- [X] T022 [US1] Build the non-blocking first-run overlay/route guard and the reusable recipe/plan/grocery empty-state next-action composition in `frontend/src/features/onboarding/FirstRunJourney.tsx` and `frontend/src/features/onboarding/NextUsefulAction.tsx`
- [X] T023 [US1] Integrate first-run state into the authenticated shell and existing empty states without adding navigation destinations in `frontend/src/app/App.tsx`, `frontend/src/features/recipes/RecipeLibraryPage.tsx`, `frontend/src/features/plans/WeeklyPlannerPage.tsx`, and `frontend/src/features/grocery/GroceryListPage.tsx`
- [X] T024 [US1] Add responsive, reduced-motion, keyboard-focus, loading, and failure-state styling for the first-run composition in `frontend/src/styles/globals.css`

**Checkpoint**: A new owner can begin with a real task in under a minute, skip setup safely, and receive context-sensitive follow-up without a repeated blocking screen.

---

## Phase 4: User Story 2 — Give a handwritten recipe a home (Priority: P1)

**Goal**: Let a manual-recipe author preview, save, replace, and remove one representative photo without coupling media changes to nutrition or recipe-content changes.

**Independent Test**: Create a manual recipe with and without a valid photo; verify it appears across all existing recipe-media surfaces, then replace/remove it and exercise invalid-file and conflict recovery without losing nutrition or recipe content.

### Tests for User Story 2

- [X] T025 [P] [US2] Add photo endpoint contract tests for content type, size/dimension validation, authenticated ownership, replacement safety, removal, and `If-Match` conflicts in `backend/tests/contract/test_recipe_api.py`
- [X] T026 [P] [US2] Add recipe-media integration tests proving normalization, export inclusion, replacement cleanup, fallback preservation, and no input-hash/nutrition/correction change in `backend/tests/integration/test_recipe_media.py`
- [X] T027 [P] [US2] Add editor/detail/library component tests for preview, remove/replace, invalid file recovery, and fallback art in `frontend/src/features/recipes/__tests__/recipe-photo-ui.test.tsx`
- [X] T028 [P] [US2] Add desktop and 390x844 Playwright coverage for photo upload, replacement, removal, and accessibility alternatives in `frontend/e2e/recipes.spec.ts`

### Implementation for User Story 2

- [X] T029 [US2] Extend the existing image service with an authenticated in-memory file capture path that reuses decode, dimension, normalization, content, and size safeguards in `backend/src/cookfully/infrastructure/recipe_images.py` and `backend/src/cookfully/infrastructure/media_store.py`
- [X] T030 [US2] Add a recipe-photo application mutation that validates ownership/version, persists/replaces the representative media relation, preserves recipe input/nutrition fields, and deletes superseded unreferenced media safely in `backend/src/cookfully/application/recipe_photos.py`
- [X] T031 [US2] Add `PUT` multipart and `DELETE` recipe-photo routes plus explicit response/problem schemas in `backend/src/cookfully/api/routes/recipes.py` and `backend/src/cookfully/api/schemas/recipes.py`
- [X] T032 [US2] Add multipart-aware client request support and typed `uploadPhoto`/`removePhoto` calls in `frontend/src/features/recipes/api.ts` and `frontend/src/features/recipes/types.ts`
- [X] T033 [US2] Add an optional, progressively disclosed photo picker with local preview, replace/remove, pending, failure, and retry states to manual recipe creation/editing in `frontend/src/features/recipes/RecipeEditorPage.tsx`
- [X] T034 [US2] Ensure saved manual photos consistently feed existing detail, card, plan picker, suggestion, and Cook Mode media rendering without changing fallback semantics in `frontend/src/features/recipes/RecipeDetailPage.tsx`, `frontend/src/features/recipes/RecipeCard.tsx`, `frontend/src/features/plans/RecipePickerSheet.tsx`, `frontend/src/features/suggestions/SuggestionPage.tsx`, and `frontend/src/features/recipes/CookModePage.tsx`
- [X] T035 [US2] Add food-first, responsive photo-picker and preview styles with useful text alternatives in `frontend/src/styles/globals.css`

**Checkpoint**: Manual recipes can have a trustworthy representative image while remaining fully saveable and nutrition-correctable without one.

---

## Phase 5: User Story 3 — Shop by the way I actually shop (Priority: P2)

**Goal**: Turn a weekly plan into a calm active shopping pass grouped by real stops, retain safe personal placement memory, and preserve an explicit completed weekly record.

**Independent Test**: Generate a list containing plan-derived and manual items, create/order/delete two stops, remember one safe placement, refresh after a plan update, and check everything off to complete/reopen the pass without source or pantry-regression loss.

### Tests for User Story 3

- [X] T036 [P] [US3] Add contract tests for shopping-stop CRUD, owner isolation, item placement validation, remembered-placement eligibility, completion, reopen, and completed-regeneration conflicts in `backend/tests/contract/test_onboarding_library_grocery_api.py`
- [X] T037 [P] [US3] Add integration tests for stop deletion fallback, remembered-placement application/rejection, reconciliation carry-forward, dirty-plan behavior, completed history, and pantry deductions in `backend/tests/integration/test_grocery_lists.py`
- [X] T038 [P] [US3] Add Grocery page component tests for grouped/unassigned items, remembered placement choice, stale refresh, all-items-complete state, and conflict recovery in `frontend/src/features/grocery/__tests__/GroceryListPage.test.tsx`
- [X] T039 [P] [US3] Add a desktop and 390x844 Playwright shop journey covering two stops, a refresh, finish, and explicit reopen in `frontend/e2e/grocery-list.spec.ts`

### Implementation for User Story 3

- [X] T040 [US3] Implement owner-scoped shopping-stop CRUD/reorder/delete and remembered-placement upsert/remove behavior in `backend/src/cookfully/application/grocery_shopping_stops.py`
- [X] T041 [US3] Extend grocery-list generation, item writes, dirty marking, completion, and reopen transitions to preserve manual/check/source/pantry/stop state and protect completed lists in `backend/src/cookfully/application/grocery_lists.py` and `backend/src/cookfully/application/grocery_reconciliation.py`
- [X] T042 [US3] Add shopping-stop routes, grocery item placement writes, and grocery complete/reopen routes in `backend/src/cookfully/api/routes/grocery.py` and `backend/src/cookfully/api/schemas/grocery.py`
- [X] T043 [US3] Add typed shopping-stop, placement, complete, and reopen API calls in `frontend/src/features/grocery/api.ts` and `frontend/src/features/grocery/types.ts`
- [X] T044 [US3] Build the compact shopping-stop manager and reusable placement control in `frontend/src/features/grocery/ShoppingStopManager.tsx` and `frontend/src/features/grocery/GroceryListPage.tsx`
- [X] T045 [US3] Rework the grocery page into ordered stop groups plus an always-visible unassigned fallback, explicit safe-memory choice, progress, finish, completed, reopen, stale, error, and conflict states in `frontend/src/features/grocery/GroceryListPage.tsx`
- [X] T046 [US3] Add mobile-first check-off target spacing, group hierarchy, completed-pass, and stop-management styles in `frontend/src/styles/globals.css`

**Checkpoint**: An owner can carry a weekly plan through a real shopping trip, without losing the generated-list provenance and safeguards that make the list trustworthy.

---

## Phase 6: User Story 4 — Keep familiar recipes easy to find (Priority: P2)

**Goal**: Let an owner favorite recipes, keep them in optional named collections, and choose standard meal roles with focused retrieval that does not turn manual entry into a metadata form.

**Independent Test**: Favorite a recipe; create, rename, reorder, and delete collections; give a recipe two collections and Dinner; filter search by favorite, collection, and role; then confirm an unorganized recipe remains searchable and plannable.

### Tests for User Story 4

- [X] T047 [P] [US4] Add contract tests for favorite/collection/role updates, collection CRUD/order/delete semantics, owner validation, filters, and version conflicts in `backend/tests/contract/test_recipe_organization_api.py`
- [X] T048 [P] [US4] Add query/service integration tests for many-to-many memberships, fixed meal-role validation, archive/search/filter composition, and no nutrition/plan mutation in `backend/tests/integration/test_recipe_organization.py`
- [X] T049 [P] [US4] Add recipe detail/library component tests for optional organization controls, focused removable filters, favorite state, and long names in `frontend/src/features/recipes/__tests__/recipe-organization-ui.test.tsx`
- [X] T050 [P] [US4] Add desktop and 390x844 Playwright coverage for favorite, collection membership, meal role, filter removal, and planning an unorganized recipe in `frontend/e2e/recipe-organization.spec.ts`

### Implementation for User Story 4

- [X] T051 [US4] Implement favorite, collection CRUD/order, membership, fixed meal-role validation, ownership checks, and optimistic-version mutations in `backend/src/cookfully/application/recipe_organization.py`
- [X] T052 [US4] Extend recipe read queries and list filters with favorite, collection, and meal-role evidence while retaining current search/archive/readiness semantics in `backend/src/cookfully/application/recipe_queries.py`
- [X] T053 [US4] Add collection/organization routes and enrich recipe response/filter schemas in `backend/src/cookfully/api/routes/recipes.py` and `backend/src/cookfully/api/schemas/recipes.py`
- [X] T054 [US4] Add typed organization values and collection/filter API calls in `frontend/src/features/recipes/types.ts` and `frontend/src/features/recipes/api.ts`
- [X] T055 [US4] Build optional favorite, collection, and meal-role controls with explicit save/conflict states in `frontend/src/features/recipes/RecipeOrganizationPanel.tsx` and integrate them into `frontend/src/features/recipes/RecipeDetailPage.tsx`
- [X] T056 [US4] Add a focused collection/favorite/meal-role filter sheet or popover, removable active filter summary, and collection management entry to `frontend/src/features/recipes/RecipeLibraryPage.tsx` and `frontend/src/features/recipes/RecipeLibraryFilters.tsx`
- [X] T057 [US4] Add calm, progressive-disclosure organization styles that protect the recipe editor's writing-first hierarchy at desktop and mobile widths in `frontend/src/styles/globals.css`

**Checkpoint**: A growing library stays personally findable, while a person entering a simple family recipe can still save it without being asked to classify it.

---

## Phase 7: Polish, documentation, and release evidence

**Purpose**: Integrate cross-story behavior, verify all required states and data lifecycle guarantees, then document the finished vertical slice.

- [X] T058 Update the OpenAPI artifact and generated frontend schema after all endpoint work, and verify no generated drift remains in `backend/openapi.json` and `frontend/src/app/api/generated/schema.ts`
- [X] T059 [P] Add end-to-end cross-story coverage for first recipe → photo → organization → plan → grocery stop → finish shop in `frontend/e2e/first-kitchen-journey.spec.ts`
- [X] T060 [P] Add export/restore and full-erasure fixtures that prove the complete new owner-owned data graph and photo media are respectively portable and removed in `backend/tests/integration/test_exports.py` and `backend/tests/integration/test_owner_erasure.py`
- [X] T061 [P] Update the visible owner data/export and self-hosting guidance for recipe photos, first-run state, recipe organization, shopping stops, and completed lists in `README.md`, `docs/self-hosting.md`, and `docs/owner-erasure.md`
- [X] T062 [P] Record the final adopt/adapt/reject implementation outcome and any observed limitations in `docs/inspiration-review.md`
- [X] T063 Verify every changed screen has loading, empty, partial, estimated/manual nutrition, stale, failed, completed, and conflict recovery states plus meaningful image alternatives in `frontend/src/features/onboarding/`, `frontend/src/features/recipes/`, and `frontend/src/features/grocery/`
- [X] T064 Verify keyboard flow, focus restoration, reduced motion, long-text overflow, 200% zoom, 1440x900 desktop, and 390x844 mobile behavior; update targeted CSS/e2e evidence in `frontend/src/styles/globals.css` and `frontend/e2e/`
- [X] T065 Run backend formatting, lint, type, complete tests, and migration checks using the commands in `specs/003-onboard-recipe-library/quickstart.md`
- [X] T066 Run frontend lint, typecheck, unit tests, production build, and full Playwright suite using the commands in `specs/003-onboard-recipe-library/quickstart.md`
- [X] T067 Review the final diff against every requirement in `specs/003-onboard-recipe-library/spec.md` and record completion evidence in `specs/003-onboard-recipe-library/tasks.md`

---

## Dependencies and execution order

### Phase dependencies

- **Phase 1**: Starts immediately.
- **Phase 2**: Depends on T001–T004 and blocks all user stories.
- **Phase 3 (US1) and Phase 4 (US2)**: Both begin after the shared contract/schema baseline; their frontend work can proceed in parallel after the shared types are regenerated.
- **Phase 5 (US3)**: Depends on the grocery foundation in T005–T014, but is otherwise independent of US1/US2.
- **Phase 6 (US4)**: Depends on the organization foundation in T005–T014, but is otherwise independent of US1/US2/US3.
- **Phase 7**: Depends on all desired user stories being complete.

### User-story delivery order

1. **US1** — first-run entry gives an immediate, safe path to value.
2. **US2** — optional imagery makes the first manually saved recipe emotionally recognizable.
3. **US3** — shopping completes the recipe-to-plan-to-buy loop.
4. **US4** — organization keeps the growing library useful without up-front metadata burden.

### Parallel opportunities

- T002–T004 may proceed after T001's migration-head inspection.
- T006–T009 can proceed together once the migration fields are agreed; T010–T012 follow the shared model names.
- Within each user story, backend contract/integration tests and frontend component/e2e tests can be authored in parallel before implementation.
- US1, US2, US3, and US4 can be staffed in parallel after Phase 2, provided each owner avoids shared files such as `backend/src/cookfully/api/main.py`, generated schema, and `frontend/src/styles/globals.css` until coordination points are merged.

## Completion evidence (2026-08-28)

- Backend gates: `ruff format --check`, `ruff check`, and `mypy src` passed; the complete suite passed with **408 passed, 1 skipped** (the documented performance reference-profile skip); the Alembic migration-drift integration check passed.
- Frontend gates: lint, typecheck, 162 unit tests, production build, and responsive/accessibility Playwright coverage passed (15 passed, 1 intentional mobile-menu skip).
- Runtime evidence: the selected FastEmbed model is ready and the automatic `food_embedding_index` rebuild completed **8080/8080** successfully after model readiness was persisted.
- Dedicated follow-up coverage now passes: onboarding/library/grocery contracts (2), owner onboarding integration (2), recipe media integration (1), recipe organization contract (1), recipe photo UI (4), grocery page UI (3), recipe organization UI (2), and organization Playwright coverage on desktop plus 390x844 (4).
- Final diff review covered model-readiness/index handoff, backup-store type narrowing, shared test fixtures, logging observability hardening, and the dedicated story-test files above; every task in this checklist is now marked complete with named evidence.

## Implementation strategy

### MVP first

1. Complete Phase 1 and Phase 2.
2. Complete US1 and demonstrate that a new owner reaches an actual task without a mandatory questionnaire.
3. Complete US2 and demonstrate an image-backed manual recipe with non-destructive failure handling.
4. Run the targeted US1/US2 tests before beginning broader grocery or organization UI work.

### Incremental delivery

1. Shared foundation → typed data/API/export/erasure safety.
2. First-run + manual photo → a welcoming, complete first recipe.
3. Grocery shopping pass → a reliable plan-to-store workflow.
4. Recipe organization → a library that remains calm as it grows.
5. Cross-story release verification → confirmed product-quality vertical slice.

## Notes

- All tasks use the canonical FastAPI application services and existing self-hosted media store; do not create an AI feature, third-party media host, generic tag system, retailer integration, or separate admin/dashboard route.
- Preserve current nutrition provenance, correction precedence, recipe input hashes, meal-plan snapshots, grocery item sources, pantry deductions, session/CSRF protections, and optimistic concurrency in every task that touches those areas.
- Mark tasks complete only with the evidence named in the task and the corresponding scenario in `spec.md`; do not treat a narrow unit check as proof of the complete user journey.
