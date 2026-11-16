# Continuous integration

Workflows live in `.github/workflows/`. `ci.yml` is the entry point: it runs once per change (pull
requests and pushes to `main`), cancels itself when a newer push supersedes a pull request, and calls the
other workflows as reusable workflows. Every job has a timeout.

| Workflow | What it checks | Gate |
| --- | --- | --- |
| `ci.yml` | decides what changed, calls the workflows below, lints the workflows themselves (actionlint, zizmor), scans new commits for secrets (gitleaks), then reports **`ci-ok`** | `ci-ok` |
| `backend.yml` | **Lint and types** (ruff, mypy); **Tests and coverage** (pytest against the same `vchord-postgres` and Redis images as `deploy/compose.yaml`) | total coverage ≥ `fail_under`; changed lines ≥ 85% |
| `frontend.yml` | **Lint, types and build** plus a generated-API-client drift check; **Unit tests and coverage** (Vitest); **End-to-end** (Playwright on Chromium in two shards, with WebKit native-select in its own job) | coverage thresholds in `vite.config.ts`; every e2e assertion |
| `dependency-audit.yml` | `pip-audit` and `pnpm audit --prod` when a manifest changes; a daily full report | production dependencies only |
| `containers.yml` | compose files validate; each image builds (nothing is pushed) | when `deploy/**` or a lockfile changes |
| `publish-containers.yml` | build and push images to GHCR | release tags `v*.*.*`, only for a commit on `main` whose `ci-ok` passed |
| `visual-baselines.yml` | regenerate and commit Linux screenshot baselines | manual |

Jobs inside a workflow run in parallel, so a lint or audit failure can no longer hide whether tests
pass.

## The merge gate

Branch protection should require exactly these checks (Settings → Rules → the `main` ruleset → *Require
status checks to pass*), and *Require branches to be up to date*:

- **`ci-ok`**: passes only when every job in `ci.yml` passed or was skipped on purpose. Add a new
  check by putting its job in `ci-ok.needs`; the required name never changes, so a renamed or removed job
  cannot silently drop out of the gate.
- **`Analyze (python)`**, **`Analyze (javascript-typescript)`**, **`Analyze (actions)`**: CodeQL. It runs
  from GitHub's *default setup* (Settings → Code security → Code scanning), not from a workflow file, on
  pull requests, pushes to `main` and weekly. Do not add a `codeql.yml`: GitHub rejects results from an
  advanced workflow while default setup is on. Require these checks once they appear on a pull request.

Remove the per-job entries (`Lint and types`, `Tests and coverage`, …) once `ci-ok` is required.

A documentation-only pull request skips the build, test and container jobs and still reports `ci-ok`. The
filter only skips what a change cannot affect: any file outside `docs/`, `*.md` and `LICENSE` runs the whole
suite, and every push to `main` runs it unfiltered.

## Releases

Pushing a `v*.*.*` tag publishes images only if the tagged commit is on `main` **and** its `ci-ok` check
succeeded. Tag `main` after merging; a tag on a feature branch is refused.

## Workflow security

- Every `uses:` is pinned to a commit SHA with the version in a comment; Dependabot keeps them current.
- Checkouts do not persist credentials (`persist-credentials: false`), except where a job must push.
- Untrusted values (branch names, PR text) are passed through `env:`, never interpolated into scripts.
- `zizmor` and `actionlint` (with shellcheck, `uvx --with shellcheck-py --from actionlint-py actionlint` locally) run on every change; intentional exceptions live in `.github/zizmor.yml`.
- Enable **push protection** under Settings → Code security so secrets are rejected before they land;
  the gitleaks job is the backstop for commits that get through.

## Speed budget

Pull-request checks should finish in about 6 minutes and never take more than 12; a slow check is a bug,
not a cost of doing business. What keeps them fast without dropping coverage of behaviour:

- **Parallel backend tests.** CI runs `pytest -n 4`. Every database test creates its own schema, so workers
  never share state. Run `uv run --directory backend pytest -n 4` locally for the same speed-up.
- **Sharded browser tests.** The Chromium suite is split into two runners (`--shard=N/2`).
- **Caches.** uv, pnpm, Playwright browsers and the mypy cache are restored between runs.
- **Hard limits.** Every job has a tight `timeout-minutes`, each backend test has a 60 s `timeout`, and
  Playwright has a `globalTimeout` and a single retry, so a hang or a flake cannot stretch a run.

## Coverage policy

- **Total coverage is a ratchet.** `fail_under` in `backend/pyproject.toml` and `coverage.thresholds` in
  `frontend/vite.config.ts` sit just under the measured baseline. When coverage rises, raise them in the same
  change; never lower them to make a build pass, add tests instead.
- **New code is held to a higher bar.** Pull requests must cover at least 85% of the backend lines they
  change (`diff-cover`), so a growing codebase cannot dilute its own coverage.
- Reports are uploaded as artifacts (`backend-coverage`, `frontend-coverage`) and summarised on the run page.

## Static checks

Lint rules are chosen to catch bugs, not to enforce taste:

- **Backend (ruff):** besides the default correctness and style rules, `S` (security: injection, weak
  crypto, swallowed exceptions), `ASYNC` (blocking calls in async code), `SIM`, `PERF`, `RET` and `PT`
  (pytest style). `assert` is allowed in tests only; in `src` use `require_present()` from
  `cookfully.domain.common`, which still fails under `python -O`. Catch-and-ignore must log.
- **Frontend (ESLint):** `jsx-a11y` (labels, focusable interactive elements, alt text) and
  `no-floating-promises` / `no-misused-promises`. Mark deliberate fire-and-forget with `void`. A rule may be
  disabled on one line only with a reason (`// eslint-disable-next-line rule -- why`).
- **Changed lines, frontend:** the unit job reports how much of the changed frontend code Vitest covers
  (`diff-cover`, 85%). It warns instead of failing because Playwright-only coverage is not counted;
  flip `FRONTEND_DIFF_COVERAGE_BLOCKING` in `frontend.yml` to make it a gate.

### Local hooks (optional)

`lefthook.yml` runs the quick checks on staged files before a commit and the unit tests before a push:

```text
pnpm --dir frontend install
pnpm --dir frontend exec lefthook install      # once per clone
```

## Dependency vulnerabilities

Advisories change daily, so they must not block unrelated work. Only *production* dependencies gate a
change, and only when a manifest or lockfile changes. Build-time tooling (`shadcn`, ESLint, Vite, …) is
reported daily instead. Dependabot opens grouped weekly updates.

## Visual baselines

See `frontend/e2e/README.md`. CI skips pixel comparisons, with a warning, until `-linux.png` baselines are
committed by the **Update visual baselines** workflow.

## Running the same checks locally

`scripts/verify.sh` is the full release gate. The quick equivalents are listed under *Commands* in
`AGENTS.md`.
