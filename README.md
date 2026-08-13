# Cookfully

Cookfully is a self-hosted recipe and nutrition planner for people who want to cook, plan, and eat
with more care. It helps you keep recipes you love, shape a realistic week, make a grocery list, and
understand nutrition without making food feel like a spreadsheet.

It is not a gym dashboard. Food and cooking stay in the foreground; calorie and macro estimates are
quiet, correctable evidence for anyone eating for general health, dietary requirements, balanced
nutrition, weight change, performance, or simple organization.

## What it does

- Import a recipe from the web or write one yourself.
- Preserve ingredient text and show a nutrition estimate with its coverage, source, assumptions, and
  corrections.
- Plan meals by week or day, adjust servings, and use suggestions where they solve a visible gap.
- Generate an editable grocery list and optionally apply reviewed pantry deductions.
- Start with one familiar recipe, optionally add a representative photo, and keep a growing library
  findable with favorites, collections, and meal moments.
- Shop a weekly list by the stops you actually visit; completed shopping passes remain an explicit
  record until you reopen them.
- Create owner foods for nutrition labels or staples that need a more faithful match.
- Keep advanced integration access separate from everyday cooking flows.

## Experience principles

Cookfully follows an **editorial kitchen utility** direction: warm, assured, and appetizing. It
uses progressive disclosure so a person can start with a recipe or meal rather than confronting a
wall of inputs or self-hosting settings. The authoritative UI rules—including accessibility,
responsive behavior, nutrition language, and empty/error states—are in [DESIGN.md](DESIGN.md).

The first-run guide is optional and intentionally contains no body measurements, diet labels, or
mandatory targets. Nutrition guidance remains available beside planning when it is useful.

## Project layout

The implementation is organized as a Python 3.13 API/worker/CLI under `backend/`, a React 19 web
client under `frontend/`, and Docker Compose deployment assets under `deploy/`.

| Directory | Purpose |
| --- | --- |
| `backend/` | FastAPI application, workers, migrations, and tests |
| `frontend/` | React application, component system, and browser tests |
| `deploy/` | Self-hosting and Docker Compose assets |
| `docs/` | Product, nutrition, operations, and integration documentation |
| `specs/` | Contracts, plans, and the development quickstart |

## Develop and verify

Install the required Python and Node toolchains, then use these checks from the repository root:

```powershell
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

For the complete development environment and service setup, see
[the quickstart](specs/001-nutrition-recipe-planner/quickstart.md). For a runnable self-hosted
deployment, start with [self-hosting](docs/self-hosting.md).

## Further reading

- [Nutrition methodology](docs/nutrition-methodology.md)
- [Backup and restore](docs/backup-restore.md)
- [Owner erasure](docs/owner-erasure.md)
- [Operations runbook](docs/operations-runbook.md)
- [Inspiration review log](docs/inspiration-review.md)

