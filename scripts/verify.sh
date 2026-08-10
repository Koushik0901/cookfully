#!/usr/bin/env bash
set -euo pipefail

uv sync --project backend --locked --all-extras --dev
uv run --directory backend ruff format --check .
uv run --directory backend ruff check .
uv run --directory backend mypy src
uv run --directory backend pytest

pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
pnpm --dir frontend exec playwright test

docker compose -f deploy/compose.yaml config --quiet
