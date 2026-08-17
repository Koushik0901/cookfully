# Instant Feedback, Trust, and Thumbnail Cropping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make recipe actions feel immediate and trustworthy while adding persistent focal-point thumbnail cropping for imports and recipe editing.

**Architecture:** Preserve the existing FastAPI, PostgreSQL, Celery, React, and TanStack Query architecture. Add normalized crop and origin metadata to the recipe contract, make the existing chained recipe jobs readable through stage labels and progress, and use focused optimistic mutation feedback instead of introducing a global notification framework. Reuse one crop dialog for import review and editor photo selection.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, Alembic, PostgreSQL, React 19, TypeScript, TanStack Query, Radix Dialog, Vitest, Playwright.

## Global Constraints

- Preserve original ingredient text, nutrition provenance, serving basis, and active correction precedence.
- Use exact-decimal strings for persisted crop coordinates and zoom values.
- Background handlers remain idempotent and reject stale input hashes.
- Verify desktop and 390x844 behavior, keyboard access, overflow, and explicit loading/partial/estimated/manual/stale/failed states.
- Do not add a crop dependency; implement pointer/touch drag plus keyboard-accessible range controls with existing React/browser APIs.

---

### Task 1: Add Recipe Crop and Origin Contracts

**Files:**
- Create: `backend/alembic/versions/<new_revision>_recipe_thumbnail_crop_origin.py`
- Modify: `backend/src/cookfully/infrastructure/models/recipes.py`
- Modify: `backend/src/cookfully/application/recipes.py`
- Modify: `backend/src/cookfully/application/recipe_queries.py`
- Modify: `backend/src/cookfully/api/schemas/recipes.py`
- Modify: `frontend/src/features/recipes/types.ts`
- Modify: `frontend/src/features/recipes/api.ts`
- Test: `backend/tests/contract/test_recipe_api.py`
- Test: `backend/tests/unit/test_recipe_application.py`

**Interfaces:**
- Add `ThumbnailCrop` with `focal_x`, `focal_y`, and `zoom` as normalized decimal values.
- Add `origin_kind` values `manual`, `web_import`, and `cookbook_import`.
- Expose `thumbnailCrop` and `originKind` in recipe read/write schemas.

- [ ] Write failing contract tests for default crop values, exact decimal serialization, origin values, and invalid ranges.
- [ ] Run `uv run --directory backend pytest backend/tests/contract/test_recipe_api.py -k "crop or origin" -v`; expect failures because the fields do not exist.
- [ ] Add numeric recipe columns with defaults `0.500000`, `0.500000`, `1.000000` and a non-null origin default of `manual`.
- [ ] Add Pydantic validation for `focalX` and `focalY` in `[0, 1]` and `zoom` in `[1, 3]`.
- [ ] Thread the values through `RecipeWrite`, create/update, `RecipeRead`, and response serializers.
- [ ] Regenerate the frontend API schema from live backend OpenAPI and update frontend types.
- [ ] Run focused backend tests, frontend typecheck, and the OpenAPI parity test; expect all to pass.
- [ ] Commit with `feat: add recipe thumbnail crop and origin contracts`.

### Task 2: Persist Import Covers and Attachment Results

**Files:**
- Modify: `backend/src/cookfully/application/import_preview.py`
- Modify: `backend/src/cookfully/application/recipe_photos.py`
- Modify: `backend/src/cookfully/api/schemas/jobs.py`
- Modify: `backend/src/cookfully/api/routes/recipes.py`
- Modify: `backend/src/cookfully/infrastructure/recipe_importer.py`
- Modify: `frontend/src/features/recipes/RecipeImportDialog.tsx`
- Modify: `frontend/src/features/recipes/api.ts`
- Modify: `frontend/src/features/recipes/types.ts`
- Test: `backend/tests/unit/test_import_preview_coordinator.py`
- Test: `backend/tests/contract/test_import_preview_api.py`
- Test: `frontend/src/features/recipes/__tests__/import-dialog.test.tsx`

**Interfaces:**
- `ImportConfirmRequest` carries `thumbnailCrop` and the preview origin kind.
- `JobAcceptedResponse` gains optional `coverStatus: "attached" | "not_selected" | "failed"`.
- `RecipePhotoService.attach_url(..., crop: ThumbnailCrop | None)` persists both media and focal metadata.

- [ ] Add failing tests proving a selected remote URL is attached, a PDF data URI is attached, crop metadata is persisted, and attachment failures return `coverStatus: "failed"` without failing recipe confirmation.
- [ ] Run the focused tests and verify they fail because URL imports are currently skipped and attachment status is discarded.
- [ ] Validate remote candidates against the stored preview image list; allow data URIs only for the selected preview thumbnail.
- [ ] Attach both `url` and `pdf_thumbnail` kinds, pass crop metadata, and return the result status while retaining idempotent confirm behavior.
- [ ] Set `originKind` to `web_import` or `cookbook_import` from the importer rather than inferring it in the UI.
- [ ] Show “Recipe added”, “Cover attached”, or “Recipe saved, but the cover needs another try” after confirmation.
- [ ] Run focused backend/frontend tests and commit `fix: persist imported covers with explicit attachment feedback`.

