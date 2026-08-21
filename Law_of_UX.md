# Cookfully Design & UX Constitution

> This is a product requirement, not aesthetic inspiration.
> Any agent changing user-facing UI must read this document and DESIGN.md first.

## 1. Product experience

Cookfully is a cooking and meal-planning application with quiet nutritional intelligence. Its job is to
help people move through a useful food loop:

**Discover → Understand → Plan → Prep → Shop → Cook → Review**

The product is for anyone who wants better control over food: home cooks, households, meal-preppers,
people with dietary needs, people pursuing health goals, and people who simply want dinner to be easier.
It must not assume that fitness, weight change, body composition, or macro optimization is the user's
identity.

The core principle is:

> **Food is the primary object. Nutrition is supporting intelligence.**

When food and numbers compete, lead with the dish, ingredients, cooking action, and context. Show nutrition
near the food when it helps a decision; disclose precision, provenance, and corrections when they become
useful.

## 2. Source of truth and experience personality

The live Home route at /app is the visual and density reference for the entire product. Every route can
change its composition for its task, but it inherits Home's:

- warm ivory canvas, near-white raised surfaces, deep herb anchors, soft mint attention fields, and
  restrained saffron/tomato accents;
- Afacad Flux Variable for expressive headings and recipe names, Inclusive Sans Variable for interface
  language and data;
- food-first imagery, deliberate fallback art, compact metadata, organic asymmetric corners, and calm
  surface depth;
- one useful next action per region, progressive disclosure, and meaningful above-the-fold content;
- responsive shell: quiet 112px desktop rail; compact top bar and aligned 72px mobile bottom nav.

Cookfully should feel warm, assured, appetizing, calm, capable, personal, and quietly intelligent. It should
not feel clinical, gym-coded, rustic, childish, luxury-theatre, database-like, spreadsheet-like,
enterprise-software-like, or visually empty.

## 3. The first question on every screen

Before designing a page or component, write down:

1. What is the user trying to accomplish?
2. What is the primary object?
3. What is the one primary action?
4. What information is required now?
5. What can be disclosed later?
6. What complexity can the system absorb?
7. What does success look like and where does the user go next?

Do not begin with "What information can we display?" A page exists to help someone do something.

## 4. Decision hierarchy

When principles conflict, choose in this order:

1. Comprehension
2. Task completion
3. Cognitive-load reduction
4. Accessibility and inclusive language
5. Familiar mental models
6. Responsive and performance quality
7. Visual hierarchy
8. Aesthetic polish
9. Delight
10. Novelty

Never sacrifice usability, honesty, accessibility, or cooking flow for visual novelty.

## 5. UX laws as implementation rules

### Cognitive load and working memory

Make the interface remember and calculate what the user should not have to. Use defaults, recognition,
grouped content, stable context, serving math, grocery consolidation, pantry deductions, nutrition
calculation, and clear labels. Do not expose database identifiers, infrastructure, provider details, or
nutrition provenance as primary content.

Recipe entry is structured: Basics → Ingredients → Method → Nutrition. Ingredients are rows and method
steps are numbered blocks, not giant "one per line" textareas.

### Hick's law and selective attention

Show one primary action and a small number of relevant choices. Search-first pickers, contextual
recommendations, and progressive disclosure are preferred to a wall of controls. Advanced nutrition,
provenance, import diagnostics, integrations, and system controls are available but not permanently loud.

### Jakob's law and familiar mental models

Search behaves like search, tabs like tabs, filters like filters, links like links, checkboxes like
checkboxes, drag-and-drop like direct manipulation, and back navigation predictably. Innovate in the
cooking value, not in basic affordances.

### Fitts's law

Frequent actions have at least 44×44px targets, 8px adjacent separation, and generous mobile placement.
This includes Add meal, Cook, Mark ingredient complete, Add grocery item, servings, and navigation. Icon
buttons always have an accessible name and a visible focus state.

### Proximity, common region, and similarity

Keep a control beside the thing it changes. Use surfaces, lines, and spacing only when they explain
ownership or grouping. Similar things look and behave similarly: recipe media has one shared shape/crop
contract; primary actions share one treatment; nutrient colors and status colors mean the same thing
everywhere. Do not cardify every sentence.

### Tesler's law

Complexity exists; the product should absorb it. Automatically parse and normalize recipe lines, scale
servings, match foods, calculate nutrition, consolidate groceries, identify repeated prep, and preserve
source/correction history. The user should not be forced to understand the implementation.

### Aesthetic-usability and peak-end

Polish builds trust only when the task is clear. Invest in type, food imagery, hierarchy, empty/loading
states, responsive composition, and small causal transitions. Give extra care to importing a recipe,
planning the first meal, generating a grocery list, completing cooking, and reviewing a week. Do not
celebrate every click.

### Doherty threshold

Acknowledge actions immediately. Fast actions update optimistically; slower work shows a shaped skeleton,
stage, progress, retry, and preserved context. Never leave a blank page or an ambiguous spinner.

### Von Restorff, serial position, and goal gradient

Emphasis is scarce. Keep primary navigation and actions salient, rare administration secondary, and
meaningful progress visible: meals planned, prep remaining, groceries checked. Do not invent streaks,
points, badges, or progress bars without a real user goal.

### Postel's law and active users

Accept reasonable URL, ingredient, unit, case, and whitespace variation; normalize internally; show
predictable results. Assume users will not read documentation. Teach through labels, defaults, useful
empty states, and contextual guidance.

