---
name: Cookfully
version: 3.0
direction: Editorial kitchen utility
sourceOfTruth: Home at /app
defaultTheme: light
fonts:
  display: Afacad Flux Variable
  body: Inclusive Sans Variable
colors:
  canvas: oklch(0.985 0.007 92)
  surface: oklch(0.998 0.002 92)
  surface-muted: oklch(0.968 0.011 94)
  surface-high: oklch(0.932 0.020 96)
  ink: oklch(0.218 0.038 148)
  ink-muted: oklch(0.455 0.030 145)
  line: oklch(0.858 0.027 96)
  primary: oklch(0.405 0.126 148)
  primary-hover: oklch(0.350 0.118 148)
  on-primary: oklch(0.988 0.008 92)
  primary-container: oklch(0.880 0.100 138)
  accent: oklch(0.790 0.158 72)
  accent-soft: oklch(0.940 0.062 78)
  tomato: oklch(0.535 0.160 34)
  destructive: oklch(0.555 0.195 28)
  protein: oklch(0.610 0.125 244)
  carbohydrate: oklch(0.740 0.145 78)
  fat: oklch(0.800 0.145 92)
  fiber: oklch(0.560 0.105 145)
rounded:
  control: 10px
  surface: 18px
  media: 22px
  pill: 999px
spacing:
  unit: 4px
  page-mobile: 16px
  page-tablet: 28px
  page-desktop: 48px
---

# Cookfully design system

This is the authoritative interface contract. The live Home route at `/app` is the reference
implementation: it defines the visual language, density, component relationships, and emotional
register that every other route must inherit. A page may have a different task, but it must still
look like it belongs to the same kitchen.

## North star

Cookfully is a living kitchen control center: a cooking-first, self-hosted tool with quiet nutritional
intelligence. It should feel like a contemporary food publication made useful, not like a database,
fitness dashboard, or generic wellness SaaS.

- **People:** home cooks, households, meal-preppers, people with dietary requirements, and people who
  want balanced food without making nutrition their identity.
- **Jobs:** discover/save recipes, understand a dish, plan a realistic week, use the pantry, shop,
  cook, and review what happened.
- **Feeling:** warm, assured, appetizing, calm, capable, personal, and quietly intelligent.
- **Food first:** images, dish names, ingredients, and the next cooking action lead. Nutrition is useful
  evidence that appears close to the food, never the personality of the product.
- **One useful next step:** each region has one clear primary action. Secondary detail is disclosed when
  it becomes useful.

## Home-derived composition

Home answers five questions in scan order: what matters tonight, what is happening this week, what needs
attention in the pantry, what could be cooked next, and what should be shopped. Keep this order unless a
route's task makes a deliberate exception.

1. **Kitchen intro** — a short eyebrow (`Your kitchen · Thursday`), a dynamic greeting, one calm
   supporting sentence, and unobtrusive search on desktop.
2. **Tonight + This week** — a wide editorial hero beside a compact week card. The hero owns the first
   visual moment; the week card gives an actionable calendar summary.
3. **Use soon + Quick actions** — a pale-green pantry attention surface beside a quiet list of three
   useful actions. This is information density without dashboard noise.
4. **Cook next** — one featured recipe and two companion recommendations. Every suggestion has a reason,
   such as `A good next choice from your recipe box`, `Uses spinach from your pantry`, or `Ready in 20 min`.
5. **Recently saved + Grocery** — a compact four-item image shelf and a dark herb grocery prompt.

The page should use the ordinary desktop viewport rather than ending halfway down the screen. It may
continue below the fold when data warrants it, but never add height just to make a dashboard look full.

## Visual foundation

### Color roles

Use the front-matter tokens through CSS custom properties. Raw feature colors are prohibited. Pure white
and pure black are prohibited; the warm ivory canvas and herb ink are part of the brand.

- `canvas` is the page field; `surface` is a raised, readable region; `surface-muted` groups quiet
  secondary material; `surface-high` is a media/fallback field.
- `primary` is deep herb green for active navigation, the main action, confirmed completion, and the
  dark surfaces that anchor the page. `primary-container` is the soft mint selected/attention field.
- `accent` is saffron. Use it sparingly for discovery, a small state dot, or a food-forward highlight;
  it is never a second primary-action system. `tomato` is a food accent, not a general status color.
