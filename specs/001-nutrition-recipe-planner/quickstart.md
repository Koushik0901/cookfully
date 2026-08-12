# Phase 1 Quickstart: Gym-Focused Recipe & Nutrition Planner

This is the validated developer and self-hosted workflow. The 2026-08-10 execution record at the end
distinguishes commands run literally from destructive or operator-supplied-data scenarios exercised
through isolated automated fixtures.

## Prerequisites

- Git
- Docker Engine/Desktop with Compose v2
- Python 3.13 and `uv`
- Node.js 22 LTS and `pnpm`
- At least 4 GB free RAM for API, worker, PostgreSQL, Redis, and frontend development
- At least 10 GB free disk for containers, reference nutrition data, fixtures, and media

## 1. Configure

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
  Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
```

Set generated local values for:

- `COOKFULLY_SECRET_KEY`
- `COOKFULLY_OWNER_EMAIL`
- `COOKFULLY_OWNER_BOOTSTRAP_PASSWORD`
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
$foundationId = (uv run --directory backend cookfully reference-data import C:\path\to\FoodData_Central_foundation_food_json.json --dataset-type foundation --release-id foundation-YYYY-MM --released-on YYYY-MM-DD --source-url https://fdc.nal.usda.gov/fdc-datasets.html).Split()[0]
$legacyId = (uv run --directory backend cookfully reference-data import C:\path\to\FoodData_Central_sr_legacy_food_json.json --dataset-type sr_legacy --release-id sr-legacy-2018-04 --released-on 2018-04-01 --source-url https://fdc.nal.usda.gov/fdc-datasets.html).Split()[0]
uv run --directory backend cookfully reference-data activate $foundationId
uv run --directory backend cookfully reference-data activate $legacyId
uv run --directory backend cookfully reference-data status
```

Replace the paths and Foundation release metadata with the downloaded supported USDA bulk files; do
not use the placeholder values literally. The first API startup bootstraps the single owner from the
validated `COOKFULLY_OWNER_*` settings, so there is intentionally no password-bearing `bootstrap-owner`
command. The reference status command prints dataset release IDs, record counts,
license/attribution, import time, and whether each release is active. Re-running an identical import
must be idempotent.

## 5. Run Development Processes

Use separate terminals:

```powershell
uv run --directory backend uvicorn cookfully.api.main:app --reload --port 8000
```

```powershell
uv run --directory backend celery -A cookfully.jobs.app worker --loglevel=INFO
```

```powershell
uv run --directory backend python -m cookfully.jobs.outbox_process
```

```powershell
uv run --directory backend python -m cookfully.jobs.retention_process
```

```powershell
pnpm --dir frontend dev
```

Expected local endpoints:

