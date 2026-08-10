# Dependency and License Inventory

The lockfiles are the authoritative resolved-version inventory. Major-version changes require review,
the relevant quality gates, and an unchanged nutrition-corpus result when calculation behavior may be
affected.

| Capability | Adopted dependency | Pinned range | License | Source/decision |
|---|---|---:|---|---|
| API and validation | FastAPI, Pydantic | `<1`, `<3` | MIT | Typed OpenAPI-first transport |
| Persistence | SQLAlchemy, Alembic, psycopg | `<3`, `<2`, `<4` | MIT / MIT / LGPL-3.0 | PostgreSQL system of record |
| Background jobs | Celery, Redis client | `<6`, `<7` | BSD-3-Clause / MIT | Durable worker with database authority |
| HTTP boundary | HTTPX | `<1` | BSD-3-Clause | Safe fetcher adapter |
| Recipe parsing | recipe-scrapers | `15.x` | MIT | Required reuse starting point |
| Ingredient parsing | ingredient-parser-nlp | `2.x` | MIT | Deterministic first pass |
| Units | Pint | `0.x` | BSD-3-Clause | Dimensional conversion |
| Suggestions | OR-Tools | `9.15.x` | Apache-2.0 | P4 bounded CP-SAT optimization |
| External tools | MCP Python SDK | `2.x` | MIT | P5 thin adapter |
| Web UI | React, React Router | `19.x`, `7.x` | MIT | Client-rendered application |
| Server state | TanStack Query | `5.x` | MIT | Polling and mutation cache |
| Forms/schema | React Hook Form, Zod | `7.x`, `4.x` | MIT | Exact input validation |
| UI primitives | Radix UI | `1.x` | MIT | Accessible unstyled primitives |
| Build/test | Vite, Vitest, Playwright | `8.x`, `4.x`, `1.x` | MIT / MIT / Apache-2.0 | Locked frontend toolchain |

USDA FoodData Central data is public domain under CC0. Mealie and Tandoor were evaluated but are not
copied or linked as application dependencies. Optional provider SDKs are not dependencies; provider
calls use the HTTP boundary and remain disabled by default.
