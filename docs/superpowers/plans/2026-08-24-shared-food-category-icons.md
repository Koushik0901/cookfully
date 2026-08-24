# Shared Food Category Icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old monochrome/initial food visuals with the supplied illustrated PNG icon system through one shared `FoodCategoryIcon` component used by Grocery, Pantry, and Home.

**Architecture:** `FoodCategoryIcon.tsx` owns the 13-category keyword matcher, asset URLs, fallback, accessibility, and size classes. Screens render only the component with a food name and context size; supplied `*-64.png` and manifest base `*.png` assets are versioned under `frontend/public/media/grocery-icons/` and selected through `srcSet`.

**Tech Stack:** React 19.2, TypeScript 5.x, Vite 8.1, Vitest, Testing Library, PNG assets, CSS custom properties from `DESIGN.md` v3.0

## Global Constraints

- Use the supplied illustrated assets from `frontend/public/media/grocery-icons/`; do not recreate them as new monochrome SVGs.
- A category rule or asset change must be made once in `FoodCategoryIcon.tsx` and affect every consumer.
- Consumers must not import category assets, call the matcher directly, render initials, or define category fallbacks.
- Use `64px` as the normal source and `256px` through `srcSet` for high-density displays.
- Food illustrations are decorative: render `alt=""` and `aria-hidden="true"` without duplicate accessible names.
- Preserve existing wrappers and responsive layout; verify desktop, `390×844`, keyboard access, and HMR.
- Use existing oklch design tokens; add no raw colors or per-screen icon sizing rules.
- Do not add backend/API category fields.

---

## File Structure

- **Create:** `frontend/src/components/FoodCategoryIcon.tsx` — single public mapping, asset, fallback, accessibility, and size contract.
- **Create:** `frontend/src/components/__tests__/FoodCategoryIcon.test.tsx` — category, asset, size, fallback, and accessibility tests.
- **Modify:** `.gitignore:33` — unignore the supplied icon PNGs and `manifest.json` so the new source assets ship in Git.
- **Delete:** `frontend/src/components/GroceryIcon.tsx` — remove the obsolete monochrome component after consumers migrate.
- **Delete:** `frontend/public/media/grocery-icons/{bakery,beverage,dairy,frozen,household,meat,other,pantry,produce}.svg` — remove obsolete artwork; the supplied PNG set is canonical.
- **Modify:** `frontend/src/features/grocery/GroceryListPage.tsx` — use `FoodCategoryIcon size="tile"`.
- **Modify:** `frontend/src/features/pantry/PantryPage.tsx` — use shared icon for shelf and use-soon rows.
- **Modify:** `frontend/src/features/home/HomePage.tsx` — use shared icon for Home use-soon rows.
- **Modify:** `frontend/src/styles/features.css`, `frontend/src/styles/home.css`, `frontend/src/styles/redesign.css` — remove consumer icon sizing overrides and retain wrapper/layout styling.
- **Modify:** `frontend/src/features/grocery/__tests__/GroceryIcon.test.tsx` — migrate to the new component or replace with the shared component test.
- **Modify/Create:** `frontend/e2e/responsive.spec.ts` or focused icon e2e test — verify icons at desktop and 390×844.

---

### Task 1: Version the supplied assets and build the shared component

**Files:**
- Modify: `.gitignore:33`
- Create: `frontend/src/components/FoodCategoryIcon.tsx`
- Create: `frontend/src/components/__tests__/FoodCategoryIcon.test.tsx`
- Delete: `frontend/src/components/GroceryIcon.tsx`
- Delete: `frontend/public/media/grocery-icons/bakery.svg`, `beverage.svg`, `dairy.svg`, `frozen.svg`, `household.svg`, `meat.svg`, `other.svg`, `pantry.svg`, `produce.svg`
- Include: all supplied `frontend/public/media/grocery-icons/*-64.png`, base `*.png`, `*-native.png`, and `manifest.json`

**Interfaces:**
- Produces `Category = "leafy-greens" | "grains-rice" | "dairy-milk" | "fruit" | "vegetables" | "pantry-sauce" | "bread-bakery" | "protein-chicken" | "herbs-spices" | "beverages-drinks" | "seafood" | "eggs" | "snacks"`.
- Produces `categoryFor(name: string): Category` for tests only; consumers use `FoodCategoryIcon`.
- Produces `FoodCategoryIcon({ name: string; size?: "compact" | "row" | "tile"; className?: string }): JSX.Element`.

- [ ] **Step 1: Add the asset-folder Git exception and write failing tests**

Add after `.gitignore` line 33:

```gitignore
media/
!frontend/public/media/
!frontend/public/media/grocery-icons/
!frontend/public/media/grocery-icons/*.png
!frontend/public/media/grocery-icons/manifest.json
```