- Web client: `http://localhost:5173`
- API health: `http://localhost:8000/api/v1/health`
- OpenAPI document: `http://localhost:8000/api/openapi.json`

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
uv run --directory backend cookfully nutrition-corpus run --require-pass --output ../artifacts/nutrition-report.json
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
docker compose -f deploy/compose.yaml logs --tail 200 api worker outbox retention
```

The default composition contains `web`, `api`, `worker`, `outbox`, `retention`, `postgres`, and
`redis`. PostgreSQL and media directories use named volumes. Redis persistence improves recovery but
is not authoritative.

## 10. Backup, Restore, and Portable Export

```powershell
uv run --directory backend cookfully backup create --output ../artifacts/backups
$backup = Get-ChildItem -LiteralPath artifacts/backups -Filter '*.zip' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
uv run --directory backend cookfully backup verify $backup.FullName
uv run --directory backend cookfully erasure-ledger verify --ledger ./erasure-ledger
uv run --directory backend cookfully export create --include-media --output ../artifacts/exports
```

Restore testing uses a separate empty Compose project and explicit target path; it must never overwrite
the active development database or independent erasure-ledger volume by default. The backup manifest
cursor and hash must verify against the current ledger. Restore replays every later erasure and cannot
be activated when the ledger is missing, behind, discontinuous, or hash-invalid.

```powershell
$restoreProject = 'cookfully-restore-check'
$targetUrl = 'postgresql+psycopg://cookfully:restore-check-only@localhost:55432/cookfully_restore'
docker compose -p $restoreProject -f deploy/compose.restore-test.yaml up -d
$env:COOKFULLY_DATABASE_URL = $targetUrl
uv run --directory backend alembic upgrade head
uv run --directory backend cookfully backup restore --target-database-url $targetUrl --target-media-root ../artifacts/restore-media --erasure-ledger ./erasure-ledger --staging-root ../artifacts/restore-stage $backup.FullName
uv run --directory backend cookfully backup compare --target-database-url $targetUrl --erasure-ledger ./erasure-ledger $backup.FullName
```

The restore report must show the backup cursor, verified current cursor, every replayed subject/scope,
zero resurrected recipe-owned records, intact detached history, and the final inactive/active decision.

Validate full owner erasure only against a disposable restore-test project. Stop any API, worker,
outbox, retention, and web processes connected to the disposable target; capture the owner UUID;
first prove an incorrect confirmation and an
unavailable ledger leave all data unchanged; then run the exact confirmed command:

```powershell
$ownerId = '<disposable-owner-uuid>'
$env:COOKFULLY_DATABASE_URL = $targetUrl
$env:COOKFULLY_MEDIA_ROOT = '../artifacts/restore-media'
$env:COOKFULLY_EXPORT_ROOT = '../artifacts/restore-exports'
uv run --directory backend cookfully owner erase --owner-id $ownerId --confirm "ERASE OWNER $ownerId" --erasure-ledger ./erasure-ledger
```

Verify the disposable instance returns to bootstrap state, all owner-controlled database and managed-
file data is absent, one `owner_owned` record was appended, and restoring the pre-erasure backup plus
current ledger replays that record with zero resurrection. Never run this validation against the active
development project.

## 11. MCP Expansion Validation (P5)

After P5 is implemented, create a read-only token first and inspect the server:

```powershell
uv run --directory backend mcp dev src/cookfully/mcp/server.py
```

Verify `get_meal_plan` and the other read tools, then separately create a token with `plans:write` and
test idempotent add/update/remove operations. MCP and HTTP normalized outputs must match for decimal
strings, totals, provenance, versions, and failure codes. No general prompt or chat tool may be exposed.

## 12. Execution Record — 2026-08-10

This run used Docker Desktop's Linux x86-64 engine on Windows. No result below substitutes a fixture
for a real upstream dataset without saying so.

| Area | Result | Deviation or correction |
| --- | --- | --- |
| Prerequisites | Git 2.49, Docker 29.6.2, Compose 5.3.1, `uv` 0.10.0, Node 22.17.1, and pnpm 10.17.0 were available. `uv run --directory backend python --version` selected Python 3.13.5. | System `python` was 3.12.9; the locked `uv` environment is the supported runtime. |
| Configuration and infrastructure | PostgreSQL and Redis reached healthy state and Alembic upgraded through revision `0009_pantry`. | The first Compose invocation correctly failed closed because `.env` was absent. Existing local container secrets were injected without printing them; no secret was committed. |
| Locked installs | `uv sync --project backend --locked --all-extras` and `pnpm --dir frontend install --frozen-lockfile` passed. | pnpm reported that dependency build scripts were ignored by policy; subsequent client tests and production builds passed. |
| USDA reference data | The real `reference-data status` command ran. Import idempotency, activation, provenance, and record counts passed in `tests/integration/test_reference_data.py` (2 tests). | No local USDA bulk archive was supplied, so the active development database truthfully reports both supported datasets as missing. The operator-only bulk import commands were validated with isolated USDA-shaped fixtures, not represented as a full FDC installation. |
| Nutrition benchmark | `pytest tests/accuracy -m nutrition_corpus` passed 7 tests with 5 deselected; `nutrition-corpus run --require-pass` evaluated all 50 cases. | The generated report is `artifacts/nutrition-report.json`: 50/50 imports, 49/50 benchmark-eligible nutrition cases, and all SC-001/SC-002/SC-003 gates pass; the stable primary split is 30 imports and 29 nutrition cases. |
| Development API | A local Uvicorn process served the API; `/api/v1/health` returned `status=ok`, `/api/openapi.json` reported OpenAPI 3.1.0 and app version 0.2.0, and the web endpoint returned HTTP 200. | An initial probe of `/api/health` returned 404 and confirmed that the documented `/api/v1/health` path is required. The temporary Uvicorn child process was explicitly stopped after validation. |
| Recipe, job, planning, grocery, export, provider, and MCP scenarios | Contract, integration, MCP E2E, and security suites completed with 75 passing tests after the destructive tests were isolated. They cover manual/import flows, polling/retry/idempotency, active corrections, stale yield, archive/restore/permanent delete, exact snapshots, grocery reconciliation, portable export, provider-disabled behavior, token scopes, and HTTP/MCP parity. | With live services running, 72 tests passed and three owner-erasure tests intentionally failed with `services_running`. After the API, worker, outbox, retention, and one leftover local Uvicorn process were stopped, all four owner-erasure tests passed; the stack was then restored. |
| Full self-hosted stack | `docker compose -f deploy/compose.yaml up --build -d` built the client and all backend images. `web`, `api`, `worker`, `outbox`, `retention`, `postgres`, and `redis` are running; all services with health checks are healthy. Retention logged a successful first sweep and Celery connected to Redis. | This run exposed empty tuple environment decoding before validation. `NoDecode` plus CSV/empty-string validation fixed `COOKFULLY_TRUSTED_PROXY_CIDRS` and retry delays; focused format, lint, mypy, and five unit tests pass. Compose inspection commands require the same configured secrets because interpolation deliberately fails closed. |
| Backup, restore, ledger, and erasure | `erasure-ledger verify --ledger ./erasure-ledger` returned a valid empty chain. The isolated restore/erasure evidence in `artifacts/restore-report.md` covers archive verification, media, exact decimals, detached history, missing/discontinuous-ledger rejection, recipe replay, owner replay, and zero resurrection. | The destructive CLI examples were not run against the active development database. Their underlying commands were exercised against disposable schemas and temporary media/ledger roots, as the quickstart requires. |
| Quality and UI gates | Focused backend gates above pass; production client build passed during image construction. Accessibility and responsive Playwright evidence is recorded by the dedicated release-gate tasks. | The complete consolidated gate remains owned by T158 and is recorded separately in `artifacts/release-gates.md`; performance is owned by T144. |

Corrections made during execution: replaced nonexistent owner-bootstrap, reference-import,
nutrition-report, outbox, and ledger commands with their implemented interfaces; corrected the
OpenAPI and health paths; added the retention process everywhere the lifecycle requires it; made
archive selection explicit; and required an isolated restore target for destructive validation.
