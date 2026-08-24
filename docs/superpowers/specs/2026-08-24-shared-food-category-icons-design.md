# Shared Food Category Icons — Design

Date: 2026-08-24
Status: Approved design, pending implementation plan

## Goal

Make the illustrated grocery icons a single source of truth across Grocery, Pantry, Home, and future food-item surfaces. Changing an asset or category mapping once must update every surface without screen-specific icon logic.

The updated source assets live in `frontend/public/media/grocery-icons/`. They use the intended illustrated dark-green circular badge style and provide `64px`, `256px`, and native PNG variants plus `manifest.json`.

## Current Problem

`frontend/src/components/GroceryIcon.tsx` currently imports the old monochrome SVG set. Grocery uses that component, but Pantry and Home previously rendered first letters independently. Pantry now uses the old component, and Home is being migrated, but the asset selection, sizing, and fallback behavior are not yet one complete contract.

## Architecture

Create `frontend/src/components/FoodCategoryIcon.tsx` as the only public food-category icon component.

```tsx
<FoodCategoryIcon name={item.displayName} size="row" />
```

The component owns:

- the `Category` type;
- normalized keyword matching and priority order;
- category-to-asset mapping;
- `64px` and `256px` asset URLs;
- the fallback category;
- decorative accessibility behavior (`alt=""`, `aria-hidden="true"`);
- shared size classes (`compact`, `row`, `tile`).

Consumers provide only a food name and visual context size. They must not import category assets, call the matcher directly, render initials, or define their own category fallback.

The implementation uses public PNG assets rather than the old SVG imports. The `*-64.png` image is the normal source and the manifest's base `*.png` image is the `256px` source provided through `srcSet` for high-density displays. The wrapper shape and surrounding layout remain consumer concerns.

## Asset Taxonomy

The canonical categories and assets are:

| Category | Asset | Typical matches |
|---|---|---|
| `leafy-greens` | `leafy-greens-64.png` / `leafy-greens.png` | spinach, lettuce, kale, arugula, collard greens |
| `grains-rice` | `grains-rice-64.png` / `grains-rice.png` | rice, pasta, oats, flour, quinoa, barley, cereal |
| `dairy-milk` | `dairy-milk-64.png` / `dairy-milk.png` | milk, cheese, yogurt, butter, cream, ghee, paneer |
| `fruit` | `fruit-64.png` / `fruit.png` | apples, bananas, berries, citrus, grapes, avocado |
| `vegetables` | `vegetables-64.png` / `vegetables.png` | tomatoes, carrots, potatoes, broccoli, peppers, mushrooms |
| `pantry-sauce` | `pantry-sauce-64.png` / `pantry-sauce.png` | sauces, canned goods, oil, vinegar, condiments |
| `bread-bakery` | `bread-bakery-64.png` / `bread-bakery.png` | bread, rolls, bagels, tortillas, croissants |
| `protein-chicken` | `protein-chicken-64.png` / `protein-chicken.png` | chicken, beef, pork, turkey, tofu |
| `herbs-spices` | `herbs-spices-64.png` / `herbs-spices.png` | herbs and spices |
| `beverages-drinks` | `beverages-drinks-64.png` / `beverages-drinks.png` | water, coffee, tea, soda, juice, wine |
| `seafood` | `seafood-64.png` / `seafood.png` | fish, salmon, shrimp, tuna |
| `eggs` | `eggs-64.png` / `eggs.png` | egg, eggs |
| `snacks` | `snacks-64.png` / `snacks.png` | chips, crackers, nuts, granola bars |

Anything unmatched uses `pantry-sauce-64.png`. Existing `frozen`, `beverage`, `household`, and `other` categories are removed from the frontend matcher because they do not correspond to the supplied visual system. Frozen food maps to its nearest food category, beverages map to `beverages-drinks`, and household items use the neutral `pantry-sauce` fallback until a dedicated asset exists.

Matching is case-insensitive, trims whitespace, handles common singular/plural forms, and checks specific categories before broad ones. For example, `frozen vegetables` must resolve to `vegetables`, `eggplant` must resolve to `vegetables` rather than `eggs`, and `milkshake` must resolve to `beverages-drinks` rather than `dairy-milk`.

## Consumer Migration

All food-item surfaces use the component:

- `GroceryListPage` uses `size="tile"`.
- `PantryPage` shelf cards use `size="tile"`.
- `PantryPage` use-soon attention rows use `size="row"`.
- `HomePage` use-soon rows use `size="row"`.

No production food-item surface may render a first letter. The existing colored wrappers remain in place, but their SVG dimensions come from shared component size classes rather than selectors tied to individual screens.

## Styling Contract

The component emits `grocery-icon grocery-icon--<category> grocery-icon--size-<size>` classes. Shared styles define the SVG dimensions and preserve the source illustration's aspect ratio. Screen styles only define the badge wrapper, background, spacing, and responsive layout.

The icon must remain recognizable at `24–32px`, fit inside the existing `390×844` mobile layout, and inherit existing oklch design tokens. No raw colors or new per-screen icon sizing rules are introduced.

## Accessibility

Food category illustrations are decorative because the food name is already rendered as text. The component renders `alt=""` and `aria-hidden="true"`; it must not create duplicate accessible names. Existing buttons, links, headings, and item labels remain keyboard accessible.

## Verification

Unit tests verify:

- all 13 supplied categories map to the correct `64px` and `256px` assets;
- unknown names use `pantry-sauce-64.png`;
- specific matching precedence (`eggplant` → vegetables, `milkshake` → beverages, frozen vegetables → vegetables);
- plural and case normalization;
- size classes and decorative accessibility attributes.

Component or integration tests verify Grocery, Pantry, and Home render an SVG/image icon rather than an initial. Existing icon tests are migrated to the new component.

Run:

```text
pnpm --dir frontend test --run
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
pnpm --dir frontend exec playwright test
```

Manually verify the running Vite app at `http://127.0.0.1:5173` on desktop and `390×844`, including Grocery, Pantry, Home, keyboard navigation, and HMR after changing a component or asset mapping.

## Non-Goals

- No backend category field or API change.
- No admin editor for icon categories.
- No new image-generation pipeline.
- No additional icon artwork beyond the supplied folder in this iteration.