Create tests that assert the 13 category fixtures render the corresponding `*-64.png`, `srcset` contains the matching base `*.png` asset as `256w`, unknown names resolve to `pantry-sauce-64.png`, `eggplant` resolves to vegetables, `milkshake` resolves to beverages, `frozen vegetables` resolves to vegetables, plural/case normalization works, and size/accessibility classes exist.

```tsx
const fixtures = [
  ["spinach", "leafy-greens"], ["rice", "grains-rice"], ["milk", "dairy-milk"],
  ["apple", "fruit"], ["tomato", "vegetables"], ["pasta sauce", "pantry-sauce"],
  ["bread", "bread-bakery"], ["chicken", "protein-chicken"], ["basil", "herbs-spices"],
  ["coffee", "beverages-drinks"], ["salmon", "seafood"], ["eggs", "eggs"], ["granola bar", "snacks"],
] as const;

it.each(fixtures)("maps %s to %s", (name, category) => {
  expect(categoryFor(name)).toBe(category);
  const { container } = render(<FoodCategoryIcon name={name} />);
  const image = container.querySelector("img");
  expect(image).toHaveAttribute("src", `/media/grocery-icons/${category}-64.png`);
  expect(image).toHaveAttribute("srcset", expect.stringContaining(`${category}.png 256w`));
  expect(image).toHaveAttribute("alt", "");
  expect(image).toHaveAttribute("aria-hidden", "true");
});

it("uses the pantry sauce fallback and size class", () => {
  const { container } = render(<FoodCategoryIcon name="unclassified item" size="row" />);
  expect(container.querySelector(".grocery-icon--pantry-sauce.grocery-icon--size-row")).toBeTruthy();
});

it("keeps specific terms ahead of broad terms", () => {
  expect(categoryFor("eggplant")).toBe("vegetables");
  expect(categoryFor("milkshake")).toBe("beverages-drinks");
  expect(categoryFor("frozen vegetables")).toBe("vegetables");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm --dir frontend test --run src/components/__tests__/FoodCategoryIcon.test.tsx`
Expected: FAIL because `FoodCategoryIcon` and the new category map do not exist.

- [ ] **Step 3: Implement the single source of truth**

```tsx
// frontend/src/components/FoodCategoryIcon.tsx
import type { ImgHTMLAttributes } from "react";

export type Category =
  | "leafy-greens" | "grains-rice" | "dairy-milk" | "fruit" | "vegetables"
  | "pantry-sauce" | "bread-bakery" | "protein-chicken" | "herbs-spices"
  | "beverages-drinks" | "seafood" | "eggs" | "snacks";

const CATEGORY_RULES: Array<[Category, RegExp]> = [
  ["vegetables", /\b(frozen vegetables?|tomato(?:es)?|carrot(?:s)?|potato(?:es)?|broccoli|cauliflower|celery|cucumber|zucchini|pepper(?:s)?|mushroom(?:s)?|eggplant|corn|peas|beans|cabbage|asparagus|radish|leek)\b/i],
  ["beverages-drinks", /\b(milkshake|smoothie|water|coffee|tea|soda|juice|wine|beer|drink|beverage)\b/i],
  ["eggs", /\beggs?\b/i],
  ["seafood", /\b(fish|salmon|shrimp|tuna|cod|seafood)\b/i],
  ["protein-chicken", /\b(chicken|beef|pork|turkey|tofu|meat|sausage|bacon)\b/i],
  ["dairy-milk", /\b(milk|cheese|yogurt|yoghurt|butter|cream|ghee|paneer)\b/i],
  ["leafy-greens", /\b(spinach|lettuce|kale|arugula|collard|chard|greens)\b/i],
  ["herbs-spices", /\b(herb|basil|cilantro|coriander|parsley|mint|oregano|rosemary|thyme|spice)\b/i],
  ["fruit", /\b(apple|banana|berry|berries|strawberr(?:y|ies)|blueberr(?:y|ies)|raspberr(?:y|ies)|grape|lemon|lime|orange|avocado|melon|peach|pear|fruit)\b/i],
  ["bread-bakery", /\b(bread|roll|bagel|croissant|bun|pita|dough|tortilla|bakery)\b/i],
  ["grains-rice", /\b(rice|pasta|flour|oat(?:s|meal)?|quinoa|barley|couscous|cereal|grain)\b/i],
  ["pantry-sauce", /\b(sauce|canned|can|oil|vinegar|condiment|honey|syrup|sugar|salt|lentil|chickpea|bean)\b/i],
  ["snacks", /\b(snack|chip|cracker|nut|nuts|granola|popcorn|pretzel)\b/i],
];

const ASSET_CATEGORIES: Record<Category, string> = {
  "leafy-greens": "leafy-greens", "grains-rice": "grains-rice", "dairy-milk": "dairy-milk",
  fruit: "fruit", vegetables: "vegetables", "pantry-sauce": "pantry-sauce",
  "bread-bakery": "bread-bakery", "protein-chicken": "protein-chicken", "herbs-spices": "herbs-spices",
  "beverages-drinks": "beverages-drinks", seafood: "seafood", eggs: "eggs", snacks: "snacks",
};

export function categoryFor(name: string): Category {
  const normalized = name.trim();
  for (const [category, rule] of CATEGORY_RULES) if (rule.test(normalized)) return category;
  return "pantry-sauce";
}

const SIZE_CLASS: Record<NonNullable<FoodCategoryIconProps["size"]>, string> = {
  compact: "grocery-icon--size-compact", row: "grocery-icon--size-row", tile: "grocery-icon--size-tile",
};

export type FoodCategoryIconProps = {
  name: string;
  size?: "compact" | "row" | "tile";
  className?: string;
};

export function FoodCategoryIcon({ name, size = "compact", className = "" }: FoodCategoryIconProps) {
  const category = categoryFor(name);
  const asset = ASSET_CATEGORIES[category];
  const attrs: ImgHTMLAttributes<HTMLImageElement> = {
    className: `grocery-icon grocery-icon--${category} ${SIZE_CLASS[size]} ${className}`.trim(),
    src: `/media/grocery-icons/${asset}-64.png`,
    srcSet: `/media/grocery-icons/${asset}-64.png 64w, /media/grocery-icons/${asset}.png 256w`,
    sizes: size === "tile" ? "32px" : size === "row" ? "28px" : "24px",
    alt: "",
    "aria-hidden": true,
  };
  return <img {...attrs} />;
}
```

