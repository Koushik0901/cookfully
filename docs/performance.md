# Reference Performance Profile

## Result

The 2026-08-10 reference run passed every latency budget. These are local reference-profile results,
not a claim about every deployment or a comparative claim against another project. Raw evidence is in
[`artifacts/performance-report.json`](../artifacts/performance-report.json).

| Path | Budget p95 | Run 1 p50 / p95 / max | Run 2 p50 / p95 / max | Run 3 p50 / p95 / max | Worst p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10,000-recipe library read | 500 ms | 64.597 / 79.124 / 94.587 ms | 67.394 / 75.811 / 100.170 ms | 66.840 / 72.343 / 87.592 ms | 79.124 ms |
| 10,000-recipe title search | 500 ms | 36.910 / 45.309 / 50.607 ms | 37.473 / 42.510 / 55.864 ms | 37.013 / 42.906 / 71.512 ms | 45.309 ms |
| Mutation in a 50-entry plan | 500 ms | 42.370 / 49.386 / 66.045 ms | 42.016 / 52.062 / 176.266 ms | 42.243 / 47.171 / 62.092 ms | 52.062 ms |
| Import/job acknowledgement | 1,000 ms | 19.116 / 22.964 / 24.922 ms | 18.400 / 23.558 / 33.534 ms | 17.684 / 25.668 / 36.491 ms | 25.668 ms |
| Job polling | 500 ms | 8.592 / 9.689 / 22.445 ms | 8.252 / 10.717 / 39.416 ms | 8.369 / 10.387 / 19.297 ms | 10.717 ms |
| Grocery regeneration from 50 entries | 500 ms | 46.109 / 51.267 / 176.366 ms | 40.534 / 47.112 / 177.368 ms | 43.215 / 48.899 / 123.333 ms | 51.267 ms |
| Feasible suggestion solve | 10,000 ms | 21.056 / 26.323 / 29.219 ms | 21.106 / 24.637 / 28.279 ms | 21.742 / 24.474 / 27.873 ms | 26.323 ms |

Each run used 10 unmeasured warmups followed by 100 measured observations. The performance test fails
if any individual run exceeds its p95 budget; reporting only an aggregate across runs is deliberately
not allowed.

## Reference environment

- Docker Desktop Linux engine, x86-64, containerized.
- API, worker, outbox, retention, PostgreSQL, Redis, and the benchmark runner shared CPU affinity
  `0-3`; container inspection confirmed the same four-core set for every measured backend service.
- Linux reported 7,977,076 KiB total memory (the configured 8-GiB Docker engine).
- Docker data and the repository were on the host's healthy Samsung NVMe SSD. The Linux VM exposes
  virtual block devices, so the report records the operator-verified storage class instead of
  misrepresenting the VM's rotational flags as physical-drive evidence.
- PostgreSQL and Redis were colocated with the API and one Celery worker. The benchmark used a
  disposable PostgreSQL schema and left active application data untouched.

## Dataset and measured boundary

The test bulk-seeds 10,000 deterministically titled recipes, including searchable needle rows, then
creates one resolved recipe with an ingredient, a current goal, and a 50-entry weekly plan. HTTP
measurements traverse FastAPI routing, authentication/session validation, request and response
validation, application services, SQLAlchemy, and PostgreSQL. They do not include a remote browser's
network latency or rendering time. The suggestion metric measures the deterministic OR-Tools domain
solver because suggestion execution is asynchronous; acknowledgement and polling are measured
separately through HTTP.

Repeated grocery runs perform real reconciliation and replace 50 persisted sources. Repeated plan
mutations use optimistic versions and idempotency keys. Repeated job acknowledgements persist a recipe,
authoritative job, outbox event, and idempotency response before returning HTTP 202.

Run the profile with configured local secrets:

```powershell
docker compose -f deploy/compose.yaml -f deploy/compose.performance.yaml --profile performance up --build -d postgres redis api worker outbox retention
docker compose -f deploy/compose.yaml -f deploy/compose.performance.yaml --profile performance build benchmark
docker compose -f deploy/compose.yaml -f deploy/compose.performance.yaml --profile performance run --no-deps --rm benchmark
```

The test is skipped outside this Compose profile so a developer laptop run cannot overwrite the
reference artifact with incomparable results.

## Interpretation and limits

The substantial margin is encouraging, but it is not unlimited headroom. The library path currently
performs repeated per-recipe nutrition lookups, title search uses a contains predicate, and the grocery
path rewrites sources on regeneration. Those choices pass at 10,000 recipes and 50 plan entries but
should be profiled again before increasing the supported scale, adding concurrent owners, or moving
PostgreSQL off-host. Maximum latency spikes were retained in the table rather than discarded.

Mealie and Tandoor Recipes establish useful self-hosted recipe-library and shopping-list patterns;
Immich establishes a much heavier self-hosted asset-processing reference. Their maintained user and
operator documentation does not provide an apples-to-apples benchmark using this dataset, boundary,
and hardware profile. It would therefore be unsound to claim this application is faster—or that their
database/search choices are worse—from these numbers. Conversely, copying their indexing, caching, or
worker topology without measuring this nutrition-first workload would also be unjustified. The local
decision is to retain reproducible budgets and raw results, and revisit the implementation when the
measured workload changes.
