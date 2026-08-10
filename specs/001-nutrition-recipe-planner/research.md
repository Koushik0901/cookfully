# Phase 0 Research: Gym-Focused Recipe & Nutrition Planner

**Date**: 2026-08-09  
**Status**: Complete — no unresolved `NEEDS CLARIFICATION` items

## 1. Build Fresh; Reuse Narrow Components

**Decision**: Build a new nutrition-first application. Adopt permissively licensed libraries for
scraping and parsing; study Mealie and Tandoor behavior and tests, but do not fork or copy their
application code unless the project owner explicitly accepts the resulting license obligations.

**Rationale**: The time-boxed source spike inspected current upstream trees. Mealie at commit
`66afe5b` contains about 1,568 files, including 595 Python files, 454 Vue/TypeScript files, and 52
migration files. Tandoor contains about 1,675 files, including 409 Python files, 424 Vue/TypeScript
files, and 246 migration files. Their trees include extensive household/group permissions, sharing,
tags, cookbooks, localization, multi-user shopping, and other domains the product explicitly rejects.
Both application repositories are AGPL-derived; Tandoor also presents a Commons Clause selling
condition. Reworking those schemas and interfaces would preserve a large unrelated surface while the
nutrition estimate, provenance, goal, snapshot, and optimization models would still be new.

