# Project Spec: Gym-Focused Recipe & Nutrition Planner

## 1. Vision / Philosophy

Build a recipe manager and meal-planning app for one specific persona: someone actively managing body composition (cutting, bulking, or maintaining) who tracks calories and macros and wants their recipe/meal-planning tool to actually understand that goal — not a universal, everything-to-everyone recipe box like [Mealie](https://github.com/mealie-recipes/mealie) or [Tandoor](https://github.com/TandoorRecipes/recipes).

And we don't even have to build this from scratch. If it's better to take one of these apps like Mealie or Tandoor and just rework the specific parts I want and declutter some stuff to make it exactly how I want, that's still 100% better.

Core philosophy:
- **Narrow beats universal.** Every feature should serve "I have a calorie/macro target, help me hit it with real food." Features that don't serve that get cut, even if Mealie/Tandoor have them.
- **Rough beats missing.** A best-effort nutrition estimate on every recipe is more useful than a perfect estimate on none. Don't gate features behind "AI must be 100% accurate."
- **AI does structured work, not conversation.** No in-app chatbot. AI is used for specific, bounded processing tasks (parsing ingredients, estimating nutrition, matching to a reference database) that run once per recipe and get cached — not open-ended Q&A.
- **The app is a tool with an API, not a walled garden.** Expose clean structured data/actions (ideally as an MCP server) so the user's own external AI agent can do deeper reasoning on top of the app's data, instead of the app trying to build that reasoning in-house.
- **Reuse aggressively.** Don't rebuild solved problems (URL scraping, ingredient string parsing patterns) from scratch. Spend original engineering effort only where existing tools fall short — namely, nutrition-first data modeling and macro-aware meal planning. Reuse wholly or partially from existing open-source apps like [Mealie](https://github.com/mealie-recipes/mealie) or [Tandoor](https://github.com/TandoorRecipes/recipes).
- **Self-hosted, not subscription.** The polished paid apps in this space (see Section 3) are genuinely good, but the point of this project is to own the tool and the data without an ongoing subscription. Inspiration from their UX is welcome; their business model is not the goal.
- **Self-hosted doesn't mean second-rate.** Apps like Immich (see Section 3) prove a self-hosted tool can have professional-grade UI and architecture. That's the bar for this project, not "good enough for a personal project."

## 2. Pain Points With Existing Apps (Mealie / Tandoor)

These are the specific frustrations driving this project, based on hands-on use of Tandoor:

1. **UI is cluttered and dated.** Built to serve every possible recipe-management use case, which makes the everyday flow (import a recipe, check macros, add to plan) slower and busier than it needs to be.
2. **URL import gets ingredients/instructions/images great, but not nutrition.** When the source website doesn't provide nutrition info (most don't), the app just leaves it blank. No fallback estimation.
3. **No concept of personal calorie/macro goals.** Nothing in Mealie/Tandoor connects a recipe to "does this fit my day." No TDEE, no deficit/surplus target, no per-meal macro budget.
4. **No goal-aware meal planning.** Meal calendars exist, but nothing suggests what to eat based on remaining calories/macros for the day or week.
5. **Built for a general audience, not a gym/health-focused one.** Protein-forward, deficit/surplus-aware, macro-tracking workflows are not the default experience — they're afterthoughts at best.

## 3. Inspiration to Draw From

Recipe apps aren't the only place to look. Some of the best examples of what a polished, well-engineered self-hosted app can look like come from entirely outside the recipe/nutrition space — study those for UI and architecture, not just competitors in the same category.

### Paid recipe/meal-planning apps (for UX patterns)
- **Mob (Meal Planner and Recipes)** — subscription app worth studying for: weekly meal plans built around real-life cooking (not just a recipe archive), a smart shopping list that groups items by supermarket aisle, ingredient-based search ("what can I make with what I have"), adjustable portion sizes, a step-by-step cook mode that keeps the screen awake, and nutrition/macros surfaced directly on every recipe. That last point in particular is exactly the gap this project is trying to close relative to Mealie/Tandoor.
- **Paprika Recipe Manager** — worth studying for: clean ad-stripped web recipe clipping, offline-first local storage with cross-device sync, portion scaling with automatic unit conversion, a pantry feature that tracks what's on hand, grocery lists with custom/re-orderable aisle categories, and a "keep screen awake" cooking mode. Paprika is not gym/macro-focused, but its import and grocery-list UX is a good bar to aim for.