Use `localeCompare`/word-boundary regex patterns carefully; avoid substring errors such as `egg` in `veggie` and `milk` in `milkshake` being classified as dairy.

- [ ] **Step 4: Run tests and asset checks**

Run: `pnpm --dir frontend test --run src/components/__tests__/FoodCategoryIcon.test.tsx`
Expected: all category, fallback, precedence, size, and accessibility tests pass.

Run: `git check-ignore -v frontend/public/media/grocery-icons/fruit-64.png` and `git status --short frontend/public/media/grocery-icons`
Expected: the PNGs and `manifest.json` are no longer ignored and appear as addable files; obsolete SVGs appear deleted.

- [ ] **Step 5: Commit the shared component and canonical assets**

```bash
git add .gitignore frontend/src/components/FoodCategoryIcon.tsx frontend/src/components/__tests__/FoodCategoryIcon.test.tsx frontend/public/media/grocery-icons frontend/src/components/GroceryIcon.tsx
git commit -m "feat(ui): make illustrated food icons a shared source of truth"
```

---

### Task 2: Migrate all food-item consumers and remove local icon rules

**Files:**
- Modify: `frontend/src/features/grocery/GroceryListPage.tsx`
- Modify: `frontend/src/features/pantry/PantryPage.tsx`
- Modify: `frontend/src/features/home/HomePage.tsx`
- Modify: `frontend/src/styles/features.css`, `frontend/src/styles/home.css`, `frontend/src/styles/redesign.css`
- Modify: `frontend/src/features/grocery/__tests__/GroceryIcon.test.tsx` or delete after coverage moves to shared test
- Test: consumer component tests where available

**Interfaces:**
- Consumes: `FoodCategoryIcon` from Task 1.
- Produces: no screen-specific category logic or initial-letter renderers.

- [ ] **Step 1: Write failing consumer assertions**

Add assertions to the existing consumer tests or focused tests:

```tsx
expect(container.querySelector(".pantry-staple__stamp img.grocery-icon")).toBeTruthy();
expect(container.querySelector(".pantry-attention__icon img.grocery-icon")).toBeTruthy();
expect(container.querySelector(".home-use-soon__produce img.grocery-icon")).toBeTruthy();
expect(container.textContent).not.toContain("G");
```

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `pnpm --dir frontend test --run src/features/grocery/__tests__/GroceryIcon.test.tsx src/features/pantry/__tests__/PantryUseSoon.test.tsx`
Expected: consumer assertions fail for existing initial-letter or obsolete component markup.

- [ ] **Step 3: Migrate consumers**

Replace imports and renderers:

```tsx
import { FoodCategoryIcon } from "../../components/FoodCategoryIcon";

<FoodCategoryIcon name={title} size="tile" />
<FoodCategoryIcon name={item.displayName} size="tile" />
<FoodCategoryIcon name={item.displayName} size="row" />
```

