# Grocery icons, mobile single-column, and logo sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace grocery C/B initials with curated SVG category icons, make Recipes 1-per-row on mobile (<768px), and sync the new rail mark everywhere.

**Architecture:** Three independent presentational slices — trace 9 PNGs to SVGs + `GroceryIcon.tsx` keyword map (no API), one CSS breakpoint flip to `1fr` below 767px (desktop untouched), central `BrandMark` swap + regenerated `public/brand/*` + `manifest.webmanifest`. Each slice is CSS/asset-only and independently revertible.

**Tech Stack:** React 19.2 + Vite 8.1 + TypeScript 5.x, `DESIGN.md` tokens (oklch), `svgo`/`sharp`, Vitest + Playwright, `987` grid.

## Global Constraints

- `DESIGN.md` tokens only — raw hex/css colors prohibited; canvas `oklch(0.985 0.007 92)`, surface, primary `oklch(0.405 0.126 148)`, accent `oklch(0.790 0.158 72)`, etc. via CSS vars.
- Radii: control `10px`, surface `18px`, media `22px`, pill `999px`; spacing 4px rhythm; motion `160/220/280ms` ease-out, `prefers-reduced-motion` respected.
- No backend, no migrations, no new routes, no secrets/PII in logs.
- Verify at `1440×900` and `390×844`, keyboard/focus, loading/empty/failed states honest.
- Food leads, nutrition as supporting evidence — icons stay decorative (`aria-hidden`), not primary.

---

## File Structure

**New:**
- `frontend/public/media/grocery-icons/produce.svg`
- `frontend/public/media/grocery-icons/dairy.svg`
- `frontend/public/media/grocery-icons/bakery.svg`
- `frontend/public/media/grocery-icons/meat.svg`
- `frontend/public/media/grocery-icons/pantry.svg`
- `frontend/public/media/grocery-icons/frozen.svg`
- `frontend/public/media/grocery-icons/beverage.svg`
- `frontend/public/media/grocery-icons/household.svg`
- `frontend/public/media/grocery-icons/other.svg`
- `frontend/src/components/GroceryIcon.tsx`
- `frontend/src/features/grocery/__tests__/GroceryIcon.test.tsx`
- `frontend/src/components/__tests__/BrandMark.test.tsx`

**Modify:**
- `frontend/src/features/grocery/GroceryListPage.tsx:64` (`GroceryRow` — add icon span, grid)
- `frontend/src/styles/redesign.css:331,666` (breakpoint 767px → 1fr)
- `frontend/src/styles/features.css:626,646` (same breakpoint)
- `frontend/src/components/index.tsx:24` (`BrandMark` src if new file)
- `frontend/public/brand/*` (regenerated PNGs/ico if logo changes: `apple-touch-icon.png`, `cookfully-icon-192.png`, `cookfully-icon-512.png`, `icon-maskable-512.png`, `favicon-32.png`, `favicon-48.png`, `favicon.ico`, `cookfully-mark-512.png`, `cookfully-mark.png`)
- `frontend/public/manifest.webmanifest` (icons array if regenerated)
- `frontend/e2e/responsive.spec.ts` (add 1fr assertion, if exists else `frontend/e2e/recipes.spec.ts`)

---

### Task 1: Grocery SVGs + `GroceryIcon` component

**Files:**
- Create: `frontend/public/media/grocery-icons/*.svg` (9)
- Create: `frontend/src/components/GroceryIcon.tsx`
- Create: `frontend/src/features/grocery/__tests__/GroceryIcon.test.tsx`

**Interfaces:**
- Consumes: `displayName: string` from `GroceryItem`
- Produces: `export function GroceryIcon({ name, className }: { name: string; className?: string }): JSX.Element` + `export function categoryFor(name: string): Category` where `Category = "produce"|"dairy"|"bakery"|"meat"|"pantry"|"frozen"|"beverage"|"household"|"other"`

