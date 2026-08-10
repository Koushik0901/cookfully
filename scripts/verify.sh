#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
base_compose="$root/deploy/compose.yaml"
production_compose="$root/deploy/compose.production.yaml"
performance_compose="$root/deploy/compose.performance.yaml"
requirements="$(mktemp)"
trap 'rm -f -- "$requirements"' EXIT
cd "$root"

uv sync --project backend --locked --all-extras --dev
uv run --directory backend ruff format --check .
uv run --directory backend ruff check .
uv run --directory backend mypy src
uv run --directory backend python ../scripts/generate-sbom.py --verify-only
uv export --project backend --locked --all-extras --no-dev --no-hashes --no-emit-project --output-file "$requirements"
uvx pip-audit -r "$requirements" --strict

docker compose -f "$base_compose" stop api worker outbox retention
uv run --directory backend pytest
uv run --directory backend vigor-vine nutrition-corpus run --require-pass --output ../artifacts/nutrition-release-report.json

pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend audit --audit-level high
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
pnpm --dir frontend exec playwright test

pnpm --dir frontend exec openapi-typescript ../specs/001-nutrition-recipe-planner/contracts/openapi.yaml --output src/app/api/generated/schema.ts
git diff --exit-code -- frontend/src/app/api/generated/schema.ts

docker compose -f "$base_compose" config --quiet
docker compose -f "$base_compose" -f "$production_compose" config --quiet
docker compose -f "$base_compose" -f "$production_compose" build
docker compose -f "$base_compose" -f "$performance_compose" --profile performance up --build -d postgres redis api worker outbox retention web
docker compose -f "$base_compose" -f "$performance_compose" --profile performance build benchmark
VV_PERFORMANCE_REPORT_CONTAINER=/app/artifacts/performance-release-report.json \
  docker compose -f "$base_compose" -f "$performance_compose" --profile performance run --no-deps --rm benchmark

python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8080/api/v1/health", timeout=5) as response:
    health = json.load(response)
assert health["status"] == health["database"] == health["broker"] == "ok", health
PY

running="$(docker compose -f "$base_compose" -f "$performance_compose" --profile performance ps --services --status running)"
for service in postgres redis api worker outbox retention web; do
  grep -qx "$service" <<<"$running"
done
