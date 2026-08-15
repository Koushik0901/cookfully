# UI Execution Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift Cookfully's rendered execution from "disciplined but flat" to genuinely polished — stronger surface differentiation, depth, motion, and a confirmed-consistent component system — while staying inside the DESIGN.md contract.

**Architecture:** Pure frontend work. No backend, no API, no schema changes. Token additions live in `frontend/src/styles/tokens.css`; composition/depth/motion rules in the existing feature CSS; dead classes and semantic splits fixed in TSX. Every visual change is gated by lint, typecheck, tests, build, and a browser smoke check at 1440x900 and 390x844.

**Tech Stack:** React 19.2 + Vite 8.1 + Tailwind 4, shadcn primitives, OKLCH design tokens, lucide-react. Commands: `pnpm --dir frontend lint`, `pnpm --dir frontend typecheck`, `pnpm --dir frontend test --run`, `pnpm --dir frontend build`.

## Global Constraints

- OkLCH only; no raw colors in feature TSX (DESIGN.md:80). New tokens go in `tokens.css` only.
- Pure `#fff`/`#000` prohibited. All surfaces stay warm herb-tinted.
- WCAG 2.2 AA: 4.5:1 normal text, 3:1 large/UI. No regression below today's contrast.
- Nutrient/status color semantics are fixed by DESIGN.md:88-99. Green = confirmed/manual success; red = error/destructive; amber = partial/stale; blue = processing.
- "Food before figures" — no new rings/gauges except where a real target comparison exists (budgets, nutrition-pulse already qualify).
- Motion: opacity/transform only, no width/height/margin animation, no bounce/elastic, respect `prefers-reduced-motion` (already global in globals.css:265).
- shadcn primitives are source-owned; Cookfully identity comes from composition (DESIGN.md:265).
- No new dependencies, no font changes (Afacad Flux + Inclusive Sans, already self-hosted).
- **Conservative accent decision:** saffron stays rare per DESIGN.md. Flatness is fixed with depth (surfaces, hairlines, shadows), NOT by spreading saffron into eyebrows/nav/hover states.

---

### Task 1: Fix dead classes and page-class gaps (consistency)

**Files:**
- Modify: `frontend/src/features/settings/SettingsPage.tsx:25-41`
- Modify: `frontend/src/features/settings/AgentAccessPage.tsx:101`
- Test: `frontend/src/features/settings/__tests__/SettingsPage.test.tsx`

**Interfaces:**
- Produces: Settings tab buttons keyed off `aria-selected` only (no dead `settings-tab--active`); AgentAccessPage root matches other pages.

- [ ] **Step 1: Add a regression assertion to the settings test**

Open `frontend/src/features/settings/__tests__/SettingsPage.test.tsx`. Read the existing test first to match its render helpers, then append:

```tsx
it("uses the shared settings-tabs structure without dead classes", () => {
  const { getByRole } = render(<SettingsPage />);
  const account = getByRole("tab", { name: "Account" });
  expect(account).toHaveAttribute("aria-selected", "true");
  expect(account.className).not.toContain("settings-tab--active");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir frontend test --run src/features/settings/__tests__/SettingsPage.test.tsx`
Expected: FAIL — `account.className` still contains `settings-tab--active`.

- [ ] **Step 3: Clean the settings tab markup**

In `SettingsPage.tsx`, change line 35 from:

```tsx
className={`settings-tab ${tab === id ? "settings-tab--active" : ""}`}
```

to:

```tsx
className="settings-tab"
```

(The `.settings-tabs button[...]` rules in features.css:926-932 already style these; active state flows from `aria-selected`.)

- [ ] **Step 4: Add the missing page class**

In `AgentAccessPage.tsx:101`, change:

```tsx
: <main className="page-shell">
```

to:

```tsx
: <main className="page-shell settings-agent-page">
```

- [ ] **Step 5: Run tests, lint, typecheck**

