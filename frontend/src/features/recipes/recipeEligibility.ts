type RecipeLifecycle = {
  status?: string | null;
  nutritionState?: string | null;
};

/** Planning and cooking are recipe actions; only stale nutrition needs correction first. */
export function isRecipePlannable(recipe: RecipeLifecycle): boolean {
  return recipe.status !== "archived" && recipe.nutritionState !== "stale";
}

/** Nutrition-led suggestions still require nutrition evidence they can compare honestly. */
export function isRecipeReadyForNutritionGuidance(recipe: RecipeLifecycle): boolean {
  return recipe.status !== "archived" && !["pending", "failed", "stale"].includes(recipe.nutritionState ?? "");
}
