# Cookfully Critique Fixes Design

Date: 2026-08-17
Status: Approved design

## Goal

Reduce cognitive load across the core Cookfully experience while preserving its editorial kitchen
utility direction. The first viewport of each major workflow should make one next action obvious,
keep food and cooking context ahead of nutrition evidence, and expose complexity progressively.

The change covers the critique findings for Recipe Library, Recipe Detail, Planner, nutrition
terminology, secondary-feature discoverability, accessibility semantics, mobile behavior, and
power-user efficiency. Existing routes and current product contracts remain the default boundary.

## Information Architecture

### Recipe Library

- Search remains the dominant discovery control.
- The page header has one primary `Add recipe` action and one secondary `Import recipe` action.
- Suggestions are a contextual `Get ideas` entry for empty or sparse results rather than a peer
  header action.
- Status views remain available, while sorting, grouping, collection selection, and favorite-only
  filtering stay behind `Refine recipes`.
- A selection mode supports bulk archive. Permanent deletion remains an individually confirmed
  action.

### Navigation

- Add `Ideas` to the secondary desktop navigation and the mobile `More` menu.
- Recipes, Plan, Grocery, and Pantry remain the primary kitchen destinations.
- Ideas is discoverable without competing with the primary cooking workflow.

### Recipe Detail

- `RecipeNutritionSummary` remains the only prominent nutrition result in the hero.
- The lower nutrition block becomes an evidence-oriented disclosure with coverage, provenance,
  assumptions, processing status, and ingredient matches.
- The evidence block must not repeat calories, protein, carbohydrate, or fat metrics.
- Existing serving scaling and review links remain available.

### Planner

- Week is the overview state, Day is the meal-editing state, and Prep is the execution state.
- Week and day navigation remain visible while planning.
- Empty meal slots retain one `Add a recipe` action each.
- Repeated per-slot suggestion links are removed.
- When a visible gap exists, one day-level `Suggest meals for open spots` action is shown.
- Nutrition guidance remains available in the day context but does not become another dashboard panel
  in the week overview.

### Terminology

Visible nutrition states use a stable vocabulary:

| Internal states | Visible label | Supporting meaning |
|---|---|---|
| estimated, source_provided, complete | Ready | The estimate is usable for planning. |
| partial, stale | Needs review | The recipe is usable, but some evidence needs attention. |
| pending, processing, retry_wait | Updating | Cookfully is still working on the estimate. |
| failed, unavailable | Unavailable | An estimate is not currently available. |
| manual | Manual | Values were supplied or corrected by the cook. |

Internal values remain unchanged for API compatibility and domain behavior.

## Components and Data Flow

### Shared presentation

- Add a shared nutrition-state formatter and evidence summary under
  `frontend/src/components/cookfully`.
- Recipe cards, Recipe Detail, Planner, and Suggestions use the same visible state labels.
- Preserve exact decimals and provenance in detail/editing surfaces while keeping discovery values
  rounded.

### Bulk archive API

Add an owner-scoped endpoint for archive actions:

```text
POST /api/v1/recipes/bulk/archive
```

Request:

```json
{
  "recipes": [
    {"id": "recipe-id", "version": 4}
  ]
}
```

Response returns one outcome per requested recipe, including success, stale-version conflict, or
other failure. The operation is idempotent for already archived recipes and never bypasses owner
authorization or optimistic concurrency checks. Permanent deletion is not included in bulk actions.

The frontend selects recipes, submits versioned items, removes successful active recipes
optimistically, and restores failed items with an inline explanation. Partial success is retained;
the user does not need to repeat successful work.

### Planner and Suggestions

No new planner endpoint is required for the first pass. The frontend derives open meal gaps from the
authoritative loaded plan and links the existing Suggestions workflow with the selected date/week
context. Suggestions remain contextual rather than becoming a second planning dashboard.

## Accessibility and Interaction

- Recipe Library and Planner tablists use explicit `aria-controls` and matching `tabpanel` regions.
- Day tabs retain roving tabindex and arrow-key navigation.
- Recipe cards expose one keyboard destination for the primary card content; favorite and menu
  controls remain separate, named controls.
- All bulk-selection controls have accessible labels, selected counts, and disabled/loading states.
- Bulk results use inline status and alert regions with plain-language recovery actions.
- Existing dialog focus trap, Escape handling, and focus restoration remain intact.
- Verify keyboard flow, visible focus, 200% zoom reflow, and no document-level horizontal overflow.

## Visual Direction

- Preserve the existing Afacad Flux / Inclusive Sans pairing, OKLCH tokens, herb/saffron palette,
  food imagery, and editorial asymmetry.
- Remove decorative navigation gradients and stripe-like accents that compete with content.
- Replace uppercase import headings with sentence case.
- Do not introduce new generic cards, glass surfaces, gradient text, metric rings, or dashboard grids.
- Keep mobile as a cooking context, not a shrunken desktop layout.

## Error and Edge States

- Bulk archive handles empty selection, already archived recipes, stale versions, network failure,
  partial success, retry, and an archived-only library.
- Nutrition presentation retains explicit loading, empty, partial, estimated, manual, corrected,
  stale, failed, and unavailable states.
- A failed nutrition update never removes recipe content or prevents cooking.
- Existing permanent-delete confirmation remains the only destructive blocking dialog.
- Long recipe titles, missing images, sparse search results, and long collection names must reflow
  without overflow.

## Verification

### Frontend

- Unit tests cover shared nutrition labels, evidence-only rendering, library selection, partial bulk
  results, empty/sparse suggestion entry, card keyboard destinations, and tab semantics.
- Playwright tests cover Recipe Library, Recipe Detail, Planner, mobile More navigation, and keyboard
  interactions at `1440x900` and `390x844`.

### Backend

- Contract tests cover request validation, owner isolation, stale versions, partial outcomes, and
  idempotent archive behavior.
- Service tests cover successful, conflicting, missing, and already archived recipes.

### Commands

```text
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
pnpm --dir frontend exec playwright test
uv run --directory backend ruff check .
uv run --directory backend mypy src
uv run --directory backend pytest
```

## Acceptance Criteria

1. Recipe Library has one dominant discovery action and supports reversible, partially successful
   bulk archive.
2. Recipe Detail presents nutrition metrics once; deeper evidence is progressive disclosure.
3. Planner communicates Week → Day → Prep without repeated suggestion actions in every meal slot.
4. Nutrition labels are consistent across discovery, detail, planning, and suggestions.
5. Ideas is discoverable through secondary navigation and contextual planning gaps.
6. Recipe cards and tablists are keyboard-efficient and screen-reader coherent.
7. The interface remains coherent at desktop and 390px mobile sizes with no horizontal overflow.
8. Existing API/domain behavior remains intact except for the version-guarded bulk archive endpoint.
