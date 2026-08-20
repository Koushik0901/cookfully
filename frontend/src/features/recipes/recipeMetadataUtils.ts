import type { Recipe } from "./types";

export type RecipeSummary = Pick<Recipe, "title" | "prepMinutes" | "cookMinutes"> & {
  nutrition?: Pick<NonNullable<Recipe["nutrition"]>, "caloriesKcal" | "proteinG" | "fatG"> | null;
};

function display(value: string | null | undefined, digits: number, suffix: string) {
  if (value == null) return `— ${suffix}`;
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(Number(value))} ${suffix}`;
}

export function recipeTimeMinutes(recipe: Pick<Recipe, "prepMinutes" | "cookMinutes">) {
  const prep = recipe.prepMinutes ?? 0;
  const cook = recipe.cookMinutes ?? 0;
  return prep + cook > 0 ? prep + cook : null;
}

export function recipeTimeLabel(recipe: Pick<Recipe, "prepMinutes" | "cookMinutes">) {
  const minutes = recipeTimeMinutes(recipe);
  if (minutes == null) return "Time not set";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} hr ${remainder} min` : `${hours} hr`;
}

export function recipeNutritionLabel(recipe: RecipeSummary) {
  return [
    recipeTimeLabel(recipe),
    display(recipe.nutrition?.caloriesKcal, 0, "kcal"),
    display(recipe.nutrition?.proteinG, 1, "g protein"),
    display(recipe.nutrition?.fatG, 1, "g fat"),
  ].join(" · ");
}
