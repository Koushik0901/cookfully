# Continuous integration

Workflows live in `.github/workflows/`. Each runs once per change (pushes to `main` and pull requests),
cancels itself when a newer push supersedes it, and has a job timeout.

| Workflow | Jobs | Gate |
| --- | --- | --- |
| `backend.yml` | **Lint and types** (ruff, mypy); **Tests and coverage** (pytest against the same `vchord-postgres` and Redis images as `deploy/compose.yaml`) | total coverage ≥ `fail_under`; changed lines ≥ 85% |
| `frontend.yml` | **Lint, types and build** plus a generated-API-client drift check; **Unit tests and coverage** (Vitest); **End-to-end** (Playwright on Chromium, with WebKit native-select in its own job) | coverage thresholds in `vite.config.ts`; every e2e assertion |
| `dependency-audit.yml` | `pip-audit` and `pnpm audit --prod` when a manifest changes; a daily full report | production dependencies only |
| `containers.yml` | compose files validate; each image builds (nothing is pushed) | when `deploy/**` or a lockfile changes |
| `publish-containers.yml` | build and push images to GHCR | release tags `v*.*.*` |
| `visual-baselines.yml` | regenerate and commit Linux screenshot baselines | manual |

Jobs inside a workflow run in parallel, so a lint or audit failure can no longer hide whether tests
pass.

## Coverage policy

- **Total coverage is a ratchet.** `fail_under` in `backend/pyproject.toml` and `coverage.thresholds` in
  `frontend/vite.config.ts` sit just under the measured baseline. When coverage rises, raise them in the same
  change; never lower them to make a build pass, add tests instead.
- **New code is held to a higher bar.** Pull requests must cover at least 85% of the backend lines they
  change (`diff-cover`), so a growing codebase cannot dilute its own coverage.
- Reports are uploaded as artifacts (`backend-coverage`, `frontend-coverage`) and summarised on the run page.

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
