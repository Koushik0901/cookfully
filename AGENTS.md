# Gym-Focused Recipe & Nutrition Planner Development Guidelines

Auto-generated from feature plans and corrected for the repository layout. Last updated: 2026-08-09

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
├── src/vigor_vine/
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
uv run --project backend ruff format --check .
uv run --project backend ruff check .
uv run --project backend mypy src
uv run --project backend pytest
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
pnpm --dir frontend exec playwright test
```

## Code Style and Architecture

- Keep domain and application rules independent of FastAPI, Celery, and MCP transports.
- Preserve original ingredient text, nutrition provenance, serving basis, and active correction
  precedence in every code path.
- Background handlers must be idempotent and reject stale input hashes.
- Use fixed-precision decimals for stored nutrition and scaled integers for solver inputs.
- Follow `DESIGN.md` for UI tokens and verify desktop plus 390x844 behavior, keyboard access, overflow,
  and explicit loading/empty/partial/estimated/manual/stale/failed states.

## Recent Changes
- 001-nutrition-recipe-planner: Added Python 3.13 for server and workers; TypeScript 5.x on Node.js 22 LTS for the web client + FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3, Celery 5.6, Redis, HTTPX, `recipe-scrapers`, `ingredient-parser-nlp`, Pint, OR-Tools 9.15 (P4), MCP Python SDK 2.x (P5), React 19.2, Vite 8.1, React Router, TanStack Query, React Hook Form, Zod, Radix UI primitives

- 001-nutrition-recipe-planner: propagated exact-decimal contracts, the 50-recipe benchmark,
  recipe erasure, bounded retention, polling/retry deadlines, and complete API/MCP lifecycle surfaces.

- 001-nutrition-recipe-planner: selected the fresh FastAPI/React architecture, PostgreSQL/Redis/Celery
  processing boundary, nutrition-first model, OpenAPI contracts, and phased P1-P6 delivery.

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
