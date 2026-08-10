# Dependencies, licenses, and updates

The checked-in `backend/uv.lock` and `frontend/pnpm-lock.yaml` are the authoritative resolved-version
inventories. `artifacts/sbom.json` is the generated CycloneDX 1.6 view of both lockfiles, including
runtime, optional, development, transitive, and platform-specific packages.

## Verified inventory

Generated on 2026-08-10 with:

```powershell
uv run --directory backend python ../scripts/generate-sbom.py
uv run --directory backend python ../scripts/generate-sbom.py --verify-only
```

The verified document contains one Vigor & Vine root, 514 components (133 Python and 381 npm), 514
dependency nodes, and no component without a license declaration. The generator pins cdxgen 12.8.2,
normalizes the two app components under the product root, and fills the sole upstream metadata gap:
`mypy-extensions` 1.1.0 is MIT, linked to its versioned upstream license. Run the generator only in a
trusted checkout; `pnpm dlx` supplies its own `NODE_PATH` while launching cdxgen, so cdxgen's secure-
mode environment audit reports that launcher behavior even though the script removes an inherited
`NODE_PATH` and tells cdxgen not to install project dependencies.

Direct decisions and the currently locked versions are:

| Capability | Adopted dependency | Locked version | Declared license | Research decision check |
| --- | --- | ---: | --- | --- |
| API and validation | FastAPI / Pydantic | 0.141.1 / 2.13.4 | MIT / MIT | Matches typed OpenAPI-first transport |
| Persistence | SQLAlchemy / Alembic / psycopg | 2.0.51 / 1.19.1 / 3.3.4 | MIT / MIT / LGPL-3.0-only | Matches PostgreSQL system of record; retain LGPL notices/source offer obligations where distribution requires them |
| Background jobs | Celery / Redis client | 5.6.3 / 6.4.0 | BSD-3-Clause / MIT | Matches database-authoritative Celery design |
| HTTP boundary | HTTPX | 0.28.1 | 0BSD or BSD-3-Clause | Matches safe fetch/provider adapter |
| Recipe parsing | recipe-scrapers | 15.12.0 | MIT | Matches the narrow reuse decision; no Mealie/Tandoor code copied |
| Ingredient parsing | ingredient-parser-nlp | 2.7.0 | MIT | Matches deterministic-first parsing |
| Units | Pint | 0.25.3 | 0BSD | Corrects the earlier inventory's overly broad BSD-3-Clause label |
| Suggestions | OR-Tools | 9.15.6755 | Apache-2.0 | Matches bounded CP-SAT optimization |
| External tools | MCP Python SDK | 2.0.0 | MIT | Matches thin API/application adapter |
| Web UI | React / React Router | 19.2.8 / 7.18.2 | MIT / MIT | Matches client-rendered SPA decision |
| Server state | TanStack Query | 5.101.4 | MIT | Matches polling and mutation-cache decision |
| Forms/schema | React Hook Form / Zod | 7.85.0 / 4.4.3 | MIT / MIT | Matches exact input validation |
| UI primitives | Radix Dialog | 1.1.23 | MIT | Matches accessible unstyled primitives |
| Build/test | Vite / Vitest / Playwright | 8.2.1 / 4.1.10 / 1.62.1 | MIT / MIT / Apache-2.0 | Matches locked frontend toolchain |

The full inventory also contains weak/file-level licenses such as LGPL-3.0-only (psycopg) and
MPL-2.0 (for example axe-core and Lightning CSS), plus permissive MIT, BSD, Apache, ISC, 0BSD,
Python, W3C, CC0, and CC-BY metadata. No AGPL, GPL-2.0/GPL-3.0, or Commons Clause dependency is
accepted by the generator. This automated policy is a release guard, not legal advice; distribution
must still include the notices and source/relocation rights required by each shipped component.

USDA FoodData Central data is public domain under CC0. Mealie, Tandoor Recipes, and Immich are
objective implementation references only; none is copied, linked, or packaged as an application
dependency. Mealie and Tandoor's application licenses therefore do not become Vigor & Vine's license,
but their ideas must still be independently implemented. Optional structured-provider SDKs are not
dependencies; provider calls use the generic HTTP boundary and remain disabled by default.

## Update policy

- Run vulnerability audits at least monthly and for every release: `uv run --directory backend
  pip-audit` (with the release environment) and `pnpm --dir frontend audit --audit-level high`.
- Review ordinary dependency updates at least quarterly. Review supported USDA releases at least
  every 90 days, but import and activate reference data through its separate explicit lifecycle.
- Start from clean lockfiles. Use `uv lock --upgrade` or a named `uv lock --upgrade-package`, and
  `pnpm --dir frontend update` or a named package update. Never edit resolved versions by hand.
- Patch/minor updates still require lockfile review, vulnerability and license checks, backend/frontend
  gates, Docker builds, and SBOM regeneration. Treat a changed license, maintainer/source, native
  artifact, or unexplained transitive expansion as a blocking review item.
- Major updates require an explicit design/compatibility review. Python, FastAPI/Pydantic,
  SQLAlchemy/Alembic/psycopg, Celery/Redis, React/Router, Vite, MCP, and Compose/PostgreSQL upgrades
  also require migration, API-contract, backup/restore, and production smoke evidence.
- Any update to recipe-scrapers, ingredient-parser-nlp, Pint, OR-Tools, Pydantic decimal behavior,
  PostgreSQL numeric handling, or USDA mappings must pass the fixed 50-recipe nutrition corpus,
  correction precedence, exact plan totals, grocery aggregation, and suggestion corpus unchanged or
  carry an approved benchmark/version change.
- Regenerate `artifacts/sbom.json`, run `--verify-only`, and review the SBOM diff before committing the
  lockfiles and artifact together. The generator fails on missing/unexpected license metadata,
  direct-license drift, or unapproved strong-copyleft/Commons-Clause terms.
- Deploy only the reviewed revision. Before upgrade, create and verify a backup and ledger head;
  follow `docs/self-hosting.md`. Roll back lockfiles/images only when schema compatibility is proven,
  otherwise restore into a clean target and replay the current ledger.

Urgent exploited vulnerabilities may shorten review time but do not waive exact-decimal, contract,
restore, or provider-degraded safety gates. If a safe update cannot be completed immediately, disable
or isolate the affected optional surface and record the temporary operational control.
