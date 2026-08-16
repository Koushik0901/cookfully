# Import Preview, Missing Quantities, Duplicates, and PDF Images — Design

Feature: Phase 3 of the 11-issue product-improvement pass. Addresses issues #3, #4, #8, #9, #11 from `problems.txt`.
Date: 2026-08-16.

## Problem

- **#4** Users cannot preview an imported recipe (title, ingredients, instructions, components, thumbnail) before it lands in their collection, nor edit that content in the flow.
- **#3** Imported recipes frequently omit quantities; today the user only discovers this after import on the detail page with no guided prompt.
- **#8** Multi-component imports must surface each component separately in the preview so the user can inspect/edit/remove parts before finalizing.
- **#9** Duplicate imports add clutter; the app does not warn when an existing recipe matches.
- **#11** PDF cookbooks do not reliably parse embedded recipe images.

## Current Behavior

`POST /api/v1/recipes/import` (with an idempotency key) fetches the URL, creates a placeholder recipe
(no content yet), and enqueues a background job. The frontend immediately navigates to the detail page
and polls the job until nutrition/content is ready. There is no pre-save preview, no edit-before-save,
and no duplicate check. Images are auto-selected once when there is exactly one candidate; multiple
candidates produce no image (arbitrary silent choice avoided).

## Goals

- Let the user see and edit an import's title, components (each with ingredients + instructions),
  per-ingredient quantities, and chosen thumbnail **before** it is saved.
- Prompt explicitly for ingredients that parse without a quantity, while keeping it non-blocking.
- Detect near-duplicate existing recipes and offer keep / discard / open-existing.
- Extract images from PDF cookbooks and present them alongside the HTML image candidates.

## Approach

### Backend — "parse first, confirm after"

Two endpoints (both behind browser `idempotency`-style scoping but distinct):

1. **`POST /api/v1/recipes/import/preview`** (`Pre importPreviewRequest{ url }` → `ImportPreviewResponse`)
   - Synchronously fetches + parses with the existing `RecipeImporter` (reuses `ImportedRecipe` /
     `ImportedCookbook`, section mapping, image candidate logic).
   - Returns an **unsaved** structured preview: `title`, `yieldQuantity`, `yieldText`, `imageCandidates[]`,
     and `sections[]` (each `{ title?, ingredients[], instructions[] }`). No nutrition matching, no
     persistence, no thumbnail download.
   - Returns `parseId` (scoped to the owner, short TTL) used by the confirm step. A cookbook PDF
     produces multiple component **titles** but still one confirm; each recognized recipe is a section.
   - On timeout or transport failure, returns a **fallback response** (`{ fallback: true }`) signaling the
     client to use the legacy direct-import path (current behavior).
   - Synchronous parse is bounded (client timeout ~8s). No scope creep into PDF multi-recipe splitting.
2. **POST `/recipes/import`** (confirm) — extended payload `ImportConfirmRequest`:
   - `parseId`, plus optional edits: `title`, `imageIndex` (into preview candidates), `yieldQuantity`,
     `components[]` where each overrides with `title`, `ingredients[]` (`{ originalText, optional,
       quantityTextOverride?, remove? }`), `instructions[]` (`{ text, section? }`, `remove?`).
   - Server looks up the preview by `parseId`, applies additive edits, marks quantities overridden /
     keeps-as-written, and creates the recipe with the requested image. Enqueues the existing
     background jobs (nutrition/media).
   - Response matches current success shape (`JobAcceptedResponse`), so the client flow downstream of
     "the recipe now exists" is unchanged.
- **Duplicate detection** is computed server-side during preview: normalized-title match or shared-
  ingredient resolution → `ImportPreviewResponse.duplicates[]` (ids + titles). No auto-merge.

### Molecule

- New `application/import_preview.py` service: owns preview capture + confirm application (edits,
  quantity overrides, image selection, section merges) and delegates mutation to `RecipeService`.
- `RecipeImporter` gains a re-entrant "image candidates only" path so preview can include multiple
  thumbnails without choosing one.
- PDF extraction enhanced (see below) with the same image-choices shape.

### Frontend — modal wizard

- `RecipeImportDialog` becomes a 3-step wizard (Radix `Dialog`):
  1. **URL** — existing field (unchanged).
  2. **Preview** — on Start, calls preview; on fallback, navigates to detail (op) as today.
     Shows title, image-chooser (candidate thumbnails), and an editable component list. Each
     component row: title, ingredient list, method list. Ingredients flagged `needsQuantity` render an
     inline quantity prompt (optional "add a quantity" / "as written"). Duplicate warning banner with
     actions: **Keep this import / Discard / Open existing**.
  3. **Confirm** — "Add to collection" submits edits; success navigates/sets the existing post-import
     state.
- Visual design follows existing `dialog`, `stack`, `actions`, field, and button tokens; verify
  390px layout, keyboard accessibility, and explicit loading/empty/stale states.

## Non-Goals

- No automatic merge of duplicates.
- No full PDF-to-multiple-records splitting in this phase.
- No nutrition preview inside the modal (stays post-save).
- No persistence of the `parseId` beyond the short-lived request window.

## Open items left to implement

- Exact `parseId` TTL and storage location (scoped, short-lived).
- Confirm-payload shape for "remove component" vs "mark quantity as-written".
- Image candidate count limit for preview and the thumbnail chooser.

## References

- `docs/superpowers/plans/` prior plans for Phase 1/2 state.
- `problems.txt` items #3, #4, #8, #9, #11.

## Concurrency / boundaries

This is one cohesive feature (import lifecycle). Backend first (TDD), then contract update, then
TS client regen, then frontend modal, then e2e. Where feasible dispatch independent parse/confirm
work in parallel once the backend proposal is green.