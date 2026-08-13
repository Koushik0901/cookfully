# Implementation Plan: A calmer first kitchen

**Branch**: `003-onboard-recipe-library` | **Date**: 2026-08-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-onboard-recipe-library/spec.md`

## Summary

Deliver one coherent journey from a calm first action to a finished weekly shop. Add durable
owner-onboarding state; reuse the existing normalized recipe-media pipeline for one optional manual
recipe photo; add favorite, collection, and fixed meal-role organization; and extend grocery
reconciliation with personal shopping stops, safe remembered placement, and an explicit completed
shopping-pass state. Keep navigation stable and surface supporting controls in Recipes and Grocery.

Implement vertical slices in this order: (1) migration, canonical services, schemas, export/erasure,
and OpenAPI contracts; (2) first-run and manual photo surfaces; (3) recipe organization and focused
library retrieval; (4) grocery stops, reconciliation preservation, completion/reopen; (5) responsive
and end-to-end verification.

## Technical Context

**Language/Version**: Python 3.13 backend; TypeScript 5.x / Node.js 22 frontend
**Primary Dependencies**: FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Pillow, python-multipart; React 19.2, Vite 8.1, React Router, TanStack Query, React Hook Form, Zod, Radix primitives
**Storage**: PostgreSQL 18 for canonical records; existing self-hosted filesystem/object-compatible media volume for normalized recipe photos; existing portable export archive
**Testing**: pytest contract/integration/unit coverage; Vitest component coverage; Playwright responsive/end-to-end coverage; lint, type, build, and OpenAPI generated-schema checks
**Target Platform**: Self-hosted web application on modern desktop and mobile browsers
**Project Type**: React web client plus FastAPI service and worker
**Performance Goals**: First-run actions render without a blocking form; valid image preview/upload completes within the specification target; 25-recipe focused filtering feels immediate; a 15-item two-stop shopping pass is usable in under two minutes
**Constraints**: One optional representative manual-recipe photo; server-side validated JPEG/PNG/WebP; no AI/photo nutrition inference; no new external provider, secrets, subscription, or client-side media storage; preserve nutrition, export, erasure, optimistic concurrency, grocery reconciliation, and pantry safeguards
**Scale/Scope**: Single self-hosted owner/small household; current recipe/plan/grocery library; desktop 1440x900 and mobile 390x844 are required verification targets

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Macro-goal alignment — PASS**: The work shortens the existing path of creating/importing a recipe,
  planning meals, acquiring ingredients, and cooking them. It explicitly excludes social feeds,
  arbitrary lifestyle organization, and retailer commerce.
- **Nutrition integrity — PASS**: No new nutrition value is inferred or recalculated. Photo and
  organization operations leave recipe input hashes, servings, estimates, corrections, provenance,
  and plan snapshots unchanged. Existing grocery-source and pantry-deduction preservation is expanded
  with shopping-stop assignment tests.
- **Bounded processing — PASS**: There is no AI. Local image decode/normalization is a fixed,
  server-validated operation using existing Pillow/media code; existing asynchronous nutrition/import
  jobs remain unchanged. Failed photo processing is non-destructive and retryable.
- **Data ownership and contracts — PASS**: New records are owner-scoped and added to export/restore and
  erasure coverage. Canonical services back documented HTTP contracts; existing session/CSRF,
  idempotency where applicable, and `If-Match` conflict behavior are retained. No provider, secret, or
  MCP mutation is added.
- **Reuse and product quality — PASS**: Research adopts the useful collection and meal-plan-to-shopping
  ideas evidenced by Mealie/Tandoor and the visible, safe image handling exemplified by Immich, while
  rejecting their broader configuration/metadata surface. Existing `MediaStore`, `RecipeImageService`,
  shared UI primitives, `RecipeFallbackArt`, and grocery reconciliation are reused. Every changed
  screen receives loading, empty, partial, stale, failed, conflict, keyboard, and responsive evidence.
- **Verification — PASS**: Add backend migration/service/contract/integration fixtures; frontend
  component tests; desktop/mobile Playwright journeys; export/erasure coverage; and run the complete
  repository quality gates named in `quickstart.md`.

## Project Structure

### Documentation (this feature)

```text
specs/003-onboard-recipe-library/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
```text
backend/
├── src/
│   └── cookfully/
│       ├── api/routes/{owner,recipes,grocery,media}.py
│       ├── api/schemas/{recipes,grocery}.py
│       ├── application/{owner_onboarding,recipe_organization,grocery_lists}.py
│       ├── infrastructure/models/{identity,recipes,grocery,media}.py
│       └── infrastructure/{media_store,recipe_images}.py
├── migrations/versions/
└── tests/{contract,integration}/

frontend/
├── src/
│   ├── app/{App.tsx,api/generated/schema.ts}
│   ├── components/{cookfully,ui}/
│   ├── features/onboarding/
│   ├── features/recipes/
│   └── features/grocery/
└── e2e/

docs/
└── inspiration-review.md
```

**Structure Decision**: Use the existing FastAPI/React split. New domain operations live in
application services and SQLAlchemy models, routes remain transport adapters, and the generated
frontend schema remains the UI contract. Do not create a separate photo service, collection app,
shopping microservice, or navigation destination.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | All constitution gates pass without an exception. | N/A |