### Occam's razor

When two solutions work equally well, prefer the simpler mental model. A user should be able to add a
recipe to Tuesday directly, not navigate a chain of implementation concepts.

## 6. Home contract

Home must feel like the kitchen's live control center and answer these questions in order:

1. What matters tonight? Editorial Tonight hero, useful recipe facts, one Start cooking action.
2. What is happening this week? Seven-day Week card with actual open/planned states and Next up.
3. What needs attention? Use soon pantry surface with honest expiry data and a route to act.
4. What could I cook next? Cook next recommendations with contextual reasons and recipe metadata.
5. What should I shop? Compact Grocery prompt, with full list one step away.

Use the compact Recently saved shelf as a bridge to the recipe box, never as a replacement for Recipes.
Do not add empty-height filler, anonymous progress marks, or generic headings such as "Context, not
guesswork". Prefer human labels: Tonight, This week, Use soon, Cook next, Recently saved, Grocery.

The greeting is dynamic by local time: morning, afternoon, and evening. Late night still uses Good evening;
Good night is not a product heading.

## 7. Page principles

### Recipes

Recipes is visual discovery and organization, not a database table. Put food media first, search near the
top, keep common filters to a few visible controls, and disclose the rest. Recipe cards use the shared
media ratio, curve, fallback art, and RecipeMetadata contract. A card exposes estimated time, servings,
calories, protein, carbs, and fat where known; it does not become a different height because one recipe
has more facts.

### Plan

Plan is the week of meals. Make days, meal slots, servings, leftovers, prep, and the next empty slot
obvious. Use direct manipulation or a search-first picker. Nutrition stays adjacent as a supporting
summary, never as a macro dashboard.

### Pantry

Pantry is the current shelf. Approximate inventory is useful. Use-by dates drive Use soon; when dates are
missing, explain how adding them unlocks attention rather than inventing urgency. Connect pantry items to
recipes and grocery actions.

### Grocery

Grocery is a practical shopping tool generated from the plan. Consolidate quantities, group items
meaningfully, allow personal additions, make rows checkable, preserve links back to the meals, and show
clear generating/dirty/completed states.

### Cook mode

Cook mode is focused and touch-friendly. The current step, relevant ingredients and quantities, timers,
progress, servings, wake-lock, previous/next actions, and completion state dominate. Hide unrelated
navigation and administration. The screen should work with wet hands and divided attention.

### Goals, nutrition, settings, and system

Begin with human intent and useful defaults. Show calculated targets for review; disclose manual macro,
micronutrient, provenance, AI, MCP, database, maintenance, and integration controls. These surfaces are
scannable indexes, not walls of unrelated inputs.

## 8. Progressive disclosure and visual hierarchy

Every screen should make five answers visible:

1. Where am I?
2. What is this for?
3. What should I look at first?
4. What can I do?
5. What is secondary?

Use type, scale, spacing, imagery, tonal surfaces, and restrained color. Do not solve hierarchy with
borders, badges, cards, or bright colors alone. Precision belongs in detail; discovery stays compact.

## 9. Content, states, and honesty

Use cooking-first, non-moralizing language: planned, remaining, needs review, estimated, manual,
outside target. Never use bad food, cheat, failure, guilt, or gym-bro language.

Represent loading, empty, partial, estimated, manual, stale, failed, and success states when the data
model permits them. Missing image, time, nutrition, pantry date, and source are explicit states with a
next action. Color never stands alone. Async status uses aria-live where appropriate.

## 10. Motion

Use motion to show cause and response:

- 160ms for hover/focus/feedback;
- 220ms for disclosure and sheets;
- 280ms for meaningful entrance;
- opacity and transform with ease-out; no layout animation or content jumps;
- useful signatures include recipe-image transitions, planning drops, serving recalculation, cooking-step
  progression, grocery completion, and skeleton-to-content;
- avoid flying headings, global fade-ins, animated backgrounds, parallax, and delayed actions;
- honor prefers-reduced-motion; on narrow mobile do not use page-entry transforms.

## 11. Accessibility and responsive behavior

Use semantic landmarks and heading order, persistent labels, keyboard operation, visible focus, 44px
targets, text alternatives, contrast, zoom/reflow, safe areas, and focus restoration for overlays.
Desktop uses a quiet rail; mobile uses aligned equal-width bottom-navigation hit areas and a compact top
bar. Mobile compositions are redesigned for cooking context, not merely stacked desktop grids.

## 12. Anti-patterns

Reject:

- a gym dashboard or macro-first home;
- a giant blank beige canvas;
- a page made from identical bordered rectangles;
- recipe cards with inconsistent heights or missing fallback art;
- a circular hero thumbnail visibly stitched into a surface;
- persistent filter/form walls before food;
- giant textareas for ingredients or method;
- anonymous seven-day lines without day meaning;
- decorative gradients, glass, rings, side stripes, or color without purpose;
- a generic component-library demo that does not feel like the Home kitchen.

## 13. Release review

At 1440×900 and 390×844, compare the change with /app and confirm:

- the next action is obvious;
- food leads and nutrition supports;
- shared tokens, curves, metadata, and fallback art are used;
- the content is useful above the fold;
- empty/loading/error/partial/stale/manual states are designed;
- mobile navigation, fixed UI, keyboard, focus, reduced motion, and safe areas work;
- no new raw color, one-off spacing, or local component variant was introduced without a documented reason.
