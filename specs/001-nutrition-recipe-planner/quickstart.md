# Phase 1 Quickstart: Gym-Focused Recipe & Nutrition Planner

This is the target developer and self-hosted validation workflow. Commands describe the interfaces
the implementation must provide; they are not expected to run until the corresponding setup tasks are
complete.

## Prerequisites

- Git
- Docker Engine/Desktop with Compose v2
- Python 3.13 and `uv`
- Node.js 22 LTS and `pnpm`
- At least 4 GB free RAM for API, worker, PostgreSQL, Redis, and frontend development
- At least 10 GB free disk for containers, reference nutrition data, fixtures, and media

## 1. Configure

```powershell
Copy-Item -LiteralPath '.env.example' -Destination '.env'
```

Set generated local values for:

- `VV_SECRET_KEY`
- `VV_OWNER_EMAIL`
- `VV_OWNER_BOOTSTRAP_PASSWORD`
- PostgreSQL credentials
- Redis URL
- Public/base URL and trusted proxy settings
- Failed-import diagnostic capture disabled by default

Optional provider keys remain unset for the deterministic baseline. Secrets must not be committed or
placed in frontend-prefixed environment variables.

## 2. Start Infrastructure

```powershell
docker compose -f deploy/compose.yaml up -d postgres redis
docker compose -f deploy/compose.yaml ps
```

Both services must report healthy before migrations or workers start.

## 3. Install Locked Dependencies

```powershell
uv sync --project backend --locked --all-extras
pnpm --dir frontend install --frozen-lockfile
```

Lockfiles are committed. CI and production builds fail rather than silently update them.

## 4. Initialize Application Data

```powershell
uv run --directory backend alembic upgrade head
uv run --directory backend vigor-vine bootstrap-owner
uv run --directory backend vigor-vine reference import-fdc --dataset foundation
uv run --directory backend vigor-vine reference import-fdc --dataset sr-legacy
uv run --directory backend vigor-vine reference status
```

The reference status command prints dataset release IDs, record counts, license/attribution, import
time, and whether each release is active. Re-running an identical import must be idempotent.

## 5. Run Development Processes

Use separate terminals:

```powershell
uv run --directory backend uvicorn vigor_vine.api.main:app --reload --port 8000
```

```powershell
uv run --directory backend celery -A vigor_vine.jobs.app worker --loglevel=INFO
```

```powershell
uv run --directory backend vigor-vine outbox-dispatcher
```

```powershell
pnpm --dir frontend dev
```

Expected local endpoints:

- Web client: `http://localhost:5173`
- API health: `http://localhost:8000/api/v1/health`
- OpenAPI document: `http://localhost:8000/openapi.json`

The browser dev server proxies `/api` to the API; cookies remain same-site in development.

## 6. Validate the P1 Recipe Pipeline

1. Sign in with the bootstrap owner.
2. Create a manual recipe with an ingredient range, an item without quantity, and a volume measure.
3. Import a representative public recipe URL.
4. Confirm save/import commits a recipe and job within one second, then observe two-second foreground
   polling and status recovery after a page reload.
5. Observe parsing, matching, conversion assumptions, coverage, canonical decimal strings, and final
   per-serving macros.
6. Correct one match and one macro value; rerun processing and verify both corrections remain active.
7. Change recipe yield and confirm nutrition becomes stale rather than silently changing.
8. Stop Redis during an import, restart it, and verify the outbox/reconciler eventually dispatches one
   idempotent job.
9. Force retryable failures and verify 60-second attempt limits, retry delays of 5 seconds, 30 seconds,
   2 minutes, and 5 minutes, a five-attempt maximum, and a terminal state by 15 minutes.
10. Archive and restore a recipe, then permanently delete it from archive and verify historical plan
    snapshots and grocery source text remain while recipe-owned records disappear.

Run the versioned evaluation corpus before planning UI work beyond the correction flow:

```powershell
uv run --directory backend pytest tests/accuracy -m nutrition_corpus
uv run --directory backend vigor-vine nutrition-report --format markdown --output ../artifacts/nutrition-report.md
```

The gate runs all 50 versioned recipes, reports the stable 30-recipe primary constitutional subset and
20 extension/stress cases separately, and passes only when SC-001/SC-002 thresholds are met. Every miss
is classified as parse, match, conversion, yield, reference-data, or benchmark-eligibility error.
Do not begin the searchable recipe library, polished editor, recipe-detail UI, or any later story until
the stable 30-recipe subset passes. Only the minimum review/correction harness needed to diagnose the
gate may exist beforehand.

## 7. Validate Planning and Grocery Behavior

1. Create a goal with daily calories/macros and one optional meal target.
2. Add known recipe servings across seven days and compare displayed totals with hand-calculated
   round-half-up fixtures. Verify HTTP, MCP, and UI use decimal strings and that displayed entries sum
   exactly to displayed totals and target differences.
