type RecipeLifecycle = {
  status?: string | null;
  nutritionState?: string | null;
};

/** One shared definition keeps Home, Plan, and Suggestions honest with each other. */
export function isRecipeReadyToPlan(recipe: RecipeLifecycle): boolean {
  return recipe.status !== "archived" && !["pending", "failed", "stale"].includes(recipe.nutritionState ?? "");
}