- `ink` and `ink-muted` are the default text colors. Strong contrast comes from hierarchy and imagery,
  not from black text.
- Nutrition uses one global semantic registry: protein blue, carbohydrate orange, fat golden yellow,
  fiber plant green, calories neutral ink. The category name is always present; color never carries
  meaning alone.
- Interface states are separate from nutrition: processing/info blue, partial/stale amber,
  confirmed/manual green, failed/destructive red. Pair every state color with text or an accessible name.

Maintain WCAG 2.2 AA contrast: 4.5:1 for normal text and 3:1 for large text, controls, icons, focus
indicators, and meaningful marks.

### Typography

Self-host the variable faces. Never use a third-party font CDN.

- **Afacad Flux Variable** for wordmark, greeting, page/section titles, recipe names, and display moments.
- **Inclusive Sans Variable** for body copy, buttons, labels, navigation, forms, metadata, and data.
- Use `font-variant-numeric: tabular-nums` for quantities and comparisons; do not use monospace as a
  visual shorthand for nutrition or technical credibility.

| Role | Desktop | Mobile | Weight | Use |
|---|---:|---:|---:|---|
| Display | 56/58 | 40/43 | 650 | Marketing or milestone moments only |
| Page title | 38/38 | 34/36 | 500 | One route title; Home greeting |
| Section title | 28/31 | 24/28 | 500 | Major module headings |
| Card title | 17–25/21–27 | 17–24/21–27 | 500 | Recipe, meal, and prompt titles |
| Body | 16/24 | 16/24 | 400 | Explanatory copy |
| Small | 14–15/20–22 | 14–15/20–22 | 400 | Metadata and helper text |
| Eyebrow/label | 12–13/16 | 12–13/16 | 500 | Short context labels; never all caps |

Headings use approximately `-0.015em` tracking; short eyebrows may use `0.02em`. Keep body lines
between 45 and 72 characters. Avoid making every label bold or every sentence a heading.

### Space, shape, and depth

The base unit is 4px. Approved rhythm is 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, and 96px.

- Tight internal groups: 4–12px. Related content and controls: 16–24px. Major module transitions:
  40–64px.
- Controls use a 10px radius and a 44px minimum target (48px for primary fields). Content surfaces use
  18px. Media uses 22px. Pills (`999px`) are reserved for filters, statuses, and compact categories.
- Home uses occasional organic asymmetry: the hero, pantry, recommendation, and grocery surfaces may
  have one larger corner (typically 56–72px) while the remaining corners stay 18–24px. This is a quiet
  food/editorial signature, not a license for random geometry.
- Use tonal contrast and a one-pixel line before reaching for shadow. Shadows belong to floating sheets,
  menus, and surfaces intentionally overlapping another plane. Never nest cards inside cards.
- Avoid glassmorphism, ornamental gradients, side stripes, rings, and decorative borders that do not
  clarify grouping.

## Application shell and responsive rules

### Desktop and tablet (768px and above)

- Use a fixed 112px warm-ivory rail. The rail is quiet: centered 20px icons, short visible labels,
  generous hit boxes, and a mint active field with a small saffron state dot. It must not compete with
  food imagery.
- The content area uses the remaining width with a readable maximum of 1440px, 48px desktop inset, and
  28px tablet inset. At wide monitors, fill useful width before increasing empty margins.
- Home's first dashboard grid is approximately 1.32fr / 0.68fr: the tonight hero is wide, the week
  card is compact. Preserve that visual priority rather than giving every column equal weight.

### Mobile (below 768px)

- Use a compact top bar with no heavy bottom rule, an 18px Afacad Flux wordmark, and a fixed 72px bottom
  navigation. Include safe-area padding. The navigation has five evenly distributed destinations: Home,
  Recipes, Plan, Grocery, More.
- Bottom-nav icons and labels are centered in equal-width, full-height hit areas. The active item uses the
  same mint field as desktop. Never allow icons, labels, or the More menu to collide or drift.
- Mobile is a cooking context, not a shrunk desktop. Stack modules in task order, let the hero become an
  image-led vertical surface, keep the week card and pantry attention readable, and move secondary
  actions into a sheet/menu when necessary.