### Task 3: Make Recipe Job Progress Authoritative and Human-Readable

**Files:**
- Modify: `backend/src/cookfully/jobs/recipe_pipeline.py`
- Modify: `frontend/src/features/recipes/RecipeDetailPage.tsx`
- Modify: `frontend/src/features/recipes/RecipeNutritionSummary.tsx`
- Modify: `frontend/src/features/recipes/NutritionPanel.tsx`
- Create: `frontend/src/features/recipes/RecipeProcessingBanner.tsx`
- Modify: `frontend/src/components/index.tsx`
- Test: `backend/tests/integration/test_recipe_jobs.py`
- Test: `frontend/src/features/recipes/__tests__/recipe-ui.test.tsx`

**Interfaces:**
- Map job kinds to labels: `recipe_import`, `ingredient_parse`, `nutrition_match`, `nutrition_rollup`.
- `RecipeProcessingBanner` accepts the current job and recipe nutrition state and renders stage, progress, retry, failure, and completion copy.

- [ ] Add failing tests for progress updates during parse/match/rollup and for detail pages preferring `recipe.activeJob` over a stale terminal job.
- [ ] Run focused tests and verify the current implementation reports no recipe-stage progress and can display “Done” while another stage is active.
- [ ] Update pipeline loops to set bounded progress totals and current values without changing job chaining or stale-hash checks.
- [ ] Derive the displayed job from `recipe.activeJob ?? job.data ?? recoveredJob.data` and translate technical states into plain language.
- [ ] Add the processing banner near the hero and synchronize macro status, nutrition state, and detailed nutrition output.
- [ ] Run backend job tests, recipe UI tests, lint, and typecheck; commit `feat: explain recipe processing progress in the UI`.

### Task 4: Elevate Nutrition Into the Primary Recipe Experience

**Files:**
- Create: `frontend/src/features/recipes/RecipeNutritionOverview.tsx`
- Modify: `frontend/src/features/recipes/RecipeDetailPage.tsx`
- Modify: `frontend/src/features/recipes/NutritionPanel.tsx`
- Modify: `frontend/src/features/recipes/RecipeNutritionSummary.tsx`
- Modify: `frontend/src/styles/features.css`
- Test: `frontend/src/features/recipes/__tests__/recipe-ui.test.tsx`

- [ ] Add failing UI tests for always-visible nutrition, shared macro values, coverage bar, partial estimate copy, and review-match action.
- [ ] Replace the collapsed drawer with `RecipeNutritionOverview`, keeping technical evidence below the user-facing result.
- [ ] Render one macro data source for the hero summary and detailed overview; show the same basis and rounded values in both locations.
- [ ] Add status treatments for estimated, partial, manual, pending, stale, retrying, failed, and source-provided states.
- [ ] Ensure “Recalculate nutrition” immediately updates the cache to pending and shows the processing banner.
- [ ] Verify responsive layout at desktop and 390x844, then commit `feat: make recipe nutrition a primary user-facing section`.

### Task 5: Fix Delete Lifecycle and Add Immediate Organization Feedback

**Files:**
- Modify: `frontend/src/features/recipes/RecipeLibraryPage.tsx`
- Modify: `frontend/src/features/recipes/RecipeCard.tsx`
- Modify: `frontend/src/features/recipes/RecipeDetailPage.tsx`
- Modify: `frontend/src/features/recipes/RecipeOrganizationPanel.tsx`
- Modify: `frontend/src/features/recipes/RecipeCollectionManager.tsx`
- Modify: `frontend/src/styles/features.css`
- Test: `frontend/src/features/recipes/__tests__/recipe-ui.test.tsx`
- Test: `frontend/e2e/recipes.spec.ts`

- [ ] Add failing tests for delete error rendering, active-item removal, heart toggling, optimistic collection changes, and visible success feedback.
- [ ] Change active recipe removal to archive-first behavior; permanently delete only after the archived version is confirmed, and keep a recoverable archived state if the second step fails.
- [ ] Render `remove.error` separately from lifecycle errors and disable only the affected action while it is pending.
- [ ] Add always-visible heart controls and update recipe/detail/library caches optimistically with rollback.
- [ ] Replace the explicit organization save dependency with immediate mutation feedback while retaining a grouped save path where multiple edits are staged.
- [ ] Run focused unit/E2E tests and commit `fix: make recipe deletion and organization actions visible and reliable`.

