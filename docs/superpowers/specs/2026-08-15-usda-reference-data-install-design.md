# Design: In-app USDA reference data install

Date: 2026-08-15
Status: Approved by owner

## Problem

Nutrition estimates only work when USDA FoodData Central reference data is present. Today the only
way to install it is an operator CLI (`cookfully reference-data import` + `activate`) that requires
downloading ~100 MB of official bulk files and, in the documented path, a local Python 3.13 + `uv`
environment. A user who clones the repo, starts the Docker stack, and opens the app gets an empty
nutrition corpus: every ingredient is unmatched and coverage is near zero. The user asked for a
button in the app: pick what to install, and the app downloads, imports, and activates everything in
the background.

## Non-goals

- Health Canada Canadian Nutrient File (CNF): rejected after evaluation — ~5,700 mostly generic
  foods overlapping USDA naming, relational CSV format requiring a second importer, no text-search
  API, and the matching benchmark is anchored on the USDA corpus. The `provider` column is already
  extensible, so a later Canadian-market addition stays possible without schema work.
- Live USDA API lookups at match time: the matching pipeline is deliberately local and deterministic
  (50-recipe benchmark, exact-decimal contracts, exact-tie-only ambiguity). A live API would add
  network dependency, rate limits (~1,000 req/h), latency, and non-determinism to the constitutional
  core. Rejected.
- Automatic install at container startup: no user choice, no progress UI, long first boot. Rejected.
- Branded-food reinstall/update workflow (supersede via UI): later concern. YAGNI.

## Behavior

### Datasets

Two installable units, both sourced from pinned USDA FoodData Central bulk downloads
(`fdc.nal.usda.gov/fdc-datasets/...`):

1. **Foundation + SR Legacy** (one unit, required for useful nutrition): ~10,000 foods —
   Foundation (~1,700 deeply lab-analyzed whole foods) plus SR Legacy (~7,800, the classic 2018
   database of ingredients and prepared items). ~100 MB download, a few minutes to import.
2. **Branded foods** (optional): packaged gym products — protein powders, protein bars, Greek
   yogurt, cottage cheese, nut butters, shakes, etc. — filtered by the existing
   `GYM_BRANDED_CATEGORIES` set. ~1.5 GB download, much slower.

Pin exact release IDs, dates, and URLs as code constants so installs are deterministic and
repeatable (matching the CLI's `foundation-YYYY-MM` / `sr-legacy-2018-04` convention). URLs are
validated with a HEAD request during implementation.

### Backend

Reuses the existing job infrastructure (`JobService`, jobs table, outbox, Celery, five-attempt
backoff + deadlines, `JobProgress` polling) and the existing library functions
`import_release()`, `activate_release()`, and `release_status()` from
`cookfully/cli/reference_data.py`. Those functions currently create their own engine/session; the
install path calls them from the worker with the same settings, which is already the CLI pattern.

- `GET /reference-data/status` — owner-scoped. Returns `release_status()` output (available,
  missing, active releases with license/release date/review-overdue) plus the latest install job's
  progress: phase (`downloading` | `importing` | `activating`), percent, state
  (`running` | `succeeded` | `failed`).
- `POST /reference-data/install` — owner-scoped. Body `{"datasets": ["foundation_sr_legacy",
  "branded"]}`. Creates one install job (aggregate type `reference_data` with a fixed sentinel
  aggregate id defined as a code constant, so `latest_for_aggregate` always finds the latest
  install). Idempotency:
  - datasets whose pinned release is already `ready`/`active` are skipped (accepted, no-op);
  - 409 `install_in_flight` if an install job is already running; one install at a time;
  - the job's input carries the requested dataset units; the worker rejects stale inputs per the
    existing job-hash rule.
- Worker task (`cookfully.jobs.reference_data_install`):
  1. For each requested unit, in order: download the pinned zip via HTTPX (streamed to a temp
     directory), report progress by phase.
  2. `import_release(path, dataset_type=..., release_id=..., released_on=..., source_url=...)`
     for foundation and sr_legacy (or branded) — one transaction, so a malformed file leaves zero
     rows.
  3. `activate_release(dataset_id)` for each imported dataset (supersedes older active releases of
     the same type, existing behavior).
  4. Delete the temp zip in a `finally` block — after success and after failure (bounded disk).
- Auth: existing owner-scoped session auth; no new roles.

### Onboarding

The existing first-run journey (`FirstRunJourney`, shown on the recipe library when onboarding is
`pending`) gains a second screen, "Real nutrition numbers?":

- Two option cards with the same short descriptions and download sizes used in Settings.
- Choices: **Install both**, **Foundation + SR Legacy only**, **Not now**.
- Choosing persists `referenceDataChoice` (`both` | `foundation_sr_legacy` | `none`) on the
  onboarding record (new optional field, versioned PUT as today), then fires the install request
  when applicable, and continues to the existing welcome flow.
- Non-blocking, matching the existing principle "optional guidance must never block the real task":
  if the install request fails, onboarding still completes; Settings shows the retry surface.

### Settings

New "Nutrition data" tab (next to Account / Security / Connections):

- Status card: active datasets (release id, released-on, license), missing datasets, and any
  in-flight job with phase + percent progress bar.
- Buttons: "Install Foundation + SR Legacy", "Install Branded foods" — disabled while installed or
  while a job is running; "Retry" on failed jobs.
- Same one-paragraph explanations as onboarding, including the branded size caveat.

### Documentation

`docs/docker-quickstart.md` "Nutrition reference data (optional)" section updated to point at the
in-app install as the primary path; CLI remains available for operators.

## Error handling

- Download failures (network, 404, disk full) → attempt fails; existing 5-attempt backoff and
  deadline machinery; terminal `failed` state surfaces in Settings with Retry.
- Malformed/invalid USDA JSON → job fails with a clear message; single-transaction import leaves
  zero partial rows.
- Concurrent install requests → 409 while a job is in flight.
- Temp zips always removed in `finally`, including failure paths.

## Testing

- Backend unit: pinned-release constants/URLs, idempotent skip logic, 409 concurrency rule.
- Backend integration: fixture archives shaped like USDA JSON (no network) — full
  download-substitute → import → activate against a test database; job lifecycle
  accept → claim → progress → succeed; failed import leaves zero rows; cleanup runs on failure.
- Frontend: onboarding step renders options, persists choice, fires install without blocking
  navigation; Settings tab renders active/missing/progress/failed states.
- Playwright E2E: onboarding → choose → job completes → status shows active; Settings retry path.
- Quality gates per AGENTS.md: ruff, mypy, pytest, lint, typecheck, vitest, build.

## Files touched (expected)

- `backend/src/cookfully/api/routes/reference_data.py` (new), schemas
- `backend/src/cookfully/jobs/` — install task + registration
- `backend/src/cookfully/cli/reference_data.py` — reuse (no change expected)
- `backend/src/cookfully/infrastructure/models/` — onboarding choice column migration (Alembic)
- `frontend/src/features/onboarding/` — second screen, api/types
- `frontend/src/features/settings/` — Nutrition data tab
- `docs/docker-quickstart.md` — updated install note