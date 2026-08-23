# Grocery icons, mobile single-column, and logo sync — Design

**Date:** 2026-08-23
**Status:** Approved (Approach 1)
**Scope:** Three independent polish slices shipped together — grocery C/B → curated icons, recipes 1-per-row on mobile, rail new logo → everywhere. No backend, no model, no new routes.
**Source of truth:** `DESIGN.md` v3.0 + Home at `/app` + `critique-UI.md`. `IDEAS.md:53` new requests.

---

## 1. Goals / Non-goals

**Goals**
- Replace generic C/B initial fallback on `GroceryListPage.tsx:64` `GroceryRow` with calm, category icons traced from `frontend/public/media/grocery-icons/` (9 PNG screenshots).
- Make `RecipeLibraryPage.tsx:253` `.recipe-grid` 1-per-row on mobile (<768px), cards scale to viewport; desktop ≥768px keeps 2+ cols.
- Sync the new rail mark (`App.tsx:196` `BrandMark`) to every other surface (`App.tsx:219` mobile top, `GlobalErrorBoundary.tsx:25`, `providers.tsx:21/40`, `frontend/public/brand/*`, `manifest.webmanifest`).

**Non-goals**
- No per-SKU exact icon via `food_references`, no new `RecipeCard` variant, no new brand family (mark/wordmark/stacked) — deferred.
- No grocery API change, no pantry-expiry model, no new taxonomy (tags/cuisine) — out of scope.

Persona test: all three help plan/cook/shop with less friction without adding admin.

---

## 2. Chosen approach (Approach 1 — lightweight, DESIGN-aligned)

Trace the 9 PNGs → optimized SVGs, single `GroceryIcon` mapping by keyword, one CSS breakpoint to `1fr`, central `BrandMark` swap + regenerated favicons. Reversible, no new deps, respects editorial kitchen tokens.

Alternatives considered: (2) exact food → icon + `RecipeCard--compact` + full `BrandLogo` component (precise but over-engineered), (3) emoji/lucide `::before` + JS media query + global find/replace (fast but inconsistent). Rejected for scope/calm reasons.

---

## 3. Architecture

```
frontend/public/media/grocery-icons/*.svg  ← traced from Screenshot 2026-08-23 1434*.png (svgo)
frontend/src/components/GroceryIcon.tsx    ← categoryFor(name) → Category → SVG
frontend/src/features/grocery/GroceryListPage.tsx:64 GroceryRow  ← renders <GroceryIcon>
frontend/src/styles/redesign.css:331 + features.css:626/646  ← mobile 1fr
frontend/src/components/index.tsx:24 BrandMark  ← single source for mark
frontend/public/brand/* + manifest.webmanifest  ← regenerated from new SVG
```

Isolation: grocery icon is purely presentational (no backend), mobile is CSS-only, logo is asset-only. Each slice is independently reviewable and independently revertible.

---

## 4. Slice 1 — Grocery icons

**Components**
- `frontend/public/media/grocery-icons/*.svg` (9): `produce.svg`, `dairy.svg`, `bakery.svg`, `meat.svg`, `pantry.svg`, `frozen.svg`, `beverage.svg`, `household.svg`, `other.svg`. Traced manually or with `potrace`/`Image Trace`, then `svgo` (`viewBox 0 0 24 24`, `stroke="currentColor" fill="none"`, `stroke-width 1.6`).
- `frontend/src/components/GroceryIcon.tsx`:
  ```ts
  type Category = "produce"|"dairy"|"bakery"|"meat"|"pantry"|"frozen"|"beverage"|"household"|"other";
  function categoryFor(name: string): Category // lowercases, keyword includes
  // dairy: milk, cheese, yogurt, butter, cream, ghee
  // produce: tomato, lettuce, apple, banana, spinach, onion, potato, herb, berry, carrot, cucumber, avocado
  // bakery: bread, roll, bagel, croissant, bun, pita, dough
  // meat: chicken, beef, pork, fish, salmon, turkey, mutton, paneer? → actually dairy/paneer → pantry? keep meat for fish/meat
  // pantry: rice, pasta, oil, flour, sugar, salt, spice, lentil, chickpea, honey
  // frozen: frozen, ice
  // beverage: water, juice, wine, coffee, tea, soda
  // household: paper, soap, detergent
  // other: fallback (basket icon)
  export function GroceryIcon({ name, className }: { name: string; className?: string }) // renders <img src={`/media/grocery-icons/${categoryFor(name)}.svg`} aria-hidden />
  // or inline SVG via import to allow currentColor theming — prefer inline <svg> via React component per category for token control
  ```
