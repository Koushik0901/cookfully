---
name: Cookfully
version: 2.0
direction: Editorial kitchen utility
defaultTheme: light
fonts:
  display: Afacad Flux Variable
  body: Inclusive Sans Variable
colors:
  canvas: oklch(0.985 0.007 92)
  surface: oklch(0.985 0.007 92)
  surface-muted: oklch(0.968 0.011 94)
  ink: oklch(0.218 0.038 148)
  ink-muted: oklch(0.455 0.030 145)
  line: oklch(0.858 0.027 96)
  primary: oklch(0.405 0.126 148)
  primary-hover: oklch(0.350 0.118 148)
  on-primary: oklch(0.988 0.008 92)
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

This document is authoritative for Cookfully interface work. It translates the product persona into
component rules that can be reviewed in code and verified in the browser. If a screen is attractive but
breaks these rules, the screen is not finished. If a rule creates friction for the user, change this
document deliberately rather than adding a local exception.

## Product feeling

Cookfully is a cooking tool with nutritional intelligence. It is for anyone trying to eat with more
care: a household planning weeknight meals, someone managing dietary targets, a person cutting or
bulking, or a cook who simply wants balanced food. It must never assume that exercise, weight loss,
body composition, or macro optimization is the user's identity.

The visual direction is **editorial kitchen utility**: the appetite and pacing of a contemporary food
publication, combined with the clarity and reliability of a calm personal tool.

- **Personality:** warm, assured, appetizing.
- **Not:** clinical, gym-coded, rustic, childish, luxury-theatre, or generic wellness SaaS.
- **Memorable idea:** food is the foreground; nutrition is the quiet evidence layer beneath it.
- **Default theme:** light. A dark theme may be added, but it cannot delay or weaken the light theme.

## Product principles

1. **Food before figures.** Recipe imagery, names, ingredients, and cooking context lead. Nutrition
   supports the decision; it does not dominate every surface.
2. **Start with the next useful action.** Every page answers what the user can do now. A region has at
   most one primary action.
3. **Reveal complexity on demand.** Quick paths stay visible. Advanced nutrition, provenance, import
   diagnostics, and system settings live behind deliberate disclosure.
4. **Never judge.** Use neutral language such as `remaining`, `planned`, and `outside target`; never
   `bad`, `cheat`, `failed`, or celebratory weight-loss language.
5. **Honesty without noise.** Estimated, partial, manual, corrected, stale, and failed data remain
   explicit, but compact. Precision belongs in detail and editing surfaces, not discovery cards.
6. **Mobile is a cooking context.** Mobile layouts prioritize touch, one-handed navigation, readable
   ingredients, and quick plan edits. They are redesigned, not shrunk desktop pages.

## Visual foundation

### Color roles

Use the semantic tokens in the front matter through CSS custom properties. Raw colors are prohibited in
feature CSS. Neutrals are warm and subtly herb-tinted; pure white and pure black are prohibited.

- `canvas` is the page field.
- `surface` is used sparingly for interactive or raised regions.
- `surface-muted` groups quiet secondary material without creating another card.
- `ink` and `ink-muted` are the only default text colors.
- `primary` is deep herb green and is reserved for the page's primary action, active navigation, and
  successful completion.
- `accent` is saffron. It marks moments of discovery, a new suggestion, or a small decorative detail;
  it is not a second primary action color.
- Nutrient colors are semantic and based on familiar food associations: protein is blue (structure),
  carbohydrate is orange (energy), fat is oil/golden yellow, and fiber/plants are green. Calories and
  totals stay neutral ink. These assignments are global and cannot be changed page-by-page merely to
  create visual variety.
- Nutrient colors carry meaning only when the category is also named. They never color general
  navigation, buttons, or headings. Color reinforces a label; it never replaces one.
- Interface states use a separate registry so they never borrow a nutrient meaning: blue is
  processing/information, amber is partial/stale attention, green is confirmed/manual success, and
  red is failed/destructive. A status color always appears with text or an accessible name.
- Error/destructive red is reserved for errors and destructive actions.

Minimum contrast is WCAG 2.2 AA: 4.5:1 for normal text and 3:1 for large text, icons, controls, focus
indicators, and meaningful chart marks.

### Typography

