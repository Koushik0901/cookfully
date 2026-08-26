import type { RecipeSummary } from "./recipeMetadataUtils";
import { recipeTimeLabel, recipeTimeMinutes } from "./recipeMetadataUtils";
import { Clock3 } from "lucide-react";

export function RecipeMetadata({ recipe, compact = false }: { recipe: RecipeSummary; compact?: boolean }) {
  const calories = recipe.nutrition?.caloriesKcal == null ? null : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(Number(recipe.nutrition.caloriesKcal))} kcal`;
  const protein = recipe.nutrition?.proteinG == null ? "— g" : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(Number(recipe.nutrition.proteinG))} g`;
  const fat = recipe.nutrition?.fatG == null ? "— g" : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(Number(recipe.nutrition.fatG))} g`;
  const hasNutrition = calories !== null || recipe.nutrition?.proteinG != null || recipe.nutrition?.fatG != null;
  const time = recipeTimeMinutes(recipe) == null ? "—" : recipeTimeLabel(recipe);

  return (
    <div className={`recipe-meta${compact ? " recipe-meta--compact" : ""}`} aria-label={`${recipe.title} cooking time and nutrition`}>
      <span className="recipe-meta__item recipe-meta__item--time" aria-label={recipeTimeMinutes(recipe) == null ? "Cooking time not set" : `${time} cooking time`} title={recipeTimeMinutes(recipe) == null ? "Cooking time not set" : `${time} cooking time`}>
        <Clock3 aria-hidden="true" />
        <span>{time}</span>
      </span>
      {calories ? <span className="recipe-meta__item recipe-meta__item--calories"><strong className="recipe-meta__value">{calories}</strong></span> : null}
      {recipe.nutrition?.proteinG != null ? <span className="recipe-meta__item recipe-meta__item--protein"><i className="recipe-meta__dot" aria-hidden="true" /><strong className="recipe-meta__value">{protein}</strong> protein</span> : null}
      {recipe.nutrition?.fatG != null ? <span className="recipe-meta__item recipe-meta__item--fat"><i className="recipe-meta__dot" aria-hidden="true" /><strong className="recipe-meta__value">{fat}</strong> fat</span> : null}
      {!hasNutrition ? <span className="recipe-meta__pending">Nutrition pending</span> : null}
    </div>
  );
}
