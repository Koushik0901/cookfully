import type { RecipeSummary } from "./recipeMetadataUtils";
import { recipeTimeLabel } from "./recipeMetadataUtils";

export function RecipeMetadata({ recipe, compact = false }: { recipe: RecipeSummary; compact?: boolean }) {
  const calories = recipe.nutrition?.caloriesKcal == null ? null : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(Number(recipe.nutrition.caloriesKcal))} kcal`;
  const protein = recipe.nutrition?.proteinG == null ? "— g" : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(Number(recipe.nutrition.proteinG))} g`;
  const fat = recipe.nutrition?.fatG == null ? "— g" : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(Number(recipe.nutrition.fatG))} g`;
  const hasNutrition = calories !== null || recipe.nutrition?.proteinG != null || recipe.nutrition?.fatG != null;

  return (
    <div className={`recipe-meta${compact ? " recipe-meta--compact" : ""}`} aria-label={`${recipe.title} cooking time and nutrition`}>
      <span>{recipeTimeLabel(recipe)}</span>
      {calories ? <span>{calories}</span> : null}
      {recipe.nutrition?.proteinG != null ? <span><span className="recipe-meta__value">{protein}</span> protein</span> : null}
      {recipe.nutrition?.fatG != null ? <span><span className="recipe-meta__value">{fat}</span> fat</span> : null}
      {!hasNutrition ? <span className="recipe-meta__pending">Nutrition pending</span> : null}
    </div>
  );
}