Run: `pnpm --dir frontend test --run && pnpm --dir frontend lint && pnpm --dir frontend typecheck`
Expected: PASS with 0 warnings.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/settings/
git commit -m "fix(ui): remove dead settings-tab class, add missing page class"
```

---

### Task 2: Unify success-state color semantics

**Files:**
- Modify: `frontend/src/styles/features.css` (`.suggestion-success` ~line 919, `.suggestion-success .eyebrow`, `.suggestion-success__evidence` ~line 921)
- Test: `frontend/src/features/suggestions/__tests__/suggestion-ui.test.tsx`

**Interfaces:**
- Consumes: existing `--status-success-container` / `--status-success` tokens.
- Produces: every "confirmed success" surface uses success green, not herb-primary.

- [ ] **Step 1: Ensure the success panel is assertable**

Read `frontend/src/features/suggestions/__tests__/suggestion-ui.test.tsx` to understand its existing accept flow. Give `.suggestion-success` a stable hook if it lacks one (add `data-testid="success-panel"` in `SuggestionPage.tsx`) and assert it appears after accepting.

- [ ] **Step 2: Re-point the success panel**

In `features.css`, change `.suggestion-success` (line ~919) background/color to the success registry:

```css
.suggestion-success {
  color: var(--status-success);
  background: var(--status-success-container);
}
```

Keep the layout grid rules unchanged. Add:

```css
.suggestion-success .eyebrow { color: var(--status-success); }
```

- [ ] **Step 3: Fix the evidence divider**

`.suggestion-success__evidence` currently uses `border-left: 1px solid color-mix(in oklch, var(--color-primary) 25%, transparent)` (line ~921). Change `var(--color-primary)` to `var(--status-success)` so the divider shares the status hue.

- [ ] **Step 4: Run tests, lint, typecheck, build**

Run: `pnpm --dir frontend test --run && pnpm --dir frontend lint && pnpm --dir frontend typecheck && pnpm --dir frontend build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/features.css frontend/src/features/suggestions/
git commit -m "fix(ui): success panels use success-green semantics"
```

---

### Task 3: Add surface/card depth tokens and apply to raised cards

**Files:**
- Modify: `frontend/src/styles/tokens.css:109-121`
- Modify: `frontend/src/styles/features.css` (nutrition-panel ~456, pantry-result ~1116, plan-entry ~1323, recipe-editor__save ~618, goal-save ~850, recipe-card--featured border ~253)
- Test: visual gate — build + browser check

**Interfaces:**
- Produces tokens consumed later: `--color-card-raised`, `--color-card-raised-border`, `--shadow-card-raised`, `--color-outline-strong`.

- [ ] **Step 1: Add the new tokens**

In `tokens.css`, inside the `:root` near the existing shadow lines (after line 107), add:

```css
--color-card-raised: oklch(0.992 0.006 92);
--color-card-raised-border: oklch(0.872 0.025 100);
--color-outline-strong: oklch(0.668 0.042 100);
--shadow-card-raised: 0 1px 2px oklch(0.218 0.038 148 / 6%), 0 14px 34px oklch(0.218 0.038 148 / 9%);
```

- [ ] **Step 2: Apply to raised cards**

In `features.css`, swap these to the new tokens:
- `.nutrition-panel` (line ~456): `background: var(--color-card-raised); border-color: var(--color-card-raised-border); box-shadow: var(--shadow-card-raised);`
- `.pantry-result` (line ~1116): same swap.
- `.plan-entry` (line ~1323): same swap.
- `.recipe-editor__save` (line ~618) and `.goal-save` (line ~850): `background: var(--color-card-raised)`.
- `.recipe-card--featured` border (line ~253): `border-color: var(--color-outline-strong)`.

- [ ] **Step 3: Visual smoke check**

Run: `pnpm --dir frontend dev`, open `http://localhost:5173`, sign in, open a recipe detail + the pantry search area. Confirm cards read as a distinct raised plane against the page at 1440x900 and 390x844.

- [ ] **Step 4: Gate and commit**

Run: `pnpm --dir frontend lint && pnpm --dir frontend typecheck && pnpm --dir frontend test --run && pnpm --dir frontend build`
Expected: PASS.

```bash
git add frontend/src/styles/
git commit -m "feat(ui): raised-card tokens and application"
```

---

### Task 4: Conservative depth — media shadows lift (reserved accent token)

**Files:**
- Modify: `frontend/src/styles/tokens.css:19-26`
- Modify: `frontend/src/styles/features.css` (`.recipe-card__media` ~174, `.recipe-hero__media` ~282)

**Interfaces:**
- Produces token `--color-accent-strong` (defined but NOT broadly applied; reserved).

- [ ] **Step 1: Add the reserved accent-strong token**