### Task 6: Add Origin and Collection Discovery UI

**Files:**
- Modify: `frontend/src/features/recipes/RecipeLibraryPage.tsx`
- Modify: `frontend/src/features/recipes/RecipeCard.tsx`
- Modify: `frontend/src/features/recipes/RecipeDetailPage.tsx`
- Create: `frontend/src/features/recipes/RecipeCollectionStrip.tsx`
- Modify: `frontend/src/styles/features.css`
- Test: `frontend/src/features/recipes/__tests__/recipe-ui.test.tsx`
- Test: `frontend/e2e/recipes.spec.ts`

- [ ] Add failing tests for origin badges, collection chips, collection counts, unfiled filtering, and detail-page provenance.
- [ ] Add a visible collection strip with counts and an Unfiled entry; clicking an entry applies the existing collection filter.
- [ ] Render collection chips, origin badge, source host, meal roles, favorite state, and nutrition readiness on cards without creating an overloaded card.
- [ ] Show the same provenance and collection context on recipe details.
- [ ] Verify overflow and mobile wrapping at 390x844, then commit `feat: surface recipe provenance and collection context`.

### Task 7: Build the Reusable Thumbnail Crop Dialog

**Files:**
- Create: `frontend/src/features/recipes/ThumbnailCropDialog.tsx`
- Create: `frontend/src/features/recipes/thumbnailCrop.ts`
- Modify: `frontend/src/features/recipes/RecipeImportDialog.tsx`
- Modify: `frontend/src/features/recipes/RecipeEditorPage.tsx`
- Modify: `frontend/src/features/recipes/RecipeDraftPreview.tsx`
- Modify: `frontend/src/features/recipes/RecipeCard.tsx`
- Modify: `frontend/src/styles/features.css`
- Test: `frontend/src/features/recipes/__tests__/import-dialog.test.tsx`
- Test: `frontend/src/features/recipes/__tests__/recipe-ui.test.tsx`
- Test: `frontend/e2e/recipes.spec.ts`

**Interfaces:**
- `ThumbnailCrop` is `{ focalX: string; focalY: string; zoom: string }`.
- `ThumbnailCropDialog` accepts `imageSrc`, `value`, `onCancel`, and `onApply`.

- [ ] Add failing tests for centered defaults, apply/cancel behavior, zoom bounds, keyboard controls, and import/editor integration.
- [ ] Implement pure crop clamping helpers in `thumbnailCrop.ts` before adding pointer interaction.
- [ ] Implement a fixed 4:3 preview frame with drag gestures, range controls for focal X/Y/zoom, reset, cancel, and apply.
- [ ] Add the dialog after import thumbnail selection and after editor upload/source-photo selection.
- [ ] Pass crop metadata through import confirmation and editor save/photo endpoints.
- [ ] Apply focal point and zoom via CSS variables in cards and editor preview while keeping the original media intact.
- [ ] Run unit tests, E2E crop flows, accessibility checks, and mobile viewport checks; commit `feat: add focal-point recipe thumbnail cropping`.

### Task 8: Full Verification and Documentation

**Files:**
- Modify: `docs/inspiration-review.md`
- Modify: `AGENTS.md`
- Modify: `frontend/e2e/recipes.spec.ts`

- [ ] Add final E2E coverage for import cover persistence, crop preview, nutrition progress, collections, favorites, provenance, and deletion.
- [ ] Run:
  - `uv run --directory backend ruff format --check .`
  - `uv run --directory backend ruff check .`
  - `uv run --directory backend mypy src`
  - `COOKFULLY_DATABASE_URL=... uv run --directory backend pytest`
  - `pnpm --dir frontend lint`
  - `pnpm --dir frontend typecheck`
  - `pnpm --dir frontend test --run`
  - `pnpm --dir frontend build`
  - `pnpm --dir frontend exec playwright test`
- [ ] Record any pre-existing environment-only failures separately from regressions.
- [ ] Document the adopted Mealie/Tandoor/Immich comparisons for provenance, media persistence, and collection visibility.
- [ ] Update `AGENTS.md` with the instant-feedback, nutrition, organization, and crop behavior.
- [ ] Commit `docs: document instant feedback and thumbnail crop behavior`.

## Self-Review

- Import cover persistence is covered in Task 2 and final E2E verification.
- Human-readable processing is covered in Tasks 3 and 4.
- Nutrition synchronization is covered in Tasks 3 and 4.
- Delete and organization feedback is covered in Task 5.
- Collection grouping and provenance are covered in Task 6.
- Focal-point cropping is covered in Task 7, including import, editor, card rendering, and mobile behavior.
- No task relies on a placeholder implementation or an undefined interface.
- Exact decimal serialization is used for crop metadata, matching the existing contracts.
