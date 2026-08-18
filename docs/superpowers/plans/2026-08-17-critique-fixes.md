# Cookfully Critique Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce cognitive load across Recipes, Recipe Detail, Planner, and Suggestions while adding version-safe bulk archive and preserving Cookfully's food-first visual language.

**Architecture:** Keep the existing route and query architecture. Add one small owner-scoped bulk archive API with per-item outcomes, a shared frontend nutrition-state formatter, an evidence-only nutrition disclosure, and focused UI state for library selection and planner suggestions. Existing suggestions, meal-plan, archive, restore, and delete APIs remain authoritative.

**Tech Stack:** FastAPI, Pydantic 2, SQLAlchemy 2, React 19.2, TypeScript 5.x, TanStack Query, React Testing Library, Vitest, Playwright, openapi-typescript.

## Global Constraints

- Preserve original ingredient text, nutrition provenance, serving basis, and active correction precedence.
- Preserve internal nutrition state values for API and domain compatibility; only visible labels change.
- Keep all recipe mutations owner-scoped and version-guarded.
- Use Cookfully's existing Afacad Flux / Inclusive Sans fonts, OKLCH tokens, herb/saffron palette, and food-first imagery.
- Do not add gradient text, decorative glass, side-stripe accents, generic card grids, metric rings, or pervasive uppercase labels.
- Verify `1440x900` desktop and `390x844` mobile behavior, keyboard access, visible focus, 200% zoom reflow, and no document-level horizontal overflow.
- Do not modify unrelated worktree changes in reference-data files, `problems.txt`, or the existing recipe-library-density work.
- Do not commit unless explicitly requested.

---

## File Map

### Backend API

- Modify `specs/001-nutrition-recipe-planner/contracts/openapi.yaml` to define the bulk archive request and per-item response.
- Modify `backend/src/cookfully/api/schemas/recipes.py` with Pydantic request/result models.
- Modify `backend/src/cookfully/application/recipes.py` with version-safe per-item bulk archive behavior.
- Modify `backend/src/cookfully/api/routes/recipes.py` with the owner-protected endpoint.
- Regenerate `frontend/src/app/api/generated/schema.ts` using `scripts/generate-api-client.ps1`.
- Test `backend/tests/contract/test_recipe_api.py` and `backend/tests/integration/test_recipe_application.py`.

### Shared frontend presentation

- Create `frontend/src/components/cookfully/nutritionState.ts` for pure visible-state mapping.
- Create `frontend/src/components/cookfully/__tests__/nutritionState.test.ts` for the mapping contract.
- Modify `frontend/src/components/index.tsx` only if the shared formatter needs a public component export.
- Modify `frontend/src/features/recipes/RecipeCard.tsx` to use shared labels and expose selection mode.
- Modify `frontend/src/features/recipes/RecipeNutritionSummary.tsx` to use shared labels.
- Delete `frontend/src/features/recipes/RecipeNutritionOverview.tsx` after its duplicate metric block is removed.
- Modify `frontend/src/features/recipes/RecipeDetailPage.tsx` to keep one metric result and enrich the existing evidence disclosure.
- Modify `frontend/src/features/recipes/NutritionPanel.tsx` if its visible states use old vocabulary.
- Modify `frontend/src/features/suggestions/SuggestionPage.tsx` only where visible nutrition state labels are duplicated.

### Recipe Library

- Modify `frontend/src/features/recipes/api.ts` with `recipesApi.bulkArchive`.
- Modify `frontend/src/features/recipes/types.ts` with generated bulk-archive aliases.
- Modify `frontend/src/features/recipes/RecipeLibraryPage.tsx` for header hierarchy, selection state, optimistic bulk mutation, sparse-result ideas, and tab semantics.
- Create `frontend/src/features/recipes/BulkRecipeActions.tsx` for the selected-count action bar and partial-result feedback.
- Modify `frontend/src/features/recipes/RecipeCard.tsx` so the primary card content has one keyboard destination and selection controls are named.
- Modify `frontend/src/styles/features.css` for selection mode, action-bar layout, evidence presentation, and responsive behavior.
- Modify `frontend/src/features/recipes/__tests__/recipe-ui.test.tsx` and add focused library tests if the existing file becomes too broad.