Delete all initial-letter expressions from Grocery, Pantry, and Home. Do not duplicate category matching in the screen files.

- [ ] **Step 4: Remove local icon sizing overrides**

Keep wrapper rules such as `.pantry-staple__stamp` and `.home-use-soon__produce`, but remove selectors that set `.grocery-icon` width/height inside individual screens. Add shared sizing once in `features.css`:

```css
.grocery-icon { display: block; width: 1.5rem; height: 1.5rem; object-fit: contain; }
.grocery-icon--size-compact { width: 1.25rem; height: 1.25rem; }
.grocery-icon--size-row { width: 1.5rem; height: 1.5rem; }
.grocery-icon--size-tile { width: 1.75rem; height: 1.75rem; }
```

Preserve existing wrapper colors and `390×844` layout. Remove the obsolete `font-family`/font-size icon styling only if it exists solely for initials.

- [ ] **Step 5: Run focused tests and static checks**

Run: `pnpm --dir frontend test --run src/components/__tests__/FoodCategoryIcon.test.tsx src/features/grocery/__tests__/GroceryIcon.test.tsx src/features/pantry/__tests__/PantryUseSoon.test.tsx`
Expected: all focused tests pass and no test relies on SVG markup from the removed component.

Run: `pnpm --dir frontend lint` and `pnpm --dir frontend typecheck`
Expected: exit 0 with no warnings/errors.

- [ ] **Step 6: Commit consumer migration**

```bash
git add frontend/src/features/grocery/GroceryListPage.tsx frontend/src/features/pantry/PantryPage.tsx frontend/src/features/home/HomePage.tsx frontend/src/styles/features.css frontend/src/styles/home.css frontend/src/styles/redesign.css frontend/src/features/grocery/__tests__
git commit -m "refactor(ui): use shared food category icons across grocery pantry and home"
```

---

### Task 3: Browser verification and HMR delivery

**Files:**
- Modify: `frontend/e2e/responsive.spec.ts` or create `frontend/e2e/food-category-icons.spec.ts`

**Interfaces:**
- Consumes: Task 2 shared component adoption.
- Produces: browser evidence that all visible food-item surfaces use the supplied illustrations at desktop and mobile.

- [ ] **Step 1: Add browser assertions**

```ts
test("food item surfaces render illustrated category images", async ({ page }) => {
  await page.goto("/app");
  await expect(page.locator(".home-use-soon__produce img.grocery-icon").first()).toBeVisible();
  await page.goto("/app/pantry");
  await expect(page.locator(".pantry-staple__stamp img.grocery-icon").first()).toBeVisible();
});
```

Use existing authenticated fixture/setup and route availability patterns. Do not assert a specific user item unless the fixture supplies it.

- [ ] **Step 2: Run browser tests at desktop and mobile**

Run: `pnpm --dir frontend exec playwright test frontend/e2e/food-category-icons.spec.ts`
Expected: pass at the configured desktop and mobile projects; no initial-letter fallback is visible.

- [ ] **Step 3: Run complete frontend verification**

Run: `pnpm --dir frontend test --run`
Expected: all frontend test files pass.

Run: `pnpm --dir frontend lint && pnpm --dir frontend typecheck && pnpm --dir frontend build`
Expected: all commands exit 0.

- [ ] **Step 4: Verify the running Vite HMR path**

Keep the local server running with:

```powershell
pnpm --dir frontend dev --host 127.0.0.1
```

Open `http://127.0.0.1:5173/app` and `http://127.0.0.1:5173/app/pantry`. Confirm the browser loads `/media/grocery-icons/*-64.png`, the selected element is an `IMG` rather than text, and a component/mapping edit updates without a Docker rebuild.

- [ ] **Step 5: Commit browser test/docs if changed**

```bash
git add frontend/e2e/food-category-icons.spec.ts
git commit -m "test(ui): verify illustrated food icons across responsive surfaces"
```

## Self-Review Checklist

- Spec architecture → Task 1 owns matching/assets/accessibility/sizes; Tasks 2-3 consume only the component.
- All 13 supplied categories are mapped, including new beverages, seafood, eggs, and snacks.
- `pantry-sauce` is the explicit fallback, so no missing asset can reintroduce initials.
- `.gitignore` exception versions the user-supplied PNG assets and `manifest.json`.
- Old SVG imports/assets and first-letter renderers are removed.
- `srcSet` uses `64px` normal and `256px` high-density assets.
- Accessibility, 390×844 layout, keyboard, HMR, tests, lint, typecheck, and build are covered.
- No backend/API or unrelated feature changes are included.
