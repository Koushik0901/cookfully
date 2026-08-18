# Recipe Library Desktop Density Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Widen the authenticated recipe library's desktop content frame so the existing three-column layout uses more of the available canvas without changing its interaction model.

**Architecture:** Keep the change at the application-shell layout boundary. Increase the existing `.page-shell` maximum width in `shell.css`, then protect the intended wide-desktop geometry and no-overflow contract with a focused Playwright test using the existing recipe API mock. Do not alter recipe-card markup, feature data, breakpoints, or the concurrent recipe feature stylesheet work.

**Tech Stack:** React 19.2, TypeScript 5.x, Vite 8.1, CSS custom properties, Playwright, pnpm 10.

## Global Constraints

- Increase the desktop `.page-shell` maximum width from `90rem` to approximately `100rem`.
- The existing three-column grid remains the desktop composition.
- Tablet retains the existing two-column breakpoint and compact navigation rail.
- Mobile retains the existing one-column grid, mobile page inset, top brand bar, and bottom navigation.
- The wider desktop maximum must not introduce document-level horizontal overflow at any breakpoint.
- Keyboard focus order and visible focus rings remain unchanged.
- Long titles continue to clamp without escaping their card.
- Images continue to use useful alt text or the existing food-specific fallback art.
- Verify at `1440x900`, a wide desktop viewport, and `390x844`.
- Do not add a fourth column, featured-card ranking, or content-model change.

---

### Task 1: Widen And Protect The Recipe Library Frame

**Files:**
- Modify: `frontend/src/styles/shell.css:131-140` (`.page-shell`)
- Modify: `frontend/e2e/recipes.spec.ts` near the existing recipe-library coverage around line 394
- Do not modify: `frontend/src/styles/features.css` because it contains concurrent unrelated worktree changes

**Interfaces:**
- Consumes: the existing `.page-shell.recipe-library-page` wrapper rendered by `RecipeLibraryPage` and the existing `mockApi(page)` helper in `frontend/e2e/recipes.spec.ts`.
- Produces: a `100rem` maximum desktop page frame and a regression test named `uses more of the wide desktop canvas for the recipe library`.

- [ ] **Step 1: Add the failing wide-desktop regression test**

Insert this test immediately before the existing `makes a focused recipe-library view easy to understand and clear` test in `frontend/e2e/recipes.spec.ts`:

```tsx
test("uses more of the wide desktop canvas for the recipe library", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await mockApi(page);
  await page.goto("/app/recipes");

  const shell = page.locator(".page-shell.recipe-library-page");
  await expect(shell).toBeVisible();

  const shellBox = await shell.boundingBox();
  expect(shellBox).not.toBeNull();
  expect(shellBox!.width).toBeGreaterThanOrEqual(1580);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
```

- [ ] **Step 2: Run the new test and confirm it fails for the old width**

Run:

```bash
pnpm --dir frontend exec playwright test e2e/recipes.spec.ts --project=desktop-chromium --grep "uses more of the wide desktop canvas"
```

Expected: FAIL because the current `90rem` maximum produces a page-shell width of `1440px`, which is below the new test's `1580px` minimum at a `1920px` viewport.

- [ ] **Step 3: Make the minimal CSS change**

In `frontend/src/styles/shell.css`, change only the `.page-shell` width declaration from:

```css
width: min(100%, 90rem);
```

to:

```css
width: min(100%, 100rem);
```

Leave its padding, margin, gap, animation, and every responsive override unchanged. This makes the wide desktop frame `1600px` when the remaining application content area is at least that wide, while preserving fluid width on smaller viewports.

- [ ] **Step 4: Run the focused regression and responsive checks**

Run:

```bash
pnpm --dir frontend exec playwright test e2e/recipes.spec.ts --project=desktop-chromium --grep "uses more of the wide desktop canvas"
pnpm --dir frontend exec playwright test e2e/responsive.spec.ts
```

Expected: both commands pass. The first confirms the wider three-column frame and the second confirms no document overflow across configured desktop, mobile, and tablet layout checks.

- [ ] **Step 5: Run the frontend quality gates**

Run:

```bash
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
```

Expected: all commands exit successfully with no lint, type, unit-test, or production-build errors.

- [ ] **Step 6: Review the required viewport states**

Run the recipe-library e2e coverage with the existing screenshot capture support if visual artifacts are desired:

```bash
pnpm --dir frontend exec playwright test e2e/recipes.spec.ts --project=desktop-chromium --grep "focused recipe-library"
pnpm --dir frontend exec playwright test e2e/responsive.spec.ts --project=narrow-mobile
```

Inspect the result at `1440x900` and `390x844`. Confirm that the desktop side field is reduced, the three card columns remain image-led, the header/search/grid edges align, mobile remains one column, long content does not overflow, and focusable controls retain their existing keyboard behavior.

- [ ] **Step 7: Commit the focused implementation**

```bash
git add frontend/src/styles/shell.css frontend/e2e/recipes.spec.ts
git commit -m "feat: widen recipe library desktop frame"
```