### Self-hosted apps with standout design, architecture, and AI (for the bigger picture)
- [**Immich**](https://github.com/immich-app/immich) (self-hosted photo/video manager, a self-hosted Google Photos alternative) — one of the best-designed self-hosted apps that exists, and worth studying on three fronts:
  - **UI polish:** timeline-based browsing with virtual scrolling that stays smooth across huge libraries, a full-screen asset viewer, and a maintained component library (`@immich/ui`) that keeps every screen visually consistent. Proof that "self-hosted" doesn't have to mean "looks like an admin panel."
  - **Architecture:** runs as separate Docker services — an API server, a dedicated machine-learning service, Postgres for data, and Redis-backed job queues for background work — so heavy processing (face recognition, semantic-search embeddings) never blocks the main app. This is a pattern directly worth copying: nutrition estimation and ingredient matching should run as background jobs through a queue, not inline in the request that saves a recipe.
  - **AI done right, not as a gimmick:** on-server ML (face detection, CLIP-based semantic search) runs quietly in the background and just makes search and browsing better — it's not a chat feature bolted on top. That's the exact posture this project wants for its own AI: structured, bounded, and invisible when it's working.
- General direction: it's fine, and encouraged, to bring in other well-regarded self-hosted projects (from the broader self-hosted ecosystem, not just recipe apps) as references for interaction design and engineering practice.

## 4. Goals — What "Done" Looks Like

- Import a recipe from a URL (same site coverage as Mealie/Tandoor) and get ingredients, instructions, image, **and a rough per-serving calorie/macro estimate**, automatically, even when the source page has no nutrition data.
- Set personal targets: maintenance/TDEE, daily calorie goal (deficit/surplus), and macro splits — at the day level and, if wanted, per-meal.
- Build a week of meals from saved recipes and see, at a glance, whether the week/day/meal is on target.
- Auto-generate a full week of meal suggestions from the recipe library that hits calorie and macro targets, with reasonable variety.
- Auto-generate a consolidated grocery list from the week's selected meals.
- All of the above exposed through a clean API/MCP surface so a personal AI agent (e.g. ChatGPT Codex, or Hermes Agent or OpenClaw or the user's own agent setup) can query and act on the data without a bespoke in-app chat feature.

## 5. Feature List (Prioritized)

### Must-have (v1)
- Recipe CRUD (manual entry)
- Recipe import from URL (reuse `recipe-scrapers` site coverage)
- Ingredient parsing → structured `{quantity, unit, food}` per line
- Nutrition estimation pipeline: ingredient → matched reference food → per-serving calorie/macro rollup, cached per recipe
- User goal profile: TDEE/maintenance, target calories, macro split (protein/carbs/fat), optionally per-meal macro targets
- Weekly meal calendar (assign recipes to days/meals)
- Daily/weekly totals vs. goal (calories + macros), visible at a glance
- Grocery list generated from the current week's planned meals, aggregated and deduplicated
- Manual override for any auto-estimated nutrition value (user corrects, correction is trusted going forward)

### Should-have (v2)
- Auto-suggestion engine: given remaining calorie/macro budget for a day or week, propose recipes/meals from the library that fit
- Micronutrient tracking (not just macros), where reference data supports it
- Basic variety/repetition constraints in auto-suggestions (don't suggest the same recipe 5 days running unless the library is small)
- MCP server exposing tools like: get current goals, get today's/week's totals, list recipes matching macro constraints, add recipe to plan, get grocery list
- Ingredient-based search ("what can I make with what I have") and a lightweight pantry tracker, inspired by Mob/Paprika

### Explicit non-goals (do not build)
- In-app chatbot / conversational AI interface
- Photo-based food/macro recognition (Cal AI-style) — deliberately out of scope
- Trying to match Mealie/Tandoor's full feature breadth (multi-cuisine categorization, extensive tagging systems, recipe books/sharing communities, etc.) unless it directly serves the goal-tracking use case
- Multi-user/social features, unless later decided otherwise — default assumption is single-user or small household use
- Subscription/paid-service model — this is a self-hosted alternative by design

## 6. What To Reuse vs. Build From Scratch

### Reuse
- **`recipe-scrapers` (Python library)** for URL import — this is what both Mealie and Tandoor use under the hood, covers 400+ sites. Use it directly as a dependency rather than reimplementing scraping.
- **USDA FoodData Central** as the nutrition reference database (free, ~2M entries including branded foods). Use their bulk download or API for ingredient-to-nutrition matching.
- **Mealie's or Tandoor's ingredient-string parsing logic** (unit/quantity extraction) as a reference implementation, or reused directly — worth reading their source for this narrow, well-solved piece even if the rest of the app diverges from their codebase.

### Build from scratch
- **Backend and data model**, designed nutrition-first from day one: `Recipe`, `Ingredient`, `NutritionEstimate`, `UserGoal`, `MealPlan`, `MealPlanEntry`, `GroceryList` as core first-class entities (not bolted onto a schema that wasn't designed for them).
- **Frontend**, since the whole point is a UI that doesn't feel like Tandoor's — with UX cues from Mob/Paprika, and design/architecture cues from Immich (see Section 3).
- **Nutrition estimation pipeline**: ingredient parsing (LLM-assisted structured extraction) → reference-database matching (LLM-assisted disambiguation, e.g. "kale" → raw curly kale) → unit-to-gram conversion → per-serving rollup. One-shot per recipe, result cached permanently, user-correctable.
- **Meal-plan auto-suggestion engine**: treat as a constraint-satisfaction/optimization problem over the recipe library against calorie/macro targets (e.g. via `OR-tools` or `PuLP` for an ILP/greedy approach) — not an ML model, and not something to outsource to an LLM per-request (too slow/expensive for what's fundamentally a search problem).
- **MCP server / API layer** exposing the app's data and actions as structured tools.

### On forking vs. rebuilding
Whether to fork Mealie/Tandoor directly and rework/declutter it, or build fresh while reusing their scraping/parsing pieces, is open — both are acceptable paths. The deciding factor should be practical: how much of Mealie/Tandoor's existing schema and UI can realistically be adapted to a nutrition-first, goal-aware model without fighting the codebase more than building fresh would cost. Evaluate this early, before committing to a direction.

## 7. Suggested Architecture

- **Backend:** Python (FastAPI), to sit naturally alongside `recipe-scrapers` and any Python-based nutrition-matching/optimization code (OR-tools, PuLP, pandas for the USDA dataset).
- **Database:** Postgres.
- **Frontend:** Modern reactive framework (React/Next.js or Vue) — final choice open, but should be decided before UI work starts.
- **AI processing:** LLM API calls (e.g. Claude) used narrowly for (a) ingredient-line parsing and (b) reference-food disambiguation/matching. Both are one-shot, cached, structured-output calls — not a chat feature.
- **Background processing:** follow Immich's pattern — run heavier processing (nutrition estimation, ingredient matching) as background jobs via a queue (e.g. Redis-backed) rather than blocking the request that saves/imports a recipe, so the app stays responsive while an LLM call is in flight.
- **Agent integration:** MCP server exposing the app's core actions/queries as tools, so external agents can plan, query, and act on the user's behalf without the app needing to host its own reasoning/chat layer.

## 8. Rough Roadmap & Effort (solo, part-time)

| Phase | Scope | Estimate |
|---|---|---|
| Foundation | Nutrition-first data model, recipe CRUD, URL import via `recipe-scrapers` | 2-3 weeks |
| Nutrition pipeline | Ingredient parsing, USDA matching, per-serving rollup, caching, manual override UI | 3-4 weeks |
| Goals & planning | TDEE/goal profile, meal calendar, daily/weekly totals vs. goal, grocery list generation | 1-2 weeks |
| Auto-suggestion engine | Constraint-based weekly meal suggestion against calorie/macro targets | 2-3 weeks |
| Agent integration | MCP server / structured API surface | 1 week |

**Total: roughly 9-13 weeks part-time** for a genuinely usable v1 covering must-have + should-have features.

**Recommended build order:** validate the nutrition estimation pipeline against 20-30 real recipes from the user's own recipe list *before* investing in UI polish — it's the piece the rest of the app depends on, and the biggest unknown.

## 9. Open Questions (to resolve before/during build)

- Frontend framework choice (React/Next.js vs. Vue vs. other)
- Fork Mealie/Tandoor and rework, or build fresh while reusing their scraping/parsing pieces (see Section 6)
- Single-user only, or lightweight household/multi-user support?
- Self-hosted only, or hosted option considered later?
- Which LLM provider/model for the ingredient-parsing and matching calls, and how to handle API cost at scale if the recipe library grows large?
- Exact MCP tool surface — start minimal (read goals, read/write meal plan, read grocery list) and expand based on real usage.