- [ ] **Step 1: Inspect inspiration PNGs**

Run: `python -c "from PIL import Image; import pathlib; [print(p.name, Image.open(p).size) for p in sorted(pathlib.Path('frontend/public/media/grocery-icons').glob('Screenshot*.png'))]"`
Expected: 9 PNGs `~146-152×168-176` RGBA — trace to 24×24 stroke icons.

- [ ] **Step 2: Trace 9 PNGs to optimized SVGs**

Use `potrace`/`Illustrator Image Trace` or manual recreation. Each SVG must be:
```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M..."/></svg>
```
Save to `frontend/public/media/grocery-icons/produce.svg` etc. Run `npx svgo frontend/public/media/grocery-icons/*.svg` — verify no `fill="#..."` remains, only `currentColor`.

- [ ] **Step 3: Write failing test for `GroceryIcon`**

```tsx
// frontend/src/features/grocery/__tests__/GroceryIcon.test.tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GroceryIcon, categoryFor } from "../../../components/GroceryIcon";

describe("GroceryIcon", () => {
  it("maps dairy keywords", () => { expect(categoryFor("Whole Milk 1L")).toBe("dairy"); });
  it("maps produce", () => { expect(categoryFor("Brown Rice")).toBe("pantry"); expect(categoryFor("Fresh Spinach")).toBe("produce"); });
  it("fallback other", () => { expect(categoryFor("")).toBe("other"); expect(categoryFor("xyz abc")).toBe("other"); });
  it("renders svg aria-hidden", () => {
    const { container } = render(<GroceryIcon name="milk" />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
  it("bakery/meat/frozen/beverage/household", () => {
    expect(categoryFor("Sourdough Bread")).toBe("bakery");
    expect(categoryFor("Chicken Breast")).toBe("meat");
    expect(categoryFor("Frozen Peas")).toBe("frozen");
    expect(categoryFor("Orange Juice")).toBe("beverage");
    expect(categoryFor("Paper Towels")).toBe("household");
  });
});
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pnpm --dir frontend test --run src/features/grocery/__tests__/GroceryIcon.test.tsx`
Expected: FAIL `Cannot find module '../../../components/GroceryIcon'`

- [ ] **Step 5: Implement `GroceryIcon.tsx`**

```tsx
// frontend/src/components/GroceryIcon.tsx
type Category = "produce"|"dairy"|"bakery"|"meat"|"pantry"|"frozen"|"beverage"|"household"|"other";
const MAP: Array<[Category, RegExp]> = [
  ["dairy", /\b(milk|cheese|yogurt|yoghurt|butter|cream|ghee|paneer)\b/i],
  ["produce", /\b(tomato|lettuce|apple|banana|spinach|onion|potato|herb|berry|berries|carrot|cucumber|avocado|kale|pepper|garlic|ginger|lemon|lime|corn)\b/i],
  ["bakery", /\b(bread|roll|bagel|croissant|bun|pita|dough|tortilla)\b/i],
  ["meat", /\b(chicken|beef|pork|fish|salmon|turkey|mutton|sausage|bacon|egg)\b/i],
  ["pantry", /\b(rice|pasta|oil|flour|sugar|salt|spice|lentil|chickpea|oat|quinoa|honey|vinegar|soy)\b/i],
  ["frozen", /\b(frozen|ice)\b/i],
  ["beverage", /\b(water|juice|wine|coffee|tea|soda|milkshake|smoothie)\b/i],
  ["household", /\b(paper|soap|detergent|foil|wrap)\b/i],
];
export function categoryFor(name: string): Category {
  const n = name.trim().toLowerCase();
  if (!n) return "other";
  for (const [cat, re] of MAP) if (re.test(n)) return cat;
  return "other";
}
import Produce from "../../public/media/grocery-icons/produce.svg?react";
import Dairy from "../../public/media/grocery-icons/dairy.svg?react";
import Bakery from "../../public/media/grocery-icons/bakery.svg?react";
import Meat from "../../public/media/grocery-icons/meat.svg?react";
import Pantry from "../../public/media/grocery-icons/pantry.svg?react";
import Frozen from "../../public/media/grocery-icons/frozen.svg?react";
import Beverage from "../../public/media/grocery-icons/beverage.svg?react";
import Household from "../../public/media/grocery-icons/household.svg?react";
import Other from "../../public/media/grocery-icons/other.svg?react";
const ICONS: Record<Category, React.ComponentType<React.SVGProps<SVGSVGElement>>> = { produce: Produce, dairy: Dairy, bakery: Bakery, meat: Meat, pantry: Pantry, frozen: Frozen, beverage: Beverage, household: Household, other: Other };
export function GroceryIcon({ name, className = "" }: { name: string; className?: string }) {
  const cat = categoryFor(name);
  const Icon = ICONS[cat];
  return <Icon className={`grocery-icon grocery-icon--${cat} ${className}`.trim()} aria-hidden="true" />;
}
```
If `?react` import not configured, fallback to `<img src={`/media/grocery-icons/${cat}.svg`} alt="" aria-hidden="true" />` — choose one and keep consistent (prefer inline for `currentColor`).

