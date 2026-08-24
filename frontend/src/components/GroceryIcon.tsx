/* eslint-disable react-refresh/only-export-components */
/**
 * @deprecated Use `FoodCategoryIcon` from "./FoodCategoryIcon" instead.
 *
 * Temporary shim for incremental migration (Task 1 → Task 2). Task 1 introduced
 * `FoodCategoryIcon` as the single source of truth and deleted the old SVG-based
 * `GroceryIcon` implementation. To keep `typecheck`/`build` (and import resolution
 * for existing consumers/tests) green before Task 2 migrates all call sites to
 * `FoodCategoryIcon`, this file re-exports the new icon under the legacy name.
 *
 * - No old SVG imports are restored (the 9 monochrome SVGs stay deleted).
 * - Consumers should migrate to `import { FoodCategoryIcon } from "./FoodCategoryIcon"`
 *   (or the appropriate relative path) in Task 2.
 * - This shim will be deleted in Task 2 once `GroceryListPage`, `PantryPage`,
 *   `HomePage`, and `GroceryIcon.test.tsx` have been migrated/removed.
 * - `Category` is re-exported from `FoodCategoryIcon` (13 illustrated categories).
 */

export { FoodCategoryIcon as GroceryIcon, categoryFor } from "./FoodCategoryIcon";
export type Category = import("./FoodCategoryIcon").Category;
