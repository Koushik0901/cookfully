# Gym-Focused Recipe & Nutrition Planner Development Guidelines

Auto-generated from feature plans and corrected for the repository layout. Last updated: 2026-08-09

## Active Technologies

- Python 3.13 for the API, worker, CLI, and MCP adapter
- TypeScript 5.x on Node.js 22 LTS for the React 19.2 + Vite 8.1 client
- FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3, Celery 5.6, Redis, and PostgreSQL 18
- `recipe-scrapers`, `ingredient-parser-nlp`, Pint, USDA FoodData Central, and OR-Tools 9.15 (P4)

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

- 001-nutrition-recipe-planner: selected the fresh FastAPI/React architecture, PostgreSQL/Redis/Celery
  processing boundary, nutrition-first model, OpenAPI contracts, and phased P1-P6 delivery.

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
