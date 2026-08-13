# Gym-Focused Recipe & Nutrition Planner Development Guidelines

Auto-generated from feature plans and corrected for the repository layout. Last updated: 2026-08-12

## Active Technologies
- Python 3.13 for server and workers; TypeScript 5.x on Node.js 22 LTS for the web client + FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3, Celery 5.6, Redis, HTTPX, `recipe-scrapers`, `ingredient-parser-nlp`, Pint, OR-Tools 9.15 (P4), MCP Python SDK 2.x (P5), React 19.2, Vite 8.1, React Router, TanStack Query, React Hook Form, Zod, Radix UI primitives (001-nutrition-recipe-planner)
- PostgreSQL 18 for application and locally imported nutrition-reference data; Redis for job delivery and short-lived coordination while PostgreSQL remains authoritative; filesystem/object-compatible media volume for recipe images, opt-in encrypted failed-import diagnostics, and export archives; append-only erasure-ledger volume that restore cannot overwrite (001-nutrition-recipe-planner)

- Python 3.13 for the API, worker, CLI, and MCP adapter
- TypeScript 5.x on Node.js 22 LTS for the React 19.2 + Vite 8.1 client
- FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3, Celery 5.6, Redis, HTTPX, and PostgreSQL 18
- `recipe-scrapers`, `ingredient-parser-nlp`, Pint, USDA FoodData Central, and OR-Tools 9.15 (P4)
- PostgreSQL-authoritative jobs, Redis delivery/coordination, and filesystem/object-compatible media,
  encrypted diagnostic, and export storage

## Project Structure

```text
backend/
├── src/cookfully/
└── tests/
frontend/
├── src/
└── e2e/
deploy/
docs/
scripts/
specs/
```

## Commands

```text
uv run --directory backend ruff format --check .
uv run --directory backend ruff check .
uv run --directory backend mypy src
uv run --directory backend pytest
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
pnpm --dir frontend exec playwright test
```

## Product Persona

Cookfully helps people who want to take control of their personal health through food
and stay organized in the process. The core audience is meal-preppers, health-conscious home
cooks, and anyone who wants recipes to "do the macro math for them" without feeling like a
spreadsheet. The app is deliberately not a gym-bro calorie counter — it is a cooking tool
that happens to be nutrition-aware. Every feature decision should start with: "Does this
help someone plan, cook, and eat better food with less friction?"

## Code Style and Architecture

- Keep domain and application rules independent of FastAPI, Celery, and MCP transports.
- Preserve original ingredient text, nutrition provenance, serving basis, and active correction
  precedence in every code path.
- Background handlers must be idempotent and reject stale input hashes.
- Use fixed-precision decimals for stored nutrition and scaled integers for solver inputs.
- Follow `DESIGN.md` for UI tokens and verify desktop plus 390x844 behavior, keyboard access, overflow,
  and explicit loading/empty/partial/estimated/manual/stale/failed states.

## Recent Changes
- **Food matching v2** — signal-based scoring (head/block/lead) with penalty lexicons for
  product forms, flavours, and plant parts. Exact-tie-only ambiguity. Variant-aware SQL
  containment ordering. Live-verified against 8.1k USDA corpus.

- **Nutrition pipeline fix** — SR Legacy nutrient codes (203/204/205/208) added to CORE
  lookup; Atwater energy fallback for foods missing energy data. Nutrition now resolves
  on seeded recipes at 75%/73% coverage.

- **Owner-created foods** — `owner_foods` table with CRUD API. Owner foods have lexical
  priority over USDA during recipe save. Pipeline skips manually-matched ingredients.
  Frontend: Foods library page (`/app/foods`), CreateFoodDialog, FoodPicker on recipe detail.

- **Branded food import** — `food_references.serving_size_g` + `serving_unit`. Branded
  USDA import gated behind `GYM_BRANDED_CATEGORIES` filter.

- **Cook mode + portion scaling** — Full-screen step-by-step cooking view with wake-lock
  at `/app/recipes/:id/cook`. Interactive serving adjustment on recipe detail with
  real-time ingredient + macro recalculation.

- 001-nutrition-recipe-planner: resolved the constitutional benchmark gate order, full-owner erasure,
  reference performance profile, deterministic suggestion ranking, fixed P6 micronutrients, planning-
  aid presentation, and provider-degraded workflow evidence.

- 001-nutrition-recipe-planner: propagated exact-decimal contracts, the 50-recipe benchmark,
  recipe erasure, bounded retention, polling/retry deadlines, and complete API/MCP lifecycle surfaces.

- 001-nutrition-recipe-planner: selected the fresh FastAPI/React architecture, PostgreSQL/Redis/Celery
  processing boundary, nutrition-first model, OpenAPI contracts, and phased P1-P6 delivery.

- 002-persistent-sessions-settings: Immich-style persistent sessions (configurable `COOKFULLY_SESSION_TTL_DAYS`,
  default 400 days), a session list/revoke + password-change API, and a tabbed Account/Security/API-access
  Settings page. Session cookie switched to `SameSite=lax`; the retention sweep removes stale sessions.

<!-- MANUAL ADDITIONS START -->
- Treat Mealie, Tandoor Recipes, and Immich as recurring comparison points for relevant product,
  architecture, security, data-lifecycle, background-processing, and UI decisions. Inspect current
  official code or documentation rather than relying on reputation or memory.
- Record material comparisons in `docs/inspiration-review.md`: the problem being solved, the observed
  pattern, its benefits and liabilities, whether Cookfully adopts/adapts/rejects it, and why the
  decision fits this project's narrower nutrition-first requirements.
- Do not presume either this repository or an inspiration project has the best design. Challenge both
  sets of assumptions, account for their different scale/persona/history, and validate adopted patterns
  through this project's contracts and tests.
<!-- MANUAL ADDITIONS END -->