Self-host the variable faces. Do not load fonts from a third-party CDN.

- **Afacad Flux Variable**: wordmark, display, page, section, and card headings.
- **Inclusive Sans Variable**: body, controls, labels, instructions, and data.
- Numbers use `font-variant-numeric: tabular-nums`; a monospace face is not used as shorthand for
  nutrition or technical credibility.

| Token | Desktop | Mobile | Weight | Use |
|---|---:|---:|---:|---|
| `display` | 56/58 | 40/43 | 650 | Marketing statement only |
| `page-title` | 36/39 | 30/34 | 620 | One per page |
| `section-title` | 28/32 | 24/28 | 600 | Major content section |
| `card-title` | 21/25 | 20/24 | 590 | Recipe and plan titles |
| `body` | 16/24 | 16/24 | 430 | Default copy |
| `body-small` | 14/20 | 14/20 | 440 | Metadata and helper text |
| `label` | 13/16 | 13/16 | 620 | Form and compact UI labels |

Letter spacing is normal for body copy, `-0.015em` for headings, and `0.02em` only for short eyebrow
labels. All-caps labels are prohibited. Body line length is 45–72 characters.

### Spacing and rhythm

The base unit is 4px. Approved gaps are 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, and 96px.

- Tight internal grouping: 4–12px.
- Related controls/content: 16–24px.
- Section separation: 40–64px.
- Major page transitions: 64–96px.
- Do not use identical padding on every region. Rhythm must visibly alternate between tight groups and
  open transitions.

### Shape and depth

- Controls: 10px radius; 44px minimum height, 48px for primary form fields.
- Content surfaces: 18px radius.
- Recipe media: 22px radius.
- Pills are reserved for filters, status, and compact categories—not every button.
- Default surfaces use tonal contrast and a one-pixel line. Shadows are reserved for floating sheets,
  menus, and media that intentionally overlaps another plane.
- Never nest cards inside cards. Flatten with spacing, headings, separators, or a muted field.
- Glass blur is allowed only on persistent navigation over scrolling content.

## Layout system

### Application shell

- Desktop (`>= 1024px`): 232px navigation rail, fixed within the viewport; content uses the remaining
  width and a maximum readable width of 1440px.
- Tablet (`768–1023px`): 80px icon rail or compact top navigation depending on content needs.
- Mobile (`< 768px`): compact top bar plus a 68px bottom navigation with four primary destinations and
  one `More` entry. Safe-area padding is mandatory.
- Primary destinations: Recipes, Plan, Grocery, Pantry. Suggestions may replace Pantry if product data
  proves it is used more frequently. Foods, Goals, agent/system access, and account live under More.
- Navigation labels are always visible on mobile. Icons supplement text; they never replace it.

### Page frame

- Horizontal page inset: 16px mobile, 28px tablet, 48px desktop.
- Page header has a short optional eyebrow, one title, and at most one sentence of supporting copy.
- Desktop header actions sit opposite the title. Mobile actions sit immediately below the copy.
- A page title must not exceed two lines at 390px.
- Do not repeat the page title in the first section heading.

## Component contracts

### Buttons

- Primary: filled herb green. One per region.
- Secondary: quiet tonal surface with visible boundary.
- Ghost: secondary navigation and reversible actions.
- Destructive: ghost by default; filled red only inside the final confirmation.
- Icon-only buttons require an accessible name and tooltip.
- Loading preserves width, disables repeated submission, and shows a spinner plus verb when space allows.
- Touch target is at least 44x44px; adjacent targets have at least 8px separation.

### Forms

- Labels are persistent and sit above controls. Placeholder text is an example, never the label.
- Helper or error text reserves a stable row below the control to avoid layout jumps.
- Group related fields with a visible legend and one sentence explaining why they matter.
- Two to seven exclusive options use a segmented or toggle group, not a select.
- Long recipe entry uses sections with a visible completion path: Basics → Ingredients → Method →
  Nutrition. Only the current section expands on mobile.
- Advanced nutrition, import diagnostics, external services, and automation settings are collapsed by
  default and state what opening them will reveal.
- Validation happens on blur and submit. Focus the first invalid field and provide a summary for long
  forms.

### Search, filters, and selection