- `GroceryRow` update (`frontend/src/features/grocery/GroceryListPage.tsx:64`):
  ```tsx
  <span className="grocery-item__icon" aria-hidden="true"><GroceryIcon name={title} /></span>
  ```
  Inside `grocery-item__heading` before `<h3>`. Grid changes:
  - Desktop: `grid-template-columns: 2.5rem(icon) 2.5rem(check) minmax(0,1fr) auto`
  - Mobile (<768px): `2.25rem 2.5rem minmax(0,1fr)` (controls drop to absolute as before but icon stays)

**Styling** (`frontend/src/styles/redesign.css` grocery section + `features.css`):
- `.grocery-item__icon { width:2.5rem; height:2.5rem; display:grid; place-items:center; border-radius:18px; background: color-mix(in oklch, var(--color-surface-bright) 88%, var(--color-primary-container)); color: var(--color-primary); border:1px solid color-mix(in oklch, var(--color-outline-variant) 52%, transparent); }`
- `.grocery-item__icon svg { width:20px; height:20px; }`
- Checked: `.grocery-item--checked .grocery-item__icon { opacity:0.62; }`
- Icons are decorative (`aria-hidden`), text `h3` remains the accessible name.

**Data flow / fallback:** No API. `categoryFor` is pure, no network. If `title` empty or no keyword matches → `other.svg`. Ultimate fallback if SVG fails → CSS square remains, no broken layout.

**Error & a11y:** No PII. Keyboard/focus unchanged (icon not focusable). Contrast: `primary` on `primary-container` mix passes AA for icon stroke vs bg (icon is decorative, not text). `prefers-reduced-motion` untouched.

**Testing**
- `frontend/src/features/grocery/__tests__/GroceryIcon.test.tsx`: 9 category cases + `other` + empty, asserts `svg[aria-hidden]` and `categoryFor` mapping, no `alt` on decorative.
- Visual: `grocery-list.spec.ts` at 390×844 — no overflow, `grocery-item__icon` visible, `grocery-items` still `1fr` on mobile.

---

## 5. Slice 2 — Recipes mobile 1-per-row

**Current:** `frontend/src/styles/redesign.css:331` `repeat(2,1fr)` + `features.css:626` apply down to ~391px; only `redesign.css:666` + `features.css:646` drop to `1fr` below that. At 390×844 two small cards squeeze side-by-side.

**Change (desktop untouched):**
- `frontend/src/styles/redesign.css`:
  ```css
  /* keep desktop 2-col */
  @media (min-width: 768px) {
    .recipe-library-page .recipe-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.35rem 0.75rem; }
  }
  @media (max-width: 767px) {
    .recipe-library-page .recipe-grid { grid-template-columns: 1fr; gap: 1rem; }
  }
  ```
  Remove the old `@media (max-width: ...)` 1fr at 390 — replaced by 767.
- `frontend/src/styles/features.css:626/646` similarly scoped to `min-width:768px` vs `max-width:767px` (single breakpoint, no duplicate).
- No `RecipeLibraryPage.tsx:253` JS change. `RecipeCard` keeps vertical contract: `RecipeMedia` 4:3, `thumbnailCrop` `object-position` via CSS vars, `RecipeFallbackArt` fallback art scales `object-fit:cover`, `RecipeMetadata` flex-wraps (time/servings line 1, kcal/P/C/F line 2). Title `line-clamp:2` at 2 lines.

**Responsive inheritance (DESIGN.md):** desktop/tablet ≥768px = 112px rail, `page-desktop:48px` inset; mobile <768px = compact top bar + 72px `MobileNav` (5 equal hits, safe-area), `page-mobile:16px` inset. No page-entry transform on mobile.

**Error & overflow:** collections `+N` badge, favorite toggle, menu stay in `recipe-card` overflow hidden. Gap change prevents horizontal scroll at 390, 360, 412.

**Testing**
- `frontend/e2e/responsive.spec.ts` + `recipes.spec.ts`: at 390 width `getComputedStyle(grid).gridTemplateColumns` is `1fr` (single column), at 1024 is `repeat(2`. No truncation of `data-value` at 390×844.
- Manual: 390×844, 360×740, 412×915 — cards fill width, fallback art not stretched.

---

## 6. Slice 3 — Logo sync

**Audit:** `BrandMark` is the single source. Current `frontend/src/components/index.tsx:24`:
```tsx
export function BrandMark({ className = "" }: { className?: string }) {
  return <img className={`brand-mark ${className}`} src="/brand/cookfully-mark.svg" alt="" aria-hidden="true" />;
}
```
Usages: `App.tsx:104` landing brand, `App.tsx:196` `planner-nav__brandmark` (rail), `App.tsx:219` `planner-shell__mobile-brand`, `GlobalErrorBoundary.tsx:25`, `providers.tsx:21/40` auth/utility screens.

**Design:**
- Determine new file: diff `frontend/public/brand/cookfully-mark.svg` vs `cookfully-logo.svg` + `git log --follow -- public/brand` + `App.tsx` rail commit. Assume rail now uses refreshed `cookfully-mark.svg` (optimized, same filename updated in working tree but not committed elsewhere). If rail actually introduced `cookfully-logo.svg`, swap `BrandMark` `src` to `/brand/cookfully-logo.svg` and keep `cookfully-mark.svg` as square favicon source — decision logged at implementation.
- Update `BrandMark` `src` to new mark (single line). No props change.
- Regenerate derivatives from new SVG via `sharp` (or `resvg`): `apple-touch-icon.png` 180, `cookfully-icon-192.png`, `cookfully-icon-512.png`, `icon-maskable-512.png` (with safe padding, `background: canvas`), `favicon-32.png`, `favicon-48.png`, `favicon.ico` (multi-size 16/32/48), `cookfully-mark-512.png`/`cookfully-mark.png`, `cookfully-social-card.jpg` 1200×630 if it embeds mark (Afacad Flux 500 wordmark + herb bg).
- `frontend/public/manifest.webmanifest` `icons` array points to regenerated `192/512/maskable`, `theme_color: "oklch(0.405 0.126 148)"` unchanged, `background_color: canvas`.
- `frontend/index.html` favicon links (`/brand/favicon-*.png`, `/brand/favicon.ico`, `/brand/apple-touch-icon.png`) unchanged paths — content regenerated.

**Fallback & QA:** if new SVG missing at build, Vite fallback to existing `cookfully-mark.svg` (no 404). Verify at 1440×900 and 390×844: rail `20px` centered mark, mobile top `18px` wordmark, auth card brand `utility-screen__brand`, error screens, PWA install icon crisp, maskable safe area, favicon at 16/32.

**Testing**
- `frontend/src/components/__tests__/BrandMark.test.tsx`: renders `img[src*=cookfully-mark]` (or `cookfully-logo` if swapped) with `aria-hidden` and `alt=""`.
- `App.test.tsx` + `SignInView.test.tsx` snapshot still shows `BrandMark` + `Cookfully` text.
- Playwright smoke: `/app` rail + `/` login favicon loads `200`.

---

## 7. Cross-cutting concerns

**Tokens & style:** All colors via `DESIGN.md` CSS vars (`--color-primary`, `--color-primary-container`, `--color-surface-*`, `--color-outline-variant`), radii `10/18/22/pill`, motion `160/220/280ms` + `ease-out`, no raw hex. No `glassmorphism`/gradients.

**Accessibility:** grocery icons `aria-hidden`, recipe grid `role="tabpanel"` unchanged, logo `alt=""` + visible `Cookfully` text, 44px targets preserved, `prefers-reduced-motion` respected, keyboard order = visual order.

**Performance:** 9 SVGs ~2–3kB each, no extra JS for mobile. Logo PNGs regenerated at same sizes — no bundle growth.

**Security:** no new endpoints, no secrets.

---

## 8. File change summary

- `frontend/src/components/GroceryIcon.tsx` (new)
- `frontend/public/media/grocery-icons/*.svg` (9 new, traced from PNGs)
- `frontend/src/features/grocery/GroceryListPage.tsx` (add icon span, grid)
- `frontend/src/styles/redesign.css` + `frontend/src/styles/features.css` (breakpoint `767px` → `1fr`)
- `frontend/src/components/index.tsx` (BrandMark src if needed)
- `frontend/public/brand/*` (regenerated PNGs/ico)
- `frontend/public/manifest.webmanifest` (icons if regenerated)
- Tests: `GroceryIcon.test.tsx`, `BrandMark.test.tsx`, e2e `responsive.spec.ts` update

No backend, no migrations, no API version bump.

---

## 9. Acceptance checklist (per DESIGN.md)

- [ ] Grocery: icon visible left of title, `2.5rem` square, herb/mint, `aria-hidden`, fallback `other` works, no overflow at 390×844.
- [ ] Recipes mobile: at 390×844 `grid-template-columns: 1fr`, one card fills width, 4:3 media, fallback art scales, metadata wraps, desktop 1024 still `repeat(2`.
- [ ] Logo: `BrandMark` shows new mark on rail, mobile top, auth, error, favicons/manifest/maskable updated, 1440×900 + 390×844 crisp.
- [ ] No raw colors, radii/spacing from tokens, `prefers-reduced-motion` respected.
- [ ] Keyboard, focus, empty/loading/failed states still usable.

---

## 10. Rollout

Ship as one commit on `main` (or `grocery-icons-mobile-logo-sync` branch → PR) — three slices are small and independently revertible via `git revert`. No feature flag, no migration.