- Do not use page-entry transforms on mobile; they create visible seams around the fixed navigation.
  Preserve opacity-only or no entrance motion when the viewport is narrow.
- The mobile Week view is a vertical agenda, not a seven-column canvas or horizontal card carousel. Empty
  days remain compact; days with meals reveal those meals; tapping a day opens its full editing view.

## Reusable component contracts

These are product patterns, not suggestions for one page. Reuse them before creating a local variant.

### `KitchenShell` / `RailNav` / `MobileNav`

Own the app frame, route-aware active states, keyboard focus, safe areas, and responsive transition. Labels
remain visible; icons supplement them. Settings, Foods, Goals, System, and account controls are utilities
and belong in the desktop rail's lower area or Mobile `More`, not in the five primary mobile slots.

### `PageIntro`

Accepts an optional eyebrow, one title, one sentence, and one action cluster. The Home variant uses the
dynamic greeting (`Good morning`, `Good afternoon`, `Good evening`) and never renders an awkward `Good
night`; use `Good evening` for the late-day range. Do not repeat the page title in the first section.

### `EditorialHero` / `TonightCard`

Food imagery bleeds into the entire surface or enters from one side with a soft overlay. Do not place a
small circular thumbnail or a sharp stitched boundary in the center. Copy sits on the high-contrast side:
eyebrow, recipe title, serving/time/nutrition facts, availability or grocery note, and one primary action.
The hero remains useful without an image through deliberate `RecipeFallbackArt` or a simple plated-food
illustration.

### `WeekCard`

Shows the actual seven-day rhythm, with explicit open/planned states, the current day, and one `Next up`
row. It is a compact summary and route to Plan, not a second planner. A line of anonymous progress marks
without day meaning is not sufficient.

### `ModuleHeading`

Combines an optional eyebrow, a human section title, and one trailing route action. Prefer `Cook next`,
`Use soon`, `Recently saved`, and `Grocery` over internal language such as `Context, not guesswork`.

### `UseSoon`

Surfaces pantry items with use-by dates and a direct `Find recipes using these` or `Open pantry` path.
The empty state teaches how dates make the module useful. It never invents urgency when no expiry data is
known.

### `QuickActions`

Three high-value actions presented as a separator-led list (`Plan tonight`, `Add a recipe`, `Add a grocery
item`). Each row has one icon, a verb, a short explanation, and a clear hit target. Do not turn each action
into a competing colorful card.

### `RecipeMedia` / `RecipeFallbackArt`

Every recipe surface has food media or a deliberate ingredient/plate fallback. The fallback keeps the same
frame, curve, crop behavior, and visual weight as a real image; no emoji-only or generic gray placeholder.
Use focal-point/zoom metadata when available. Alt text is empty when adjacent text names the recipe.

### `RecipeCard` / `RecipeShelf`

Image first, consistent media ratio and curve across Recipes, Home, Plan, suggestions, and search. Home's
recent shelf is compact (four items on desktop), not Recipes Lite. On mobile it remains a touch/keyboard
scrollable shelf while hiding scrollbar chrome; the partial next card and snap spacing preserve the scroll
affordance. Titles and metadata align to a common baseline; cards do not become different heights because
one has extra copy. A deliberate featured card may span space, but identical dashboard-card grids are
prohibited.

### `RecipeMetadata` / `NutritionRibbon`

Anywhere a recipe is shown, expose the useful cooking facts available: estimated total time, serving count,
calories, protein, carbs, and fat. Discovery surfaces keep this compact and round values for scanning;
detail/edit surfaces may show exact decimals, source, coverage, and correction history.

- Calories stay neutral ink.
- Protein, carbs, fat, and fiber get a 6px semantic dot plus a visible category label/value.
- Show no more than four nutrient values in one compact row; wrap before horizontal scrolling.
- Missing data is explicit (`Time not set`, `Nutrition pending`) rather than silently omitted.
- Compact metadata never drops below 14px; primary recipe facts use 15px so they remain comfortably scannable.
- A status color never substitutes for a word. Rings and gauges need a real target comparison and are not
  default decoration.

### `KitchenCompanion` / `EmptyState` / `ErrorRecovery`