### Planner and navigation

- Modify `frontend/src/app/App.tsx` to add `Ideas` to secondary desktop navigation and mobile More.
- Modify `frontend/src/features/plans/WeeklyPlannerPage.tsx` to remove repeated per-slot idea links, add one day-level open-gap action, and complete tab semantics.
- Modify `frontend/src/styles/features.css` for the revised planner toolbar/day-level action layout.
- Modify `frontend/src/features/plans/__tests__/planning-ui.test.tsx` for the new action count, labels, and ARIA relationships.
- Modify `frontend/e2e/recipes.spec.ts` and the relevant planner e2e spec to cover mocked bulk archive, navigation, and responsive states.

### Visual and accessibility cleanup

- Modify `frontend/src/styles/shell.css` to remove the decorative navigation gradient/stripe treatment without changing the rail geometry.
- Modify `frontend/src/styles/features.css` to replace uppercase import headings with sentence case and remove any critique-identified stripe-like decorative treatment.
- Modify `frontend/src/features/recipes/RecipeLibraryPage.tsx` and `WeeklyPlannerPage.tsx` with explicit tab/tabpanel IDs.
- Modify `frontend/src/features/recipes/__tests__/recipe-ui.test.tsx` and `frontend/src/features/plans/__tests__/planning-ui.test.tsx` for keyboard and screen-reader semantics.

---

## Task 1: Add the Bulk Archive Contract and Service

**Files:**
- Modify: `specs/001-nutrition-recipe-planner/contracts/openapi.yaml`
- Modify: `backend/src/cookfully/api/schemas/recipes.py`
- Modify: `backend/src/cookfully/application/recipes.py`
- Modify: `backend/src/cookfully/api/routes/recipes.py`
- Regenerate: `frontend/src/app/api/generated/schema.ts`
- Test: `backend/tests/contract/test_recipe_api.py`
- Test: `backend/tests/integration/test_recipe_application.py`

**Interfaces:**
- Request JSON: `{ "recipes": [{ "id": "uuid", "version": 1 }] }`.
- Response JSON: `{ "results": [{ "id": "uuid", "status": "archived|already_archived|failed", "version": 2|null, "code": "string|null", "message": "string|null" }] }`.
- Service method: `RecipeService.bulk_archive(items: Sequence[tuple[UUID, int]]) -> tuple[BulkArchiveResult, ...]`.

- [x] **Step 1: Add the failing contract test.**

Add a contract test that creates two recipes, sends one valid and one stale version, and asserts a
`200` response with two independent outcomes. Also assert the OpenAPI document contains
`/api/v1/recipes/bulk/archive` and the request/response schemas.

```python
updated = client.patch(
    f"/api/v1/recipes/{second_id}",
    json=recipe_payload("Second recipe updated"),
    headers={**headers, "If-Match": '"1"'},
)
assert updated.status_code == 200
assert updated.json()["version"] == 2

response = client.post(
    "/api/v1/recipes/bulk/archive",
    json={"recipes": [{"id": first_id, "version": 1}, {"id": second_id, "version": 1}]},
    headers=headers,
)
assert response.status_code == 200
assert response.json()["results"] == [
    {"id": first_id, "status": "archived", "version": 2, "code": None, "message": None},
    {"id": second_id, "status": "failed", "version": None, "code": "stale_version", "message": "The recipe changed before it could be archived."},
]
```

- [x] **Step 2: Run the focused contract test and verify it fails.**

Run: `uv run --directory backend pytest tests/contract/test_recipe_api.py -k bulk_archive -q`