3. Edit a recipe estimate and verify existing plan snapshots do not change until explicitly refreshed.
4. Generate a grocery list containing repeated compatible units and ambiguous incompatible units.
5. Check and manually edit items, change the plan, regenerate, and verify manual/check state is
   preserved or flagged for review.

## 8. Run Quality Gates

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

Contract validation must also confirm that the implementation-generated OpenAPI document is compatible
with `specs/001-nutrition-recipe-planner/contracts/openapi.yaml` and that the generated TypeScript
client has no uncommitted changes. Retention-clock tests verify successful HTML is absent after
extraction, opt-in encrypted failed-import HTML expires within 24 hours, detailed diagnostics reduce
after 30 days, and safe job metadata expires after one year.

Run provider-disabled, timeout, invalid-output, and failure substitutes while exercising manual recipe
editing, manual nutrition, goals, plans, groceries, backup, and export. Every workflow must complete
without a provider call or corrupt state, while affected automated nutrition reaches an explicit
partial/failed state with a recovery action. Verify estimated recipe, plan-impact, and suggestion
surfaces show accessible planning-aid—not-medical-advice language.

Performance evidence uses a Linux x86-64 Docker host limited to 4 vCPU, 8 GiB RAM, and SSD with API,
worker, PostgreSQL, and Redis on the same host. Seed the documented reference dataset, make 10
unmeasured warm-up requests per path, and report p50/p95/max across at least 100 measured requests in
each of three runs.

UI acceptance covers desktop and 390x844 viewports, keyboard-only navigation, visible focus, readable
contrast, no page-level horizontal overflow, and explicit loading, empty, partial, estimated, manual,
stale, and failed states. Color is never the only status cue.

## 9. Full Self-Hosted Stack

```powershell
docker compose -f deploy/compose.yaml up --build -d
docker compose -f deploy/compose.yaml ps
docker compose -f deploy/compose.yaml logs --tail 200 api worker outbox
```

The default composition contains `web`, `api`, `worker`, `outbox`, `postgres`, and `redis`. PostgreSQL
and media directories use named volumes. Redis persistence improves recovery but is not authoritative.

## 10. Backup, Restore, and Portable Export

```powershell
uv run --directory backend vigor-vine backup create --output ../artifacts/backups
uv run --directory backend vigor-vine backup verify ../artifacts/backups/<archive>.zip
uv run --directory backend vigor-vine erasure-ledger verify --ledger ../deploy/erasure-ledger
uv run --directory backend vigor-vine export create --include-media --output ../artifacts/exports
```

Restore testing uses a separate empty Compose project and explicit target path; it must never overwrite
the active development database or independent erasure-ledger volume by default. The backup manifest
cursor and hash must verify against the current ledger. Restore replays every later erasure and cannot
be activated when the ledger is missing, behind, discontinuous, or hash-invalid.

```powershell
$restoreProject = 'vigor-vine-restore-check'
docker compose -p $restoreProject -f deploy/compose.restore-test.yaml up -d
uv run --directory backend vigor-vine backup restore --target $restoreProject --erasure-ledger ../deploy/erasure-ledger ../artifacts/backups/<archive>.zip
uv run --directory backend vigor-vine backup compare --target $restoreProject
```

The restore report must show the backup cursor, verified current cursor, every replayed subject/scope,
zero resurrected recipe-owned records, intact detached history, and the final inactive/active decision.

Validate full owner erasure only against a disposable restore-test project. Stop its API, worker,
outbox, and web services; capture the owner UUID; first prove an incorrect confirmation and an
unavailable ledger leave all data unchanged; then run the exact confirmed command:

```powershell
$ownerId = '<disposable-owner-uuid>'
docker compose -p $restoreProject -f deploy/compose.restore-test.yaml stop api worker outbox web
uv run --directory backend vigor-vine owner erase --owner-id $ownerId --confirm "ERASE OWNER $ownerId" --erasure-ledger ../deploy/erasure-ledger
```

Verify the disposable instance returns to bootstrap state, all owner-controlled database and managed-
file data is absent, one `owner_owned` record was appended, and restoring the pre-erasure backup plus
current ledger replays that record with zero resurrection. Never run this validation against the active
development project.

## 11. MCP Expansion Validation (P5)

After P5 is implemented, create a read-only token first and inspect the server:

```powershell
uv run --directory backend mcp dev src/vigor_vine/mcp/server.py
```

Verify `get_meal_plan` and the other read tools, then separately create a token with `plans:write` and
test idempotent add/update/remove operations. MCP and HTTP normalized outputs must match for decimal
strings, totals, provenance, versions, and failure codes. No general prompt or chat tool may be exposed.