- Search is the dominant recipe-library control.
- Common filters appear as no more than three chips. Remaining filters live in a popover or mobile sheet.
- Active filter count appears in the trigger. `Clear filters` is available whenever any filter is active.
- Selection is optimistic and reversible; success is acknowledged quietly without a blocking modal.

### Recipe cards

- Image-first with a 4:3 media field. If no image exists, use a Cookfully ingredient/plate illustration,
  never initials or a generic gray box.
- Image, title, and entire primary card area open the recipe. Archive/edit actions appear on hover/focus
  or in a compact menu.
- The visible metadata line contains at most three useful facts: total time, serving count, and one
  contextual nutrition summary.
- Discovery surfaces round values for scanning (`540 kcal`, `32 g protein`). Exact decimals and
  provenance remain available in recipe detail/editing.
- Nutrition is never placed in a blurred overlay that obscures food.
- Desktop grid: 3 columns above 1180px, 2 columns from 760–1179px, 1 column below 760px. A deliberate
  featured card may span two columns; identical dashboard-card grids are prohibited.

### Nutrition ribbon

The compact evidence layer used on recipe, plan, and suggestion summaries:

- Calories are plain ink text; protein, carbohydrate, fat, and fiber use a 6px semantic dot plus category
  name and the global nutrient-color registry above.
- Maximum four values in one row. Collapse to two rows before horizontal scrolling.
- No rings, gauges, or progress bars unless a real target comparison exists.
- Target comparison states both values (`32 of 45 g protein`) and never relies on color alone.
- Coverage/provenance is one compact status trigger that opens explanatory detail.

### Planning

- Week and day navigation remain visible while planning.
- A day begins with a concise balance summary, followed by Breakfast, Lunch, Dinner, and Snacks.
- Empty meal slots show a single `Add a recipe` action. The recipe picker is a search-first sheet, not a
  permanently visible select/input pair repeated four times.
- Planned recipes show image thumbnail, recipe name, serving count, and contribution. Editing happens
  inline or in the same picker sheet.
- Suggestions appear only where they resolve a visible gap; they do not become another dashboard panel.

### Goals and settings

- Goals begin with intent in human language, then show calculated targets for review.
- The default path contains only the inputs necessary to calculate a useful plan. Manual macro targets,
  micronutrients, and advanced calculation assumptions are separate disclosures.
- Settings use a scannable index and focused detail groups. No page presents a wall of unrelated inputs.
- AI, MCP, database, import provider, and maintenance options are system administration, not ordinary
  cooking settings; place them in a clearly named `System` area with consequences explained.

### Overlays and feedback

- Use a popover for a small contextual choice, a sheet for browse/search/quick-edit workflows, and a
  dialog only when the user must resolve a blocking decision.
- Every dialog and sheet has a semantic title, optional description, visible close action, initial focus,
  focus trap, and focus restoration.
- Toasts acknowledge background or reversible actions. Errors that block the current task stay inline.
- Empty states teach the first action and show an illustrative food-related cue; they do not merely say
  `Nothing here`.
- Loading uses skeletons shaped like the destination content. Never replace a whole page with a spinner.
- First-run guidance may replace a relevant empty surface for an explicitly new account. It is never
  mounted above the route outlet, repeated across pages, or inferred merely from a missing preference row.
- Once a kitchen has existing data or the welcome has been resolved, ordinary contextual empty states
  take over permanently. Returning users are never sent back through first-run guidance.
- Educational guidance must stay attached to the state that makes it useful. Do not stack coach panels
  below a complete empty state, repeat the same optional action in a toolbar and every empty row, or keep
  introductory explanations open beside established content. Keep one clear action and put optional help
  behind a user-controlled disclosure.

## shadcn component foundation

Cookfully may use shadcn components as source-owned accessible primitives. The component library is not
the visual identity.

- Store primitives under `frontend/src/components/ui` and shared Cookfully compositions under
  `frontend/src/components/cookfully`.
- Map shadcn semantic variables to the tokens above; never keep an untouched preset palette.
- Prefer shadcn Button, Field/Input, Select/Combobox, ToggleGroup, Tabs, Sheet, Dialog, Popover,
  Tooltip, DropdownMenu, Badge, Separator, Skeleton, Progress, Empty, and Sonner behavior.
- Feature code must not restyle primitives with raw colors. Add documented variants when a repeated
  product pattern needs them.