Expected: FAIL because the path and response models do not exist.

- [x] **Step 3: Define the OpenAPI and Pydantic models.**

Add these source-owned models in `backend/src/cookfully/api/schemas/recipes.py`:

```python
class RecipeBulkArchiveItem(ApiModel):
    id: UUID
    version: int = Field(ge=1)


class RecipeBulkArchiveRequest(ApiModel):
    recipes: tuple[RecipeBulkArchiveItem, ...] = Field(min_length=1, max_length=100)


class RecipeBulkArchiveResult(ApiModel):
    id: UUID
    status: Literal["archived", "already_archived", "failed"]
    version: int | None = Field(default=None, ge=1)
    code: str | None = None
    message: str | None = None


class RecipeBulkArchiveResponse(ApiModel):
    results: tuple[RecipeBulkArchiveResult, ...]
```

Add the matching `components.schemas` and `POST /recipes/bulk/archive` operation to the OpenAPI
contract. The operation uses a `200` response, `require_browser_owner`, and does not accept a
single `If-Match` header because each item carries its own version.

- [x] **Step 4: Implement version-safe per-item service behavior.**

Add `Literal` to the existing `typing` imports and add this application result type in
`backend/src/cookfully/application/recipes.py`:

```python
@dataclass(frozen=True, slots=True)
class BulkArchiveResult:
    recipe_id: UUID
    status: Literal["archived", "already_archived", "failed"]
    version: int | None = None
    code: str | None = None
    message: str | None = None
```

Extract the current archive mutation in `RecipeService` into a private transaction helper that
returns `(recipe, already_archived)` and accepts `allow_already_archived: bool`. Keep the existing
single-recipe `archive()` behavior unchanged by passing `False`. Implement `bulk_archive()` by
processing each `(recipe_id, expected_version)` in its own transaction, catching `DomainError` per
item and converting it to a failed result. When the recipe is already archived and the supplied
version matches, return `already_archived` without incrementing the version. Missing recipes return
`recipe_not_found`; stale versions return `stale_version`; invalid archive states return their
existing domain code.

- [x] **Step 5: Implement the route.**

Register this route before the dynamic single-recipe operations:

```python
@router.post(
    "/bulk/archive",
    response_model=RecipeBulkArchiveResponse,
    response_model_by_alias=True,
)
def bulk_archive_recipes(
    payload: RecipeBulkArchiveRequest,
    recipes: Annotated[RecipeService, Depends(recipe_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> RecipeBulkArchiveResponse:
    del owner
    results = recipes.bulk_archive(tuple((item.id, item.version) for item in payload.recipes))
    return RecipeBulkArchiveResponse(
        results=tuple(
            RecipeBulkArchiveResult(
                id=result.recipe_id,
                status=result.status,
                version=result.version,
                code=result.code,
                message=result.message,
            )
            for result in results
        )
    )
```

Use the existing domain error-to-problem middleware behavior for malformed requests and preserve
owner authentication through the dependency.

- [x] **Step 6: Regenerate the frontend schema and run backend tests.**

Run: `powershell -ExecutionPolicy Bypass -File scripts/generate-api-client.ps1`

Expected: `frontend/src/app/api/generated/schema.ts` contains the new path and schemas.

Run: `uv run --directory backend pytest tests/contract/test_recipe_api.py -k "bulk_archive or archive_restore" tests/integration/test_recipe_application.py -q`

Expected: PASS.

## Task 2: Create Shared Nutrition-State Presentation

**Files:**
- Create: `frontend/src/components/cookfully/nutritionState.ts`
- Create: `frontend/src/components/cookfully/__tests__/nutritionState.test.ts`
- Modify: `frontend/src/features/recipes/RecipeCard.tsx`
- Modify: `frontend/src/features/recipes/RecipeNutritionSummary.tsx`
- Modify: `frontend/src/features/recipes/NutritionPanel.tsx`
- Modify: `frontend/src/features/suggestions/SuggestionPage.tsx` if old state labels are present

