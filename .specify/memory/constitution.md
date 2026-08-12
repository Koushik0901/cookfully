<!--
Sync Impact Report
- Version change: template (unratified) -> 1.0.0
- Modified principles:
  - Placeholder Principle 1 -> I. Macro Goals Define the Product
  - Placeholder Principle 2 -> II. Nutrition Estimates Are Honest and Correctable
  - Placeholder Principle 3 -> III. AI Is Bounded, Structured, and Asynchronous
  - Placeholder Principle 4 -> IV. Self-Hosted Data Is Accessible by Design
  - Placeholder Principle 5 -> V. Reuse First, Then Deliver Professional Quality
- Added sections:
  - Product and Architecture Constraints
  - Development Workflow and Quality Gates
- Removed sections: none; template placeholders were replaced.
- Templates:
  - ✅ updated: .specify/templates/plan-template.md
  - ✅ updated: .specify/templates/spec-template.md
  - ✅ updated: .specify/templates/tasks-template.md
  - ✅ reviewed: .specify/templates/commands/ (directory not present)
  - ✅ reviewed: DESIGN.md (already aligned; no update required)
- Deferred items: none.
-->
# Cookfully Constitution

## Core Principles

### I. Macro Goals Define the Product
Every product capability MUST help a person plan, prepare, or evaluate real food against explicit
calorie and macro targets. The primary workflow is importing or creating a recipe, understanding its
nutrition, placing it in a meal plan, and seeing the effect on daily or weekly goals. Features for a
general-purpose recipe archive, social network, or broad lifestyle platform MUST NOT be added unless
they demonstrably improve that workflow. In-app conversational AI, photo-based macro recognition,
subscription-only services, and unnecessary multi-user complexity remain out of scope unless this
constitution is amended. Narrow focus protects the app from the clutter that motivated its creation.

### II. Nutrition Estimates Are Honest and Correctable
Every recipe MUST have a best-effort per-serving calorie, protein, carbohydrate, and fat result once
processing completes; missing source nutrition is not a reason to omit the estimate. Each calculated
value MUST retain its provenance, assumptions, serving basis, and estimation status so the interface
and API never present inferred data as measured fact. Users MUST be able to override estimates, and a
manual correction MUST take precedence over later automated processing until explicitly reset.
Ingredient matching, unit conversion, serving rollups, and override precedence MUST be covered by
automated tests. The estimation pipeline MUST also be evaluated against 20-30 representative real
recipes before major UI investment or a v1 release decision. Rough data creates value only when its
uncertainty is visible and correction is durable.

### III. AI Is Bounded, Structured, and Asynchronous
AI MAY perform finite transformations such as ingredient parsing and reference-food disambiguation;
it MUST return schema-validated structured output and MUST NOT become an in-app chatbot or make
unreviewable open-ended decisions. AI and other expensive nutrition work MUST run outside interactive
save/import requests through observable background jobs. Jobs MUST be retry-safe and idempotent, and
successful results MUST be cached by stable inputs so unchanged recipes are not processed repeatedly.
Deterministic methods MUST be preferred when the problem is deterministic: meal suggestions MUST use
constraint solving or explicit search rather than per-request LLM reasoning. This boundary keeps the
app responsive, predictable, affordable, and testable.

### IV. Self-Hosted Data Is Accessible by Design
The complete application MUST be deployable and usable without a recurring product subscription, and
the user MUST retain control of recipes, goals, plans, estimates, and corrections. Core capabilities
MUST be modeled as stable structured data and exposed through a documented API; the MCP surface MUST
compose those same application services rather than create a second source of business logic. Data
MUST support backup and portable export, and loss of an optional external AI provider MUST degrade
processing visibly without corrupting stored recipes or blocking unrelated manual workflows. Secrets
and personal nutrition data MUST stay server-side and MUST NOT appear in logs or client bundles.