- [ ] **Step 6: Run test to verify it passes**

Run: `pnpm --dir frontend test --run src/features/grocery/__tests__/GroceryIcon.test.tsx`
Expected: PASS 5 tests

- [ ] **Step 7: Commit**

```bash
git add frontend/public/media/grocery-icons/*.svg frontend/src/components/GroceryIcon.tsx frontend/src/features/grocery/__tests__/GroceryIcon.test.tsx
git commit -m "feat(grocery): add curated SVG icons + GroceryIcon category map"
```

---

### Task 2: Grocery row integration + styles

**Files:**
- Modify: `frontend/src/features/grocery/GroceryListPage.tsx:64-68`
- Modify: `frontend/src/styles/redesign.css` (grocery section, add `.grocery-item__icon`)
- Modify: `frontend/src/styles/features.css` (if grocery base there)

**Interfaces:**
- Consumes: `GroceryIcon` from Task 1
- Produces: `GroceryRow` now renders icon left of title, grid `icon+check+1fr+auto`

- [ ] **Step 1: Write failing visual assertion (optional unit)**

Add to `GroceryIcon.test.tsx`:
```tsx
it("GroceryRow renders icon", async () => {
  const { container } = render(<div className="grocery-item__heading"><span className="grocery-item__icon"><GroceryIcon name="milk" /></span><h3>Milk</h3></div>);
  expect(container.querySelector(".grocery-item__icon svg")).toBeTruthy();
});
```

- [ ] **Step 2: Update `GroceryRow` JSX**

```tsx
// frontend/src/features/grocery/GroceryListPage.tsx:63-67
import { GroceryIcon } from "../../components/GroceryIcon";
// inside return:
<div className="grocery-item__heading">
  <span className="grocery-item__icon" aria-hidden="true"><GroceryIcon name={title} /></span>
  <label className="grocery-check"><Checkbox ... /></label>
  <div><h3>{title}</h3>...
```

- [ ] **Step 3: Add CSS for icon (DESIGN tokens)**

```css
/* frontend/src/styles/redesign.css — near .grocery-item */
.grocery-item__icon { width:2.5rem; height:2.5rem; display:grid; place-items:center; border-radius:18px; background: color-mix(in oklch, var(--color-surface-bright) 88%, var(--color-primary-container)); color: var(--color-primary); border:1px solid color-mix(in oklch, var(--color-outline-variant) 52%, transparent); flex:0 0 auto; }
.grocery-item__icon svg { width:20px; height:20px; }
.grocery-item__heading { grid-template-columns: 2.5rem 2.5rem minmax(0,1fr) auto; }
.grocery-item--checked .grocery-item__icon { opacity:0.62; }
@media (max-width: 767px) {
  .grocery-item__icon { width:2.25rem; height:2.25rem; border-radius:16px; }
  .grocery-item__icon svg { width:18px; height:18px; }
  .grocery-item__heading { grid-template-columns: 2.25rem 2.5rem minmax(0,1fr); }
}
```

Verify no raw hex, only vars.

- [ ] **Step 4: Run frontend tests + typecheck**

Run: `pnpm --dir frontend test --run` and `pnpm --dir frontend typecheck`
Expected: PASS, no TS errors for `GroceryIcon` import

- [ ] **Step 5: Manual check at 390×844 (dev)**

Run: `pnpm --dir frontend build` then `pnpm --dir frontend exec playwright test --grep grocery` or open `http://localhost:5173/app/grocery` at 390 width — icon visible left of title, wraps correctly, no overflow before `grocery-item__controls`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/grocery/GroceryListPage.tsx frontend/src/styles/redesign.css frontend/src/styles/features.css
git commit -m "feat(grocery): render category icon in GroceryRow, 2.5rem token tile"
```

---

### Task 3: Recipes mobile 1-per-row (A)

**Files:**
- Modify: `frontend/src/styles/redesign.css:331,666`
- Modify: `frontend/src/styles/features.css:626,646`
- Test: `frontend/e2e/responsive.spec.ts` (or `recipes.spec.ts`)

**Interfaces:**
- Consumes: `RecipeCard` + `RecipeMedia` + `RecipeFallbackArt` (unchanged)
- Produces: `.recipe-grid` is `1fr` below 767px, `repeat(2,1fr)` at ≥768px

- [ ] **Step 1: Write failing e2e assertion**

```ts
// frontend/e2e/responsive.spec.ts
import { expect, test } from "@playwright/test";
test("recipes grid is 1-col on mobile, 2-col on desktop", async ({ page }) => {
  await page.goto("/app/recipes");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".recipe-grid").first()).toHaveCSS("grid-template-columns", /1fr/);
  await page.setViewportSize({ width: 1024, height: 900 });
  await expect(page.locator(".recipe-grid").first()).toHaveCSS("grid-template-columns", /repeat\(2/);
});
```
If no `responsive.spec.ts`, add to `recipes.spec.ts`.

- [ ] **Step 2: Run to verify fails (currently 2-col at 390)**

Run: `pnpm --dir frontend exec playwright test responsive --project chromium`
Expected: FAIL at 390 — expected `1fr` got `repeat(2`

- [ ] **Step 3: Patch CSS — single breakpoint 767px**

```css
/* frontend/src/styles/redesign.css */
@media (min-width: 768px) {
  .recipe-library-page .recipe-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.35rem 0.75rem; }
}
@media (max-width: 767px) {
  .recipe-library-page .recipe-grid { grid-template-columns: 1fr; gap: 1rem; }
}
/* remove old 390-only 1fr rule at :666, keep no duplicate */

/* frontend/src/styles/features.css */
@media (min-width: 768px) {
  .recipe-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 767px) {
  .recipe-grid { grid-template-columns: 1fr; gap: 1.75rem; }
}
```

- [ ] **Step 4: Run e2e to verify passes**

Run: `pnpm --dir frontend exec playwright test responsive --project chromium`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/styles/redesign.css frontend/src/styles/features.css frontend/e2e/responsive.spec.ts
git commit -m "feat(recipes): mobile 1-per-row (<768px), desktop 2-col unchanged"
```

---

### Task 4: Logo sync — `BrandMark` + brand assets

**Files:**
- Modify: `frontend/src/components/index.tsx:24` (if needed)
- Modify: `frontend/public/brand/*` (regenerated PNGs/ico)
- Modify: `frontend/public/manifest.webmanifest` (if icons regenerated)
- Create: `frontend/src/components/__tests__/BrandMark.test.tsx`

**Interfaces:**
- Consumes: new SVG file in `frontend/public/brand/` (determined via git diff)
- Produces: `BrandMark` renders new mark everywhere, PWA icons consistent

- [ ] **Step 1: Determine new logo file**

Run: `git diff HEAD -- frontend/public/brand/ && git log --oneline -10 -- frontend/public/brand frontend/src/app/App.tsx`
Expected: shows which `cookfully-mark.svg` or `cookfully-logo.svg` was updated for the rail. Log chosen file in commit message (e.g., "brand: sync new cookfully-mark.svg to BrandMark + favicons").

- [ ] **Step 2: Update `BrandMark` if new filename**

If rail introduced `cookfully-logo.svg`, change:
```tsx
// frontend/src/components/index.tsx:24
export function BrandMark({ className = "" }: { className?: string }) {
  return <img className={`brand-mark ${className}`} src="/brand/cookfully-logo.svg" alt="" aria-hidden="true" />;
}
```
If refreshed `cookfully-mark.svg`, no code change — just ensure the file on disk is the new one (copy traced SVG over `public/brand/cookfully-mark.svg`).

- [ ] **Step 3: Regenerate brand derivatives (only if SVG changed)**

Run (requires `sharp`):
```bash
node -e "
import sharp from 'sharp';
const src='frontend/public/brand/cookfully-mark.svg';
for(const [out,size] of [['apple-touch-icon.png',180],['cookfully-icon-192.png',192],['cookfully-icon-512.png',512],['icon-maskable-512.png',512],['favicon-32.png',32],['favicon-48.png',48],['cookfully-mark-512.png',512],['cookfully-mark.png',256]]) {
  await sharp(src).resize(size,size).png().toFile('frontend/public/brand/'+out);
}
await sharp('frontend/public/brand/cookfully-mark.svg').resize(48,48).toFile('frontend/public/brand/favicon.ico');
"
```
If `sharp` unavailable, use `svgo` + manual export. Update `manifest.webmanifest` `icons` `src`/`sizes` if filenames changed (keep `purpose: any maskable`).

- [ ] **Step 4: Write failing test for BrandMark**

```tsx
// frontend/src/components/__tests__/BrandMark.test.tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrandMark } from "../index";
describe("BrandMark", () => {
  it("renders new mark with aria-hidden", () => {
    const { container } = render(<BrandMark />);
    const img = container.querySelector("img.brand-mark") as HTMLImageElement;
    expect(img).toBeTruthy();
    expect(img.getAttribute("aria-hidden")).toBe("true");
    expect(img.getAttribute("alt")).toBe("");
    expect(img.src).toMatch(/cookfully-mark|cookfully-logo/);
  });
});
```

- [ ] **Step 5: Run to verify**

Run: `pnpm --dir frontend test --run src/components/__tests__/BrandMark.test.tsx`
Expected: PASS; then `pnpm --dir frontend typecheck` PASS

- [ ] **Step 6: Visual check 1440×900 + 390×844**

Open `http://localhost:5173/app` (rail), `/` login, `/app` error boundary — mark is crisp, 20px rail centered, mobile top 18px wordmark, auth card brand aligned, favicon at 16/32.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/index.tsx frontend/public/brand/* frontend/public/manifest.webmanifest frontend/src/components/__tests__/BrandMark.test.tsx
git commit -m "feat(brand): sync new rail mark to BrandMark + favicons/manifest"
```

---

## Self-Review Checklist

- Spec coverage: Grocery icons (§4) → Task 1+2, Mobile 1-per-row (§5) → Task 3, Logo sync (§6) → Task 4. No gaps.
- No placeholders: all file paths exact, code blocks complete, commands with expected output.
- Type consistency: `GroceryIcon` + `categoryFor` names reused in Task 2, `BrandMark` unchanged signature.
- Scope: three slices are independent but small; each task independently testable and revertible — single plan is appropriate, no need to split.