**Interfaces:**
- `nutritionPresentation(nutritionState: string, nutritionStatus?: string | null): NutritionPresentation`.
- `NutritionPresentation = { key: "ready" | "needs_review" | "updating" | "unavailable" | "manual"; label: string; description: string }`.

- [x] **Step 1: Add mapping tests first.**

Test lifecycle precedence and every visible label:

```ts
expect(nutritionPresentation("estimated")).toMatchObject({ key: "ready", label: "Ready" });
expect(nutritionPresentation("stale", "manual")).toMatchObject({ key: "needs_review", label: "Needs review" });
expect(nutritionPresentation("pending")).toMatchObject({ key: "updating", label: "Updating" });
expect(nutritionPresentation("failed")).toMatchObject({ key: "unavailable", label: "Unavailable" });
expect(nutritionPresentation("estimated", "manual")).toMatchObject({ key: "manual", label: "Manual" });
```

- [x] **Step 2: Run the new test to verify it fails.**

Run: `pnpm --dir frontend test --run src/components/cookfully/__tests__/nutritionState.test.ts`

Expected: FAIL because the formatter does not exist.

- [x] **Step 3: Implement the pure formatter.**

Use lifecycle precedence in this order: `stale`/`partial` → `Needs review`, `pending`/`processing`/
`retry_wait` → `Updating`, `failed`/`unavailable` → `Unavailable`, manual nutrition status →
`Manual`, and `estimated`/`source_provided`/unknown usable values → `Ready`. Return a short
description suitable for an accessible status explanation.

- [x] **Step 4: Replace duplicated visible mappings.**

Remove `STATE_LABELS` from `RecipeCard`, remove nested `stateLabel` logic from
`RecipeNutritionSummary`, and replace any equivalent visible mapping in `NutritionPanel` and
Suggestions. Keep raw classes based on `presentation.key`, not backend strings, so CSS state styles
remain stable.

- [x] **Step 5: Run focused frontend tests.**

Run: `pnpm --dir frontend test --run src/components/cookfully/__tests__/nutritionState.test.ts src/features/recipes/__tests__/recipe-ui.test.tsx src/features/suggestions/__tests__/suggestion-ui.test.tsx`

Expected: PASS after updating assertions from `Estimated`, `Outdated`, and `Partial estimate` to
the approved vocabulary where the state is visible.

## Task 3: Remove Duplicate Recipe Nutrition and Improve Evidence Disclosure

**Files:**
- Modify: `frontend/src/features/recipes/RecipeDetailPage.tsx`
- Delete: `frontend/src/features/recipes/RecipeNutritionOverview.tsx`
- Modify: `frontend/src/features/recipes/NutritionPanel.tsx`
- Modify: `frontend/src/styles/features.css`
- Test: `frontend/src/features/recipes/__tests__/recipe-ui.test.tsx`

**Interfaces:**
- The detail page continues to receive `RecipeDetail` and `Job` unchanged.
- The existing `details#nutrition-details` becomes the only lower nutrition presentation.

- [x] **Step 1: Add the failing duplicate-prevention test.**

In the existing detail test, assert that the recipe title renders one prominent nutrition heading,
that the four metric labels occur only once, and that the evidence disclosure contains coverage,
provenance, and the ingredient-match review link.

```ts
expect(screen.getAllByText("Calories")).toHaveLength(1);
expect(screen.getAllByText("Protein")).toHaveLength(1);
expect(screen.getByText("Nutrition details and evidence")).toBeVisible();
expect(screen.getByText(/ingredient coverage/i)).toBeVisible();
```

- [x] **Step 2: Run the detail test to verify it fails.**

Run: `pnpm --dir frontend test --run src/features/recipes/__tests__/recipe-ui.test.tsx -t "nutrition|detail"`

Expected: FAIL because the hero summary and overview both render the same metrics.

- [x] **Step 3: Remove the duplicate overview block.**

Delete the `RecipeNutritionOverview` import and JSX from `RecipeDetailPage`. Delete the now-unused
component file. Keep the hero `RecipeNutritionSummary` and the existing lower `details` drawer.

- [x] **Step 4: Make the drawer evidence-first.**

Add a compact evidence summary inside `#nutrition-details` with the shared state label, integer
ingredient coverage, source/provenance summary, and existing match-review action. Keep detailed
micronutrients and assumptions in `NutritionPanel` below the disclosure. Do not render calories,
protein, carbohydrate, or fat in this lower block.

- [x] **Step 5: Update evidence styles without adding a card stack.**

Use the existing border-block/disclosure tokens and spacing. Remove any metric-grid rules that are
only used by `RecipeNutritionOverview`; keep the hero summary metric styles. Ensure the evidence
content wraps at 390px and does not use a colored side stripe.

- [x] **Step 6: Run the focused detail tests.**

Run: `pnpm --dir frontend test --run src/features/recipes/__tests__/recipe-ui.test.tsx`

Expected: PASS with exactly one prominent nutrition metric set.

## Task 4: Recompose Recipe Library and Add Bulk Selection

**Files:**
- Modify: `frontend/src/features/recipes/api.ts`
- Modify: `frontend/src/features/recipes/types.ts`
- Create: `frontend/src/features/recipes/BulkRecipeActions.tsx`
- Modify: `frontend/src/features/recipes/RecipeLibraryPage.tsx`
- Modify: `frontend/src/features/recipes/RecipeCard.tsx`
- Modify: `frontend/src/styles/features.css`
- Test: `frontend/src/features/recipes/__tests__/recipe-ui.test.tsx`

**Interfaces:**
- `export type BulkArchiveResponse = components["schemas"]["RecipeBulkArchiveResponse"]` in `frontend/src/features/recipes/types.ts`.
- `recipesApi.bulkArchive(items: Array<{ id: string; version: number }>): Promise<BulkArchiveResponse>`.
- `BulkRecipeActions({ selectedCount, pending, onArchive, onClear })` renders selection count,
  `Archive selected`, and `Clear selection` controls.
- `RecipeCard` receives `selectionMode`, `selected`, and `onSelectedChange` in addition to existing
  lifecycle callbacks.

- [x] **Step 1: Add API and component behavior tests.**

Cover the generated request path/body, selection toggles, selected count, empty selection disabled
state, successful removal, stale per-item failure, and partial success message.

```ts
expect(fetchMock).toHaveBeenCalledWith(
  "/api/v1/recipes/bulk/archive",
  expect.objectContaining({
    method: "POST",
    body: JSON.stringify({ recipes: [{ id: recipe.id, version: recipe.version }] }),
  }),
);
expect(screen.getByRole("button", { name: "Archive 1 selected recipe" })).toBeEnabled();
```

- [x] **Step 2: Run the focused tests to verify they fail.**

Run: `pnpm --dir frontend test --run src/features/recipes/__tests__/recipe-ui.test.tsx -t "bulk|selection"`

Expected: FAIL because the API method and selection UI do not exist.

- [x] **Step 3: Add the typed API method.**

Use the local `BulkArchiveResponse` alias backed by the generated `RecipeBulkArchiveResponse` schema
and the existing `apiRequest`:

```ts
bulkArchive(items: Array<{ id: string; version: number }>) {
  return apiRequest<BulkArchiveResponse>("/recipes/bulk/archive", {
    method: "POST",
    body: JSON.stringify({ recipes: items }),
  });
}
```

- [x] **Step 4: Add library selection state and optimistic mutation.**

Track selected recipe IDs in a `Set<string>`-equivalent state. Build the request from the current
recipe versions. On mutation start, remove selected active recipes from the visible query result.
On response, keep successful/already-archived outcomes removed, restore failed items from the query
snapshot, clear only successful selections, and render an inline status with the failed recipe
title/code. On network failure, restore the complete snapshot and offer `Try archive again`.

- [x] **Step 5: Recompose the header and discovery controls.**

Use `Add recipe` as the single primary header button, `Import recipe` as secondary, and remove the
peer `Give me ideas` header button. Show `Get ideas` in the empty state and when a non-empty search
returns no more than two results. Keep four status tabs, but place sorting, grouping, collection,
and favorites under `Refine recipes`.

- [x] **Step 6: Make card navigation keyboard-efficient.**

Keep one link around the primary media/title/metadata content, or make the media decorative and keep
the title link as the sole primary destination. Keep favorite, menu, and selection controls outside
that link with explicit accessible names. Selection mode must expose a checkbox labelled
`Select <recipe title>` and never rely on hover.

- [x] **Step 7: Add explicit tab/tabpanel semantics.**

Give each status tab a stable ID such as `recipe-view-tab-all` and `aria-controls` pointing to
`recipe-view-panel`. Give the displayed recipe section `role="tabpanel"`, `id="recipe-view-panel"`,
and `aria-labelledby` pointing to the active tab. Preserve the existing filter disclosure and
active-filter clear behavior.

- [x] **Step 8: Style selection and responsive states.**

Use a quiet surface and one-pixel boundary for selected cards, a compact action bar above the grid,
and a stacked mobile action bar. Do not add nested cards, bright status stripes, or a second primary
color. Ensure long titles and collection labels wrap.

- [x] **Step 9: Run Recipe Library tests.**

Run: `pnpm --dir frontend test --run src/features/recipes/__tests__/recipe-ui.test.tsx`

Expected: PASS, including existing archive/restore/menu/favorite behavior and the new selection flow.

## Task 5: Clarify Planner Flow and Discover Ideas