The current [Mealie repository](https://github.com/mealie-recipes/mealie) confirms its broad family
recipe-manager scope and AGPL license. The current
[Tandoor repository](https://github.com/TandoorRecipes/recipes) confirms its power-user breadth and
AGPL plus Commons Clause terms.

**Alternatives considered**:

- **Fork Mealie**: strongest FastAPI and import overlap, but household/group schema, Vue UI, AGPL
  obligations, and broad feature surface work against the constitution.
- **Fork Tandoor**: mature planning and shopping behavior, but Django/Vue coupling, 246 migrations,
  broad customization, and its additional license condition make reduction risk higher.
- **Backend fork with new UI**: still inherits the non-nutrition-first domain and license while losing
  much of the value of the original integrated frontend.

## 2. Python Runtime and Dependency Management

**Decision**: Target Python 3.13 and manage the backend with `uv`, a checked-in `uv.lock`, and bounded
major-version constraints. Upgrade to Python 3.14 only after all native dependencies have verified
wheels and the accuracy corpus passes unchanged.

**Rationale**: Python 3.14 is the newest bugfix line, while 3.13 remains in bugfix support through
2029, according to the [Python release page](https://www.python.org/downloads/). Python 3.13 gives a
long support runway with lower compatibility risk for OR-Tools and NLP packages. `uv` provides a
cross-platform lockfile and locked execution, documented in its
[project](https://docs.astral.sh/uv/guides/projects/) and
[locking](https://docs.astral.sh/uv/concepts/projects/sync/) guides.

**Alternatives considered**:

- **Python 3.14 immediately**: longer runway but unnecessary early native-wheel risk.
- **Poetry or pip-tools**: capable, but `uv` provides the desired environment, interpreter, and lock
  workflow with fewer tools.

## 3. API and Web Client

**Decision**: Use FastAPI/Pydantic/SQLAlchemy/Alembic for a versioned REST API and React 19.2 with
TypeScript and Vite 8.1 for a client-rendered SPA. Generate the TypeScript API client from OpenAPI.

**Rationale**: Python keeps scraping, parsing, reference matching, and optimization in one runtime.
FastAPI provides schema-derived OpenAPI and typed validation. The app does not need public SEO or
server-rendered pages, so a Vite SPA is simpler than a full-stack React framework. React's official
[version page](https://react.dev/versions) identifies 19.2 as current, and Vite documents supported
8.x releases and Node requirements in its [release policy](https://vite.dev/releases) and
[guide](https://vite.dev/guide/).

**Alternatives considered**:

- **Vue**: viable and familiar in both reference apps, but no reuseable upstream UI will be copied;
  React has stronger alignment with the chosen local tooling and component ecosystem.
- **Next.js**: adds server-rendering and deployment concepts without a product requirement.
- **Django**: mature batteries, but FastAPI better matches the explicit API-first, typed-contract
  posture and the original brief.

## 4. Durable Background Work

**Decision**: Run Celery 5.6 workers with Redis as broker, a PostgreSQL `processing_job` record as the
authoritative status, and a PostgreSQL outbox/reconciler for reliable publication. Tasks accept IDs and
input hashes, use late acknowledgement only when idempotent, and write results transactionally.

**Rationale**: FastAPI's own
[background-task guidance](https://fastapi.tiangolo.com/tutorial/background-tasks/) recommends a
larger queue tool for heavy multi-process work. Celery's current
[task documentation](https://docs.celeryq.dev/en/stable/userguide/tasks.html) explicitly requires
idempotency for safe redelivery, and its
[broker documentation](https://docs.celeryq.dev/en/latest/getting-started/backends-and-brokers/index.html)
lists Redis as stable with monitoring and remote control. A database job record prevents Redis from
becoming the source of product truth.

**Alternatives considered**:

- **FastAPI BackgroundTasks**: lacks durable retry and process isolation.
- **Dramatiq/Taskiq/RQ**: smaller APIs, but less operational maturity or weaker current documentation
  for the required retry, inspection, and redelivery semantics.
- **Database polling only**: fewer services but creates custom scheduling, locking, retry, and
  monitoring code.

## 5. Recipe Fetching and Import

**Decision**: Adopt `recipe-scrapers` as an HTML parser, not as the network security boundary. Build a
safe HTTP fetcher that enforces protocol, DNS/IP, redirect, size, content-type, timeout, and user-agent
rules, then pass the captured HTML and final source domain to `scrape_html`.

**Rationale**: The official [recipe-scrapers documentation](https://docs.recipe-scrapers.com/) says it
parses structured HTML, supports more than 655 sites, is MIT licensed, and expects callers to handle
fetching and network requests. Separating fetching also makes URL-import fixtures deterministic and
prevents server-side request forgery.

**Alternatives considered**:

- **Library-managed fetching**: simpler call site but insufficient control over redirects, internal
  addresses, response limits, and stored fixtures.
- **Custom scraper framework**: duplicates maintained site-specific and structured-data behavior.

## 6. Ingredient Parsing and Unit Conversion

**Decision**: Use `ingredient-parser-nlp` 2.7 as the deterministic first pass and Pint-compatible units
for dimensional conversions. Preserve original text and parser confidence. Require an explicit density
record or user assumption for volume-to-mass conversion. Invoke optional AI only for low-confidence or
unmatched lines.

**Rationale**: The package's
[official guide](https://ingredient-parser.readthedocs.io/en/latest/tutorials/index.html) exposes
amounts, units, names, preparation, comments, purposes, confidence, and optional Foundation Food
matches. This covers more structured fields than a new regex parser while keeping every result
reviewable.

**Alternatives considered**:

- **Copy Mealie/Tandoor parsers**: introduces license and maintenance coupling.
- **LLM-first parsing**: violates deterministic-first and creates avoidable latency/cost.
- **Regex-only parser**: useful fallback but insufficient for ranges, alternatives, preparation, and
  unit flags.

## 7. Nutrition Reference and Matching

**Decision**: Require versioned USDA Foundation Foods and SR Legacy bulk datasets for P1 automated
local matching. Expose release identifiers, dates, attribution, license, and installation state;
review supported releases at least every 90 days; and require explicit operator import and activation.
Activation never silently rewrites existing estimates. If either required dataset is missing,
automated reference matching is visibly unavailable while source-provided and manual nutrition remain
usable. Offer an opt-in FoodData Central API fallback for branded foods and cache selected records
locally with source release metadata. Rank candidates deterministically by normalized name, aliases,
data type, and preparation; send only ambiguous candidate lists—not personal goals or full
libraries—to an optional AI disambiguator.

**Rationale**: The official [FoodData Central API guide](https://fdc.nal.usda.gov/api-guide/) exposes
food search/detail endpoints and states the data is CC0. A local generic-food corpus makes the core
pipeline self-hosted and repeatable while optional branded lookup improves coverage.

**Alternatives considered**:

- **Remote API only**: lower setup cost but introduces rate, availability, privacy, and reproducibility
  dependencies.
- **Ship all branded data by default**: much larger footprint with limited benefit for recipe
  ingredients.
- **LLM-generated nutrient values**: untraceable and unsuitable as a reference source.

## 8. Optional AI Boundary

**Decision**: Define one provider-neutral structured-transformation port with JSON-schema inputs and
outputs for ingredient parsing fallback and food-candidate disambiguation. Disable it by default. Cache
results by provider, model, schema version, and normalized input hash; reject invalid output and retain
the deterministic partial result.

**Rationale**: This makes provider choice a deployment concern and preserves useful core behavior with
no paid provider. It also constrains transmitted data to the minimum necessary input.

**Alternatives considered**:

- **Choose one provider as a core dependency**: conflicts with self-hosted/no-subscription goals.
- **Local generative model in v1**: materially increases image size, RAM, hardware variance, and
  operational support before deterministic baseline accuracy is known.

## 9. Meal Suggestion Solver

**Decision**: Use OR-Tools CP-SAT in P4. Scale nutrition values to integers, model servings as bounded
decision variables, express exclusions and repetition as hard constraints, minimize weighted calorie/
macro deviation plus repetition penalties, and impose a solver time limit with best-found results.

**Rationale**: OR-Tools identifies CP-SAT as its primary constraint-programming solver in the official
[constraint optimization guide](https://developers.google.com/optimization/cp), and current Python
bindings are documented in the [Python reference](https://or-tools.github.io/docs/python/index.html).
This is an explicit optimization problem, not a language-generation problem.

**Alternatives considered**:

- **Greedy heuristic**: simple baseline and fallback, but can miss feasible combinations.
- **PuLP/MILP**: readable linear models, but CP-SAT handles discrete servings and logical variety
  constraints naturally without an external solver.
- **LLM suggestions**: cannot guarantee arithmetic or constraint adherence.

## 10. API and MCP Boundaries

**Decision**: Make `/api/v1` OpenAPI the canonical transport contract. Implement P5 MCP Streamable
HTTP using the official Python SDK 2.x as a thin adapter over the same application commands and
queries. Use read/write token scopes and require idempotency keys on mutating external operations.

**Rationale**: The [official MCP SDK documentation](https://modelcontextprotocol.io/docs/sdk) lists the
Python SDK as Tier 1, and the [Python SDK guide](https://py.sdk.modelcontextprotocol.io/) documents
tools, resources, and Streamable HTTP. Sharing services prevents business-rule drift.

**Alternatives considered**:

- **MCP calls the REST API internally**: duplicates authentication and serialization hops.
- **MCP-specific business logic**: violates the constitution.
- **stdio only**: convenient locally but difficult to deploy securely beside a self-hosted server;
  a small optional stdio-to-HTTP bridge can be added later.

## 11. Persistence, History, and Media

**Decision**: Use PostgreSQL 18 typed relational tables, UUIDv7 identifiers, optimistic version
columns, and immutable nutrition snapshots on meal entries. Store only flexible source metadata and
audit details as JSON; calories, macros, serving bases, statuses, and relations remain typed columns.
Store images and backup archives in a dedicated volume with content hashes and database metadata.

**Rationale**: PostgreSQL 18 is supported through 2030 according to its
[versioning policy](https://www.postgresql.org/support/versioning/) and provides native `uuidv7()`.
Snapshots prevent a later recipe edit from silently rewriting historical plan totals.

**Alternatives considered**:

- **SQLite**: simpler single-process start, but durable workers, concurrent jobs, reference search,
  and a separate MCP/API process would create avoidable locking and migration limits.
- **Store images in PostgreSQL**: simpler backup boundary but adds database bloat and inefficient
  serving; manifest-backed media keeps backups complete.

## 12. Authentication and Secrets

**Decision**: Bootstrap one owner account; use Argon2id password hashes, server-side revocable sessions
behind HttpOnly SameSite cookies, CSRF protection for browser mutations, and separately scoped API/MCP
tokens stored only as hashes. Support reverse-proxy TLS and trusted-forwarded-header configuration.

**Rationale**: Even a single-user self-hosted app can be exposed beyond localhost. Authentication is
small compared with the impact of exposing nutrition history, imports, and mutating tools.

**Alternatives considered**:

- **No authentication/local-network trust**: unsafe default and difficult to correct after clients
  depend on anonymous endpoints.
- **Full multi-user/OIDC in v1**: unnecessary scope; can be added behind the same owner/session port.

## 13. Verification Strategy

**Decision**: Require domain unit/property tests, PostgreSQL/Redis integration tests, OpenAPI and MCP
contract tests, worker redelivery/idempotency tests, frontend component/accessibility tests, and
Playwright critical-journey tests. Version 50 captured public recipe pages with trusted nutrition,
expected import fields, expected parse/match classifications, and measured error reports. Maintain a
stable 30-recipe primary subset for the constitutional gate and 20 additional extension/stress cases.
Gate median absolute percentage error at 20% for calories and 25% for protein, carbohydrates, and fat,
using the nutrient-specific near-zero floors and absolute-error reporting defined by SC-002.

**Rationale**: The hardest failures cross parser, reference match, unit conversion, yield, correction,
and aggregation boundaries. Layered fixtures locate the error instead of reporting only a final macro
difference.

Coverage is the lower of quantified matched-mass coverage and resolved non-optional ingredient-count
coverage; a missing denominator yields zero. This prevents unquantified or unmatched ingredients from
disappearing from the completeness gate.

**Alternatives considered**:

- **End-to-end tests only**: too slow and poor at explaining nutrition errors.
- **Mock all external boundaries**: misses actual parser, database, broker, and contract behavior.

## 14. Backup and Export

**Decision**: Provide two distinct artifacts: a disaster-recovery backup containing database dump,
media, manifest, versions, checksums, and an erasure-ledger cursor; and a documented portable JSON/ZIP
export containing domain records and media references. Store the content-free, hash-chained erasure
ledger on an independently preserved volume, replicate it with the backup set, and never overwrite it
during restore. Restore stages into a temporary namespace, validates checksums, schema compatibility,
and ledger continuity, replays every erasure after the backup cursor, then swaps or imports
transactionally.

**Rationale**: A raw database dump is reliable for restoring the app but not portable; a domain export
is portable but should not replace a tested operational backup.

**Alternatives considered**:

- **Database dump only**: omits portability and can omit media if operators misunderstand volumes.
- **JSON export only**: slower and less exact for full disaster recovery.

## 15. Exact Decimal and Rounding Boundary

**Decision**: Use PostgreSQL fixed decimals with six fractional places for nutrients and ingredient
quantities and three for servings. Pydantic/OpenAPI/MCP/export schemas expose canonical decimal strings.
Use round-half-up and quantize plan-entry calories to 1 kcal and macros to 0.1 g before aggregation.

**Rationale**: Decimal strings avoid JavaScript/binary-float drift, while aggregating the same values
shown per entry makes meal/day/week totals and target differences exactly reproducible.

**Alternatives considered**:

- **JSON numbers plus UI formatting**: simpler clients but transport and runtime rounding can drift.
- **Aggregate raw values and round only totals**: mathematically precise but displayed entries may not
  add to the displayed total, contradicting SC-006.

## 16. Recipe Lifecycle and Erasure

**Decision**: Archive is reversible and removes recipes from active discovery. Restore reactivates the
prior usable state when the input hash still matches, otherwise returns `stale`. Permanent deletion
requires an archived recipe plus confirmation, supersedes active jobs, deletes recipe-owned records,
detaches immutable historical plan and grocery provenance, and appends a content-free monotonic
erasure record. Each record carries the stable erased subject identifier, scope, timestamp, previous
record hash, and cursor. Restore must fail closed if the current independent ledger is missing or
discontinuous and must replay all records newer than the backup cursor before activation. A record is
retained until all backups predating it have rotated out plus 30 days.

**Rationale**: This provides owner erasure without rewriting historical nutrition totals or obscuring
what a past grocery item represented.

**Alternatives considered**:

- **Prohibit deletion after planning use**: preserves history but fails the owner's data-control goal.
- **Cascade through history**: makes earlier totals and shopping records misleading or incomplete.
- **Rely on backup rotation alone**: cannot prevent an operator from restoring an older backup before
  its expiry and unintentionally resurrecting erased recipe-owned data.

## 17. Retention and Provider Privacy

**Decision**: Discard successful-import HTML immediately after extraction. Permit encrypted failed-
import HTML for at most 24 hours only when the owner enables diagnostics. Never persist raw provider
requests/responses. Reduce detailed job diagnostics after 30 days and delete safe codes/timestamps
after one year. Keep estimates and corrections until explicit erasure; document backup rotation lag.

**Rationale**: The policy retains reproducible normalized provenance and bounded operational evidence
without building a repository of recipe-page bodies, prompts, or personal provider payloads.

**Alternatives considered**:

- **Seven-day raw payload retention**: easier debugging but materially expands private-data exposure.
- **Operator-only configuration with no defaults**: creates unsafe and untestable deployments.

## 18. Polling and Bounded Retry Semantics

**Decision**: Acknowledge persisted recipe/job creation within one second. Poll every two seconds on a
visible job screen and every 15 seconds elsewhere. Time out attempts at 60 seconds; retry after 5
seconds, 30 seconds, 2 minutes, and 5 minutes; allow at most five attempts and a 15-minute terminal
deadline from initial acceptance.

**Rationale**: Authoritative PostgreSQL polling survives reloads and proxy configurations without the
operational complexity of an event-streaming channel. The fixed schedule is testable and leaves time
inside the terminal deadline for every attempt.

**Alternatives considered**:

- **Server-sent events with polling fallback**: better live progress but adds a second transport and
  proxy/connection lifecycle before it provides necessary product value.
- **Manual refresh or synchronous processing**: poor recovery and violates the asynchronous boundary.

## 19. Complete Contract Before Code Generation

**Decision**: The Phase 1 canonical contract includes recipe restore/permanent deletion, manual grocery
item create/delete, access-token management, suggestion status/result/acceptance, and an MCP meal-plan
read tool before implementation or generated-client tasks begin.

**Rationale**: Contract-first ordering prevents transport behavior from being invented during route
implementation and resolves the constitution-level gaps identified by `/speckit.analyze`.

**Alternatives considered**:

- **Reconcile at release-gate time**: allows backend, frontend, and MCP semantics to drift for most of
  implementation.
- **Document only the initial create endpoints**: leaves required lifecycle and acceptance flows
  untestable.