In `tokens.css` after line 19 (`--color-accent: oklch(0.790 0.158 72)`), add:

```css
--color-accent-strong: oklch(0.585 0.140 62);
```

- [ ] **Step 2: Lift media shadows**

In `features.css`:
- `.recipe-card__media` (line ~174): change `box-shadow: var(--shadow-level-1)` to `box-shadow: var(--shadow-card-raised)`.
- `.recipe-hero__media` (line ~282): change `box-shadow: var(--shadow-level-2)` to `box-shadow: var(--shadow-card-raised)`.

No other accent application. Conservative mode: no saffron in eyebrows, nav, hovers, or filter badges.

- [ ] **Step 3: Gate and commit**

Run lint/typecheck/test/build → PASS. Commit:

```bash
git add frontend/src/styles/
git commit -m "feat(ui): lift media shadows, reserve accent-strong token"
```

---

### Task 5: Motion pass — staggered entry, tab slide, skeleton shimmer

**Files:**
- Modify: `frontend/src/styles/globals.css:253-256` (page-arrive + stagger variant)
- Modify: `frontend/src/styles/features.css` (`.recipe-view-tabs button` ~79, `.recipe-grid` ~151, `.recipe-card` — ensure `position: relative`)
- Modify: `frontend/src/components/shared.css:390-403` (skeleton)
- Modify: `frontend/src/features/recipes/RecipeLibraryPage.tsx` and `frontend/src/features/plans/WeeklyPlannerPage.tsx` (add `page-shell--stagger` to `<main className="page-shell ...">`)

**Interfaces:**
- Consumes: `--motion-entrance`/`--ease-out-expo` tokens.
- Produces: `page-shell--stagger` modifier; `.recipe-grid .recipe-card` entry delays (first 3 cards); `.skeleton > span` shimmer.

- [ ] **Step 1: Stagger the page entrance (header then content)**

In `globals.css`, after the existing `page-arrive` keyframes (line ~253):

```css
.page-shell--stagger > .page-header { animation: page-arrive var(--motion-entrance) var(--ease-out-expo) both; }
.page-shell--stagger > :not(.page-header) { animation: page-arrive var(--motion-entrance) var(--ease-out-expo) both; animation-delay: 90ms; }
```

Add `page-shell--stagger` to the `<main className="page-shell recipe-library-page">` element in `RecipeLibraryPage.tsx` and the `<main className="page-shell planner-page">` element in `WeeklyPlannerPage.tsx`.

- [ ] **Step 2: Add a sliding tab indicator**

In `features.css`, `.recipe-view-tabs button` (line ~79) needs `position: relative;` added, then:

```css
.recipe-view-tabs button::after {
  position: absolute;
  bottom: 0.35rem;
  left: 50%;
  width: 40%;
  height: 2px;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  content: "";
  transform: translateX(-50%) scaleX(0);
  transition: transform var(--motion-state) var(--ease-out-expo);
}
.recipe-view-tabs button[aria-pressed="true"]::after { transform: translateX(-50%) scaleX(1); }
```

- [ ] **Step 3: Recipe grid card entrance (first 3 only)**

In `features.css`, near `.recipe-grid`:

```css
@media (min-width: 48rem) {
  .recipe-grid .recipe-card { animation: page-arrive var(--motion-entrance) var(--ease-out-expo) both; }
  .recipe-grid .recipe-card:nth-child(2) { animation-delay: 45ms; }
  .recipe-grid .recipe-card:nth-child(3) { animation-delay: 90ms; }
}
```

- [ ] **Step 4: Skeleton shimmer**

In `shared.css:398-403`, replace `skeleton-breathe` with a translate shimmer:

```css
@keyframes skeleton-shimmer {
  from { background-position: -12rem 0; }
  to { background-position: calc(100% + 12rem) 0; }
}
.skeleton > span {
  background: linear-gradient(90deg, var(--color-surface-high) 25%, var(--color-surface-highest) 50%, var(--color-surface-high) 75%);
  background-size: 24rem 100%;
  animation: skeleton-shimmer 1.4s var(--ease-out-expo) infinite;
}
```

Keep the `prefers-reduced-motion` global override which already nulls animations.

- [ ] **Step 5: Gate, browser-checks (normal + reduced-motion), commit**

Run lint/typecheck/test/build → PASS. In browser verify normal motion and `prefers-reduced-motion: reduce` (devtools rendering) kills all movement. Commit:

```bash
git add frontend/src/styles/ frontend/src/features/recipes/RecipeLibraryPage.tsx frontend/src/features/plans/WeeklyPlannerPage.tsx
git commit -m "feat(ui): staggered entrances, tab slide, skeleton shimmer"
```

---

### Task 6: Typography confidence pass

**Files:**
- Modify: `frontend/src/styles/tokens.css:63-77`
- Modify: `frontend/src/styles/globals.css:31-33,79-82`
- Modify: `frontend/src/styles/features.css` (`.recipe-card h2` ~215, `.plan-entry__title h4` ~1331)

**Interfaces:**
- Produces: h3/h4 use `--text-title-lg` (1.5rem) and `1.125rem`; body weight 460.

- [ ] **Step 1: Raise body weight for legibility**

In `globals.css:33`, change `font-weight: 430` to `font-weight: 460`.

- [ ] **Step 2: Strengthen heading steps**

`globals.css:79-82`: change h3 to `gap? use --text-title-lg: 1.5rem` and h4 to `1.125rem`:

```css
h1 { font-size: var(--text-headline-md); }
h2 { font-size: var(--text-headline-sm); }
h3 { font-size: var(--text-title-lg); line-height: 1.2; }
h4 { font-size: 1.125rem; line-height: 1.25; }
```

Verify in browser no visual tie between h3/h4 and card titles.

- [ ] **Step 3: Card titles use display face**

`.recipe-card h2` (features.css:215): `font-size: 1.25rem` → `font-size: var(--text-title-md);` (inherits display font from global h2). `.plan-entry__title h4` (~1331): add `font-family: var(--font-display); font-weight: 620;`.

- [ ] **Step 4: Gate and browser check**

Run gates → PASS. Browser check at 1440x900 and 390x844: page/section/card titles read as clearly different weights/sizes. Commit:

```bash
git add frontend/src/styles/
git commit -m "feat(ui): typography confidence pass"
```

---

### Task 7: Link/action consistency

**Files:**
- Modify: `frontend/src/styles/globals.css:142-148` (`.text-link`)
- Modify: `frontend/src/components/shared.css:118-125` (`.cf-button--link`)

**Interfaces:**
- Produces: single link style source — `.cf-button--link` is canonical; `.text-link` delegates.

- [ ] **Step 1: Consolidate the two link styles**

Both `.text-link` (globals.css:143) and `.cf-button--link` (shared.css:118) define the same rules (padding 0, underline, offset, primary color). Tailwind 4 has no `@extend` for plain classes. shared.css is already imported by globals.css (globals.css:5). Remove the `.text-link` block from globals.css and keep the shared.css rule as the single source. Verify shared.css loads before features.css so all `.text-link` usages resolve.

- [ ] **Step 2: Verify no page regresses**

Grep for `text-link` usages after removal; `.cf-button--link` must cover all usages (bump its specificity/selector to also match plain `.text-link` elements: change the selector to `.cf-button--link, .text-link { ... }`).

- [ ] **Step 3: Gate and commit**

Run gates → PASS. Commit:

```bash
git add frontend/src/styles/ frontend/src/components/
git commit -m "refactor(ui): single link style source"
```

---

### Task 8: Final audit and anti-slop gate

**Files:**
- Test: `frontend/src` scan
- Modify: none expected

- [ ] **Step 1: Run the full verification battery**

```bash
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
```

Expected: all PASS.

- [ ] **Step 2: Browser review checklist** (1440x900 + 390x844)

V1: Recipe library (grid + featured, staggered entry). V2: Recipe detail (hero, nutrition panel raised). V3: Weekly planner (stagger, tabs, budget bars). V4: Suggestions (success panel green). V5: Settings (tabs aria-selected, no dead class). V6: Cook mode (dark kitchen, accent step numbers). V7: Pantry search (raised results). Confirm: no document-level horizontal overflow; food imagery leads; reduced-motion kills all movement; 200% zoom reflows.

- [ ] **Step 3: Anti-slop pass**

Grep the diff for: `background-clip:text`, gradient text, new glassmorphism, decorative border-left stripes (existing ones in nutrition metrics are divider lines and stay). Confirm none introduced.

- [ ] **Step 4: Commit any fixes**

```bash
git add frontend/
git commit -m "chore(ui): final audit pass"
```