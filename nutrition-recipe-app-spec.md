# Cookfully product and experience spec

## 1. Vision

Cookfully is a polished self-hosted kitchen control center. It combines recipe saving, nutrition-aware
planning, pantry context, grocery generation, and focused cooking into one calm loop:

**Discover → Understand → Plan → Prep → Shop → Cook → Review**

The product is cooking-first. It should feel substantially more modern and useful than the dated,
database-like experience of many self-hosted recipe managers, while preserving their ownership and
practicality. The Home route at /app is the canonical expression of that direction.

### Product promise

When someone opens Cookfully, it should tell them:

- what matters tonight;
- what is happening in the week;
- what needs attention before it is forgotten;
- what could be cooked next and why;
- what needs to be bought or prepared.

The interface earns the name Home by being a living summary of the kitchen, not a launchpad into empty
utilities.

### Audience

Cookfully serves anyone trying to plan and eat better food: home cooks, households, meal-preppers,
people with dietary requirements, people managing health goals, and people who simply want less friction.
Nutrition supports those jobs, but the product is not a gym app, calorie counter, weight-loss coach, or
macro identity.

### Product principles

- **Food before figures.** Dish names, imagery, ingredients, and cooking actions lead.
- **Quiet intelligence.** Nutrition, serving math, pantry deductions, recommendations, and grocery
  consolidation are useful evidence close to the task.
- **Rough is better than absent.** Estimated values are useful when their estimate/coverage state is honest
  and corrections remain possible.
- **One useful next step.** Every surface has one clear action and progressive disclosure for the rest.
- **Self-hosted without second-rate UX.** Own the data and keep the experience polished, reliable, and
  understandable.
- **Structured AI, no in-app chatbot.** Optional providers perform bounded parsing/matching work; external
  agents can use the API/MCP surface for deeper reasoning.
- **Neutral and inclusive.** Never moralize food or presume a body-composition goal.

## 2. Home reference and design requirements

Home's visual language is the product-wide design language; DESIGN.md is the implementation authority.

1. **Intro:** warm ivory canvas, short kitchen/date eyebrow, dynamic Good morning/afternoon/evening
   greeting, one supporting sentence, unobtrusive desktop search.
2. **Tonight:** wide editorial hero with food image integrated into the surface, dark herb grounding,
   recipe title, time/servings/nutrition facts, availability note, and one Start cooking action.
3. **This week:** compact card with real day labels, open/planned states, current day, and Next up action.
4. **Use soon:** soft mint pantry surface with expiry attention and an honest empty state.
5. **Quick actions:** separator-led list for Plan tonight, Add a recipe, Add a grocery item.
6. **Cook next:** featured plus companion recipe cards with contextual reasons.
7. **Recently saved:** compact, consistent image shelf; never a second full recipe library.
8. **Grocery:** dark herb prompt that makes a list one action away.

Across every route, use Afacad Flux Variable for expressive headings, Inclusive Sans Variable for
interface/data, warm OKLCH tokens, 10px controls, 18px surfaces, 22px media, restrained shadows, and
occasional organic asymmetric corners. Recipe media/fallback art and RecipeMetadata are shared primitives.
At every recipe occurrence, show estimated total time, serving count, calories, protein, carbs, and fat
when available; make missing values explicit.

Mobile is a cooking context: compact top bar, 72px aligned bottom navigation, stacked task order, large
touch targets, no fixed-ui collisions, and a composition deliberately adapted from desktop.

## 3. Problems this solves

Existing recipe managers such as Mealie and Tandoor are useful references for ownership and breadth, but
the everyday experience can feel dated, dense, and database-first. Cookfully addresses:

1. recipes, plans, pantry, grocery, and cooking are disconnected;
2. the first screen does not tell the user what matters today;
3. imported recipes often have no honest nutrition estimate;
4. recommendations lack a reason or pantry/week context;
5. empty states repeat the absence instead of offering the next useful action;
6. recipe cards, media fallbacks, metadata, and responsive navigation drift between pages;
7. self-hosted tools often treat polished interaction as optional.

Cookfully does not copy any reference product wholesale. It adopts useful patterns and rejects breadth,
density, or visual choices that do not serve a cooking-first tool.

## 4. Goals and definition of done

- Import a recipe URL with ingredients, method, image, source, and a rough per-serving nutrition estimate
  even when the source provides no nutrition.
- Create and edit recipes with structured ingredient rows and numbered method steps.
- Save, search, filter, organize, archive, and view recipes with consistent food-first cards.
- Show time, servings, calories, protein, carbs, and fat in recipe, plan, suggestion, Home, and cooking
  contexts wherever data exists.
- Build a week of meals with direct, understandable day/meal placement, serving math, leftovers, and
  plan snapshots.
- Surface pantry use-by attention and connect it to recipe suggestions.
- Generate an aggregated, deduplicated grocery list from the plan, with pantry deductions and provenance.
- Provide focused cook mode with step progression, timers, wake-lock, checklist, serving scaling, and a
  meaningful completion state.
- Offer goal and nutrition guidance without making the default experience clinical or macro-first.
- Expose clean structured API/MCP actions so external agents can query and act without an in-app chatbot.
- Remain usable with provider degradation, estimated/partial data, manual corrections, and self-hosted
  backup/erasure requirements.

## 5. Feature scope

### Must have

- Recipe CRUD, structured ingredient/method editing, and URL import using recipe-scrapers.
- Ingredient parsing into quantity, unit, food, and preserved original text.
- Nutrition estimation: ingredient match → unit/gram conversion → per-serving rollup, cached and
  correction-aware.
- Recipe library with search, useful filters, image/fallback media, favorites/collections, archive/delete.
- Home dashboard with Tonight, This week, Use soon, Quick actions, Cook next, Recently saved, and Grocery.
- Weekly meal calendar with day/meal slots, serving adjustment, immutable nutrition snapshots, and
  planned/open/empty states.
- Grocery list generated from the current plan, aggregated and deduplicated, with manual items and clear
  generated-item placement semantics.
- Pantry inventory with use-by dates and ingredient-based search.
- Cook mode and real-time portion scaling.
- Owner settings, sessions/security, backup/erasure contracts, accessibility, and responsive QA.

### Should have

- Contextual suggestion engine (uses pantry, fits time, balances the plan, avoids repetition).
- Supported micronutrients with coverage/provenance.
- Pantry-to-recipe "what can I make?" discovery.
- MCP tools for goals, recipe search/mutation, plan entries, suggestions, pantry, and grocery.
- Shared prep/leftover intelligence and aisle grouping.
- Optional provider-neutral structured AI boundary, disabled by default.

### Explicit non-goals

- In-app conversational chatbot.
- Photo-based calorie or macro recognition.
- A social feed, public community, subscription service, or multi-user enterprise suite by default.
- Copying every Mealie/Tandoor taxonomy, admin surface, or feature simply for parity.
- A macro-first home, streak system, guilt language, or gym-bro visual identity.
- Decorative animation, gradients, glass, or dashboard modules with no useful action.

## 6. Inspiration and comparison posture

- **Mealie/Tandoor:** inspect current code and docs for import, recipe organization, planning, and
  self-hosted ownership patterns. Adapt only what fits Cookfully's narrower cooking-first flow.
- **Mob/Paprika:** study clipping, pantry, portion scaling, shopping, and cook-mode interactions.
- **Immich:** study self-hosted polish, maintained shared components, background processing, and honest
  degraded states.
- **Home itself:** the current localhost Home implementation is the strongest design reference. It is more
  authoritative than a screenshot or a generic trend.

Material comparisons and adopt/adapt/reject decisions belong in docs/inspiration-review.md.

## 7. Architecture and data contracts

- **Backend:** Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Celery, Redis, PostgreSQL.
- **Frontend:** React 19.2, TypeScript 5.x, Vite 8.1, React Router, TanStack Query, React Hook Form,
  Zod, Radix primitives, self-hosted variable fonts.
- **Media:** filesystem/object-compatible storage for recipe images, thumbnails, exports, and diagnostics.
- **Nutrition:** fixed-precision decimals, preserved serving basis and provenance, deterministic baseline
  matching, optional provider work behind a structured boundary.
- **Jobs:** heavy import, matching, and nutrition work runs as idempotent PostgreSQL-authoritative jobs;
  Redis is delivery/coordination, not the source of truth.
- **API/MCP:** expose structured data and actions; preserve exact decimal contracts, stale-version guards,
  lifecycle states, owner erasure, and immutable plan snapshots.
- **UI:** shared tokens/components are the only way to express color, typography, media, metadata, motion,
  navigation, and state. Raw feature CSS is not permitted.

## 8. Delivery order

1. Keep the Home contract and shared shell/tokens stable.
2. Harden recipe media, metadata, fallback art, and structured editor controls.
3. Finish the recipe-to-plan-to-pantry-to-grocery loop with explicit state handling.
4. Finish cook mode, serving scaling, prep/leftover intelligence, and contextual suggestions.
5. Add MCP/provider surfaces and advanced nutrition only behind progressive disclosure.
6. Validate desktop, 390×844 mobile, keyboard/accessibility, realistic imported recipes, provider
   degradation, backups, erasure, and performance before polish is considered complete.

The dependency-ordered work and contracts in specs/001-nutrition-recipe-planner remain authoritative for
backend lifecycle and release gates when they conflict with this product summary.

## 9. Resolved build decisions

- Build a fresh nutrition-first FastAPI/PostgreSQL application rather than fork a recipe manager.
- Reuse maintained import, parsing, unit, reference-data, optimization, and MCP dependencies.
- Use React/Vite with generated OpenAPI client contracts.
- Support one owner or a small household sharing one goal context; broad administration is out of scope.
- Keep optional AI provider-neutral and disabled by default; deterministic parsing/local matching remain the
  baseline and provider loss cannot block manual workflows.
- Keep nutrition evidence adjacent to food and useful actions; never let it dominate Home.
- Keep Home, DESIGN.md, Law_of_UX.md, and .impeccable.md synchronized when the visual reference changes.

## 10. Implementation status (2026-08-20)

### Complete or shipped

- Recipe CRUD, URL import, structured ingredient parsing, USDA matching, Atwater fallback, nutrition
  corrections, goals/profile, weekly planning, grocery generation, pantry CRUD/deductions.
- Auto-suggestion engine, supported micronutrients, MCP read/plan tools, cook mode, portion scaling.
- Owner-created foods, branded-food import, ambiguous-food picker, import duplicate merge, draft preview,
  PDF thumbnail attachment, provenance, optimistic feedback, focal-point/zoom metadata.
- Shared Home dashboard composition, quiet desktop rail, mobile top/bottom shell, RecipeMetadata semantic
  nutrition colors, deliberate RecipeFallbackArt, and responsive Playwright coverage.

### Known next priorities

1. Complete MCP suggestion, pantry, and recipe mutation tool coverage.
2. Enforce solver per-day diversity and consecutive-day avoidance.
3. Refine shopping aisle grouping and generated-item placement.
4. Add Docker worker/outbox health checks.
5. Continue visual audits of every route against the Home contract, especially editor, planner, grocery,
   and cook mode at 1440×900 and 390×844.