### V. Reuse First, Then Deliver Professional Quality
Before implementing a solved capability, the plan MUST evaluate maintained open-source options and
record whether to adopt, adapt, or reject them. URL import MUST begin with `recipe-scrapers`, nutrition
matching MUST begin with USDA FoodData Central, and ingredient parsing MUST study proven Mealie or
Tandoor approaches unless documented evidence justifies another choice. The fork-versus-fresh decision
for the overall app MUST be resolved through a time-boxed technical spike before architecture is
locked. Reuse does not lower the quality bar: user-facing work MUST follow `DESIGN.md`, remain calm and
nutrition-first, support responsive and accessible interaction, and surface loading, empty, partial,
estimated, and failed states explicitly. Adopted dependencies MUST have compatible licenses and pinned,
reviewable versions.

## Product and Architecture Constraints

- The default product scope is a single user or small household; broader tenancy requires an explicit
  specification and constitution review.
- The baseline architecture is a Python API service suited to `recipe-scrapers`, nutrition tooling,
  and optimization; PostgreSQL is the system of record; a modern reactive web client consumes the API;
  and durable background workers isolate nutrition processing. Alternatives are allowed only when the
  implementation plan documents a measurable advantage and migration cost.
- `Recipe`, `Ingredient`, `NutritionEstimate`, `UserGoal`, `MealPlan`, `MealPlanEntry`, and
  `GroceryList` are first-class domain concepts. Nutrition provenance and manual overrides MUST NOT be
  hidden in opaque blobs.
- Reference data, model/provider calls, and job-queue integrations MUST be isolated behind explicit
  interfaces with timeouts, failure states, and test substitutes.
- The UI MUST use the tokens and component guidance in `DESIGN.md`. Macro colors MUST remain consistent,
  but color alone MUST NOT communicate status or meaning.
- Every feature specification MUST identify its calorie/macro-goal contribution, estimation and data
  integrity effects, API/MCP exposure, reused components or dependencies, and explicit non-goals.

## Development Workflow and Quality Gates

1. Specifications MUST define independently testable user journeys and measurable, technology-neutral
   outcomes. Assumptions and exclusions MUST be explicit.
2. Plans MUST pass the Constitution Check before research and again after design. Any exception MUST be
   recorded in Complexity Tracking with evidence and a rejected simpler alternative.
3. Work involving nutrition data, goal totals, grocery aggregation, API contracts, background jobs, or
   external-service boundaries MUST include automated unit, contract, and/or integration tests at the
   appropriate level. Critical user journeys MUST have end-to-end verification.
4. Nutrition pipeline work MUST use representative fixtures covering missing quantities, ambiguous
   foods, unit conversions, serving changes, provider failures, retries, cache invalidation, and manual
   overrides. Accuracy findings MUST distinguish measured errors from unsupported assumptions.
5. UI work MUST be checked at desktop and narrow mobile widths for keyboard access, readable contrast,
   overflow, loading/error/empty/estimated states, and consistency with `DESIGN.md`.
6. Before merge, required format, lint, type, test, and build checks MUST pass. Documentation, API/MCP
   contracts, migrations, deployment configuration, and data export/backup guidance MUST be updated in
   the same change when affected.
7. New complexity, paid dependencies, telemetry, or external data transfer MUST be justified and called
   out for review. Private data MUST use the minimum necessary scope and retention.

## Governance

This constitution is the highest-priority project guidance. Feature specifications, implementation
plans, task lists, design decisions, and reviews MUST demonstrate compliance. When another project
document conflicts with it, this constitution governs until an amendment resolves the conflict.

Amendments require a written proposal describing the changed rule, motivation, affected artifacts,
migration or compatibility impact, and validation plan. Approval by the project owner is required
before the amendment is adopted. The amendment MUST update dependent templates and guidance in the
same change, and the Sync Impact Report MUST record all propagated or deferred work.

Versions follow semantic versioning: MAJOR for removal or incompatible redefinition of a principle or
governance rule; MINOR for a new principle or materially expanded mandatory guidance; PATCH for
clarifications that do not change obligations. The ratification date remains the date of first adoption;
the last-amended date changes with every approved amendment.

Every feature plan MUST run the Constitution Check, and every code review or release review MUST verify
applicable gates with evidence. A temporary exception requires project-owner approval, an explicit
expiry or follow-up issue, and a documented reason the compliant path is presently impractical.

**Version**: 1.0.0 | **Ratified**: 2026-08-09 | **Last Amended**: 2026-08-09