Use small food/ingredient illustrations to make empty, success, and recovery moments feel like Cookfully.
Copy explains what happened and gives the next useful action. Loading skeletons match the eventual shape;
whole-page spinners are prohibited.

### `CommandPalette` / `Sheet` / `Dialog`

Search and command surfaces are keyboard reachable (`⌘/Ctrl K`). Use a popover for a small choice, a sheet
for browse/search/quick edit, and a dialog only for a blocking decision. All overlays have a title,
description when needed, close action, focus trap, restoration, and escape behavior.

## Route inheritance

- **Recipes:** visual browsing first; search and a small filter set; cards use the same media and metadata
  contract as Home. Editing uses structured ingredient rows and numbered method steps, not giant textareas.
- **Plan:** the week is the object. Use direct manipulation, visible day/meal context, recipe thumbnails,
  servings, prep, and a nutrition summary that stays adjacent rather than taking over.
- **Pantry:** current shelf and use-by attention. Empty states explain how a small, approximate pantry makes
  dinner easier; connect `Use soon` to recipe discovery.
- **Grocery:** a practical shop list derived from the plan, with categories, checkable rows, provenance back
  to meals, and a calm completion moment. Home uses only a compact prompt, never a duplicate list.
- **Cook mode:** focused, high-contrast, large touch controls, current step, relevant quantities, timer,
  progress, wake-lock, and a clear completion state. Hide unrelated admin and navigation.
- **Goals / Settings / System:** scannable index, human intent first, advanced controls disclosed. Never
  make a user learn database or macro terminology before they can cook.

## Interaction and motion

Modernity comes from clear interaction design first. Motion reinforces causality and orientation.

- Fast feedback/hover/focus: 160ms. Disclosure/sheet: 220ms. Meaningful entrance: 280ms.
- Use opacity and transform with an ease-out curve. Recipe image hover may scale to 1.035; quick-action
  arrows may move a few pixels; cards may lift subtly. Never animate layout dimensions or cause content jumps.
- Good signature moments: recipe shelf → detail shared image, plan drop snapping into a day, serving/macros
  recalculating, favorite confirmation, grocery completion, cooking-step transition, skeleton → content.
- Bad motion: headings flying in, every page fading, animated backgrounds, gratuitous parallax, or motion
  that delays a task. Respect `prefers-reduced-motion` with near-zero duration and no transform.

## Content, accessibility, and honest states

- Copy is human, cooking-first, and neutral. Say `planned`, `remaining`, `outside target`, or `needs a
  review`; never moralize food or use gym-bro language.
- Every route has explicit loading, empty, partial, estimated, manual, stale, and failed states where the
  data model allows them. A missing image, time, or nutrition value has a designed fallback.
- Use semantic landmarks and headings, keyboard order that matches visual order, visible focus, labels for
  every control, `aria-live` for async status, and at least 44×44px touch targets.
- Do not rely on color, hover, imagery, or an icon alone to convey meaning. Preserve text alternatives,
  contrast, reduced motion, zoom, and narrow-width reflow.

## Rejection list

Reject a screen or component that feels like: a gym dashboard, a dark admin panel, a wall of form fields,
an anonymous card grid, a monochrome spreadsheet, a collection of floating pills, a generic shadcn demo,
or a marketing landing page with no useful action. Also reject any “modernization” that adds animation,
gradients, or decorative color without making planning, shopping, or cooking easier.

## Acceptance checklist

Before calling a UI change complete, verify in the browser at 1440×900 (or the closest desktop viewport)
and 390×844:

1. The primary object and next action are obvious within one scan.
2. Food imagery or an intentional food fallback leads every recipe surface.
3. The page uses Home's tokens, type, curves, density, and restrained depth; no local raw colors.
4. Recipe time, servings, calories, protein, carbs, and fat appear wherever data exists, with honest
   missing/provenance states.
5. The page has useful content above the fold without arbitrary empty height.
6. Mobile composition is redesigned, the top/bottom navigation has aligned hit boxes, and nothing is
   hidden behind fixed UI.
7. Keyboard, focus, reduced-motion, zoom, error, loading, and empty paths remain usable.
8. A visual review compares the result with `/app`, not only with a unit test or a screenshot of the
   changed component.

If the current Home reference changes intentionally, update this document and the supporting context files
in the same change so the design system does not drift.