- A recipe card, nutrition ribbon, meal slot, day selector, and food media fallback are Cookfully
  components, not generic registry blocks.

## Motion and interaction

- Default duration: 160ms for hover/focus, 220ms for disclosure, 280ms for sheet/page entrances.
- Easing: `cubic-bezier(0.22, 1, 0.36, 1)` for entrances; standard ease for color transitions.
- Animate opacity and transform. Do not animate width, height, margin, or padding.
- Page entrances may stagger the header and first content group once; repeated scroll reveals are
  prohibited.
- Hover translation is at most 2px. No bounce, elastic easing, floating decoration, or decorative
  infinite motion.
- Respect `prefers-reduced-motion` by removing non-essential movement and using instant state changes.

### Illustration and companion language

- The recurring Cookfully companion is a small bowl-and-sprig character: warm, food-specific, and
  recognizable without becoming a named mascot or competing with recipe photography.
- Use it only for genuine system moments: loading, instructive empty states, task-blocking errors,
  successful saves, completed plans or shopping passes, and finishing cook mode. Ordinary clicks,
  navigation, and inline selection changes do not trigger character animation.
- Loading may loop a functional whisk-and-steam motion while shaped skeletons still communicate page
  structure. Empty, error, success, and milestone variants animate once, then remain still.
- Success uses a drawn check; milestones add a restrained saffron seed burst. Error states stay calm
  and empathic—never comic, punitive, or alarmist.
- Implement the companion as an inline, decorative SVG using semantic color tokens. Animation is CSS
  transform, opacity, and stroke drawing only, with no network asset, video, GIF, or animation runtime.
- Under `prefers-reduced-motion`, render the final illustrated state immediately and remove all movement.

## Content language

- Lead with what the person can accomplish: `Plan this week`, `Add a recipe`, `Review nutrition`.
- Use `you` and plain language; avoid marketing claims inside the application.
- Prefer `Nutrition estimate is incomplete` over `Pipeline coverage failure`.
- Prefer `System` over `Database`, `Agent access` over `MCP configuration`, and explain unfamiliar terms
  before showing controls.
- Never call food clean/dirty, good/bad, guilt-free, cheat, or sinful. Cookfully supports mindful choices
  without moralizing them.

## Required states and accessibility

Every data surface explicitly implements and tests: loading, empty, partial, estimated, manual,
corrected, stale, failed, and unavailable/provider-degraded where applicable.

- Semantic HTML first; ARIA supplements only when needed.
- Full keyboard navigation with visible 2px focus ring and 2px offset.
- Focus order follows reading order. Roving tab index is required for day tabs and composite controls.
- Images have useful alt text or empty alt when decorative.
- At 200% zoom, controls and content reflow without loss.
- Verify 1440x900 desktop and 390x844 mobile. No page may create document-level horizontal overflow.

## AI-slop rejection list

Reject the implementation if it contains any of the following:

- a generic hero with oversized centered copy, gradient text, floating glass cards, or meaningless blobs;
- a dashboard made of identical rounded statistic cards;
- icons in colored rounded squares above every heading;
- a card around every section or nested card stacks;
- default shadcn colors/typography presented as the finished brand;
- an empty page with one lonely input;
- a wall of inputs exposed before the user chooses the task;
- dark navy with electric blue as a shortcut for technical credibility;
- macros treated as the product's personality;
- nutrient colors assigned decoratively or inconsistently rather than by the global semantic registry;
- precision-heavy decimal strings on recipe discovery cards;
- side-stripe accents, decorative sparklines, gradient text, or pervasive glassmorphism;
- mobile produced solely by shrinking desktop measurements.

## Page acceptance checklist

A page is ready for visual review only when all answers are yes:

1. Does the first viewport clearly communicate the next useful action?
2. Is there at most one primary action in each region?
3. Is food or cooking context visually ahead of nutrition metrics?
4. Has complexity been progressively disclosed instead of merely restyled?
5. Are typography, color, spacing, radius, and states expressed through system tokens/components?
6. Does the page remain coherent with realistic long text, missing images, partial nutrition, and errors?
7. Is it fully usable at 390x844 with touch and at 1440x900 with keyboard?
8. Would the page still feel recognizably Cookfully if the wordmark were removed?