**Files:**
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/features/plans/WeeklyPlannerPage.tsx`
- Modify: `frontend/src/styles/features.css`
- Test: `frontend/src/features/plans/__tests__/planning-ui.test.tsx`
- Test: `frontend/src/features/suggestions/__tests__/suggestion-ui.test.tsx`

**Interfaces:**
- Existing Suggestions route accepts `scope=day&localDate=<date>` and requires no API change.
- Planner derives `openSlots = SLOTS.filter(slot => !selectedEntries.some(entry => entry.mealSlot === slot))`.

- [x] **Step 1: Add failing planner tests.**

Assert that the day view has no repeated `Find an idea` links, has at most one
`Suggest meals for open spots` link when an open slot exists, and exposes matching tab/tabpanel
relationships.

```ts
expect(screen.queryAllByRole("link", { name: /find an idea/i })).toHaveLength(0);
expect(screen.getByRole("link", { name: "Suggest meals for open spots" })).toHaveAttribute(
  "href",
  "/app/suggestions?scope=day&localDate=2026-03-11",
);
expect(screen.getByRole("tab", { name: "Day" })).toHaveAttribute("aria-controls", "planner-panel-day");
```

- [x] **Step 2: Run the planner tests to verify they fail.**

Run: `pnpm --dir frontend test --run src/features/plans/__tests__/planning-ui.test.tsx -t "suggest|tabpanel"`

Expected: FAIL because the current day view renders per-slot idea links and incomplete tab wiring.

- [x] **Step 3: Add Ideas navigation.**

Import `Sparkles` in `App.tsx` and add `{ to: "/app/suggestions", label: "Ideas", Icon: Sparkles }`
to `SECONDARY_NAVIGATION`. The existing desktop and mobile loops will then expose the same named
destination, and the current `moreIsActive` calculation will mark it active.

- [x] **Step 4: Make the planner tabs explicit.**

Assign IDs `planner-tab-week`, `planner-tab-day`, and `planner-tab-prep`; add matching
`aria-controls`; render the active view inside `role="tabpanel"` with IDs
`planner-panel-week`, `planner-panel-day`, and `planner-panel-prep`. Preserve the week/day controls
inside their active panel so navigation remains visible.

- [x] **Step 5: Replace repeated idea links with one day-level action.**

Remove the `Find an idea` link from each empty meal slot. Compute open slots from `SLOTS` and
`selectedEntries`; when `goal.data` exists and `openSlots.length > 0`, render one link after the
meal-slot list with `scope=day` and the selected date. Keep each empty slot's single `Add a recipe`
button and retain the existing `Help fill this week` action only in Week view.

- [x] **Step 6: Adjust planner hierarchy styles.**

Keep Week/Day/Prep as one segmented control, move the day-level suggestion link into the day header
or a quiet gap-action region, and avoid adding another nutrition card to Week. At mobile width,
stack the toolbar and keep the suggestion action within the thumb-friendly content flow.

- [x] **Step 7: Run planner and suggestions tests.**

Run: `pnpm --dir frontend test --run src/features/plans/__tests__/planning-ui.test.tsx src/features/suggestions/__tests__/suggestion-ui.test.tsx`

Expected: PASS with existing week/day/prep mutations and suggestion query-string behavior intact.

## Task 6: Apply Visual and Copy Cleanup

**Files:**
- Modify: `frontend/src/styles/shell.css`
- Modify: `frontend/src/styles/features.css`
- Modify: `frontend/src/features/recipes/RecipeLibraryPage.tsx`
- Modify: `frontend/src/features/recipes/RecipeCard.tsx`
- Modify: `frontend/src/features/recipes/RecipeNutritionSummary.tsx`
- Modify: `frontend/src/features/recipes/RecipeDetailPage.tsx`

- [x] **Step 1: Remove the shell navigation decoration.**

Delete `.planner-nav::after` from `shell.css`. Preserve the rail background, active link surface,
focus ring, and spacing; the active state remains communicated by color and surface contrast rather
than a stripe.

- [x] **Step 2: Replace uppercase feature headings.**

Change import wizard heading text and CSS from uppercase treatment to sentence case. Keep short
eyebrow labels in their existing tokenized style, but do not add `text-transform: uppercase` to new
content.

- [x] **Step 3: Normalize microcopy.**

Use `Needs review` instead of `Outdated`, `Partial estimate`, and `Estimate needs refreshing` where
the user is deciding what to do. Use `Updating` for active work and `Unavailable` for failed work.
Change `Next day` to `Copy to next day`. Replace operational recovery guidance such as `check
service health` with `Try again. If it keeps happening, your recipes are safe.`

- [x] **Step 4: Run markup and style searches.**

Run: `rg -n "text-transform:\s*uppercase|Outdated|Partial estimate|Estimate needs refreshing|Find an idea|border-left:\s*[^1]" frontend/src`

Expected: no user-facing nutrition labels or import headings match; remaining one-pixel structural
borders are documented by their layout role and no decorative side stripe remains.

## Task 7: Expand End-to-End Coverage and Verify the Whole Change

**Files:**
- Modify: `frontend/e2e/recipes.spec.ts`
- Modify: `frontend/e2e/meal-planning.spec.ts` or the existing planner spec file used by the suite.
- Modify: `frontend/e2e/responsive.spec.ts` if the shared responsive assertions belong there.
- Modify: `frontend/e2e/accessibility.spec.ts` for tab and selection semantics.

- [x] **Step 1: Extend recipe mocks for bulk archive.**

In the existing `mockApi` helper, handle `POST /api/v1/recipes/bulk/archive` with one successful
outcome and an optional stale outcome. Keep the mocked recipe version in the response and verify the
library removes only successful items.

- [x] **Step 2: Add desktop Recipe Library coverage.**

At `1440x900`, verify search is visible before refinement, header actions are `Add recipe` and
`Import recipe`, `Get ideas` is not a peer header action, selecting two cards shows one bulk action
bar, and a partial bulk response reports the failed title without restoring successful items.

- [x] **Step 3: Add Recipe Detail coverage.**

Verify the hero contains one set of four nutrition metrics, the evidence disclosure is collapsed by
default, and opening it exposes coverage/provenance/review content without a second metric set.

- [x] **Step 4: Add Planner and navigation coverage.**

Verify Ideas appears in desktop secondary navigation and mobile More, the day view has one
day-level suggestion action for open slots, and each planner tab points to the active panel.

- [x] **Step 5: Add responsive and accessibility coverage.**

At `390x844`, verify no document-level horizontal overflow, selection actions stack, long recipe
titles wrap, mobile More remains usable, and primary touch targets remain at least 44px. Use axe
checks already established by the suite plus explicit tab/tabpanel assertions.

- [x] **Step 6: Run the complete verification sequence.**

Run:

```text
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
pnpm --dir frontend exec playwright test
uv run --directory backend ruff format --check .
uv run --directory backend ruff check .
uv run --directory backend mypy src
uv run --directory backend pytest
```

Expected: all commands exit `0`. If generated OpenAPI output changes beyond the new bulk endpoint,
inspect the diff and correct the contract source rather than hand-editing generated TypeScript.

**Execution note (2026-08-17):** The frontend five commands exit `0` (`playwright test`: 83 passed,
1 skipped). The backend four do not exit `0`, but every remaining failure is pre-existing and outside
this change's scope: `ruff format --check` and `ruff check .` are already non-clean at HEAD (format
drift in `api/routes/recipes.py` present in HEAD; pre-existing E501 in
`migrations/versions/0021_semantic_matching.py`); `mypy src` reports a pre-existing error in
`src/cookfully/jobs/recipe_pipeline.py:486`; `pytest` has 8 pre-existing failures + 1 pre-existing
error (2× `test_import_preview_api.py`, 3× `test_owner_erasure.py`, 4×
`test_provider_degraded_workflows.py` where `import_failed` behavior exists in HEAD, and a
`test_migration_drift.py` error caused by the untracked semantic-matching migration). The new bulk
archive, OpenAPI drift, and all changed-file ruff/mypy checks pass.

**Schema regeneration note (2026-08-17):** `scripts/generate-api-client.ps1` generates from
`specs/001-nutrition-recipe-planner/contracts/openapi.yaml`, which is stale vs the running app (it
emits `Recipe`/`MealPlan` names while the app emits `RecipeResponse`/`MealPlanResponse`, and it lacks
grocery/pantry/plans/foods/reference-data components). Using it clobbered the committed schema and
broke typecheck. The correct source of truth is the worktree app itself; `frontend/src/app/api/generated/schema.ts`
was regenerated from `create_app().openapi()`. The script/contract mismatch remains an open follow-up.

## Plan Self-Review

- Spec coverage: bulk archive is Task 1; shared terminology is Task 2; duplicate nutrition is Task 3;
  Recipe Library hierarchy and power-user selection are Task 4; Planner and Ideas discoverability are
  Task 5; visual/copy cleanup is Task 6; responsive, keyboard, and state verification are Task 7.
- Placeholder scan: no incomplete markers or unspecified implementation steps are used.
- Type consistency: the API response name is `RecipeBulkArchiveResponse` in Python and generated
  `BulkArchiveResponse` in TypeScript; the frontend method consumes `Array<{ id: string; version: number }>`
  and returns that generated response. The shared formatter returns `NutritionPresentation` and all
  consumers use its `key`, `label`, and `description` fields.
- Scope check: backend bulk archive, shared nutrition presentation, Recipe Library, Recipe Detail,
  Planner, navigation, and tests are one coherent usability pass; no unrelated product subsystem is
  included.
