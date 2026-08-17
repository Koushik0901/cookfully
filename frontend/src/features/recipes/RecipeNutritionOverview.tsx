import { Link } from "react-router-dom";

import type { ResolvedNutrition } from "./types";

const display = (value: string | null | undefined, digits: number) =>
  value == null
    ? "—"
    : new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(Number(value));

function estimateLabel(nutrition: ResolvedNutrition | null | undefined, state: string): string {
  if (state === "pending") return "Estimation is starting";
  if (state === "stale") return "Estimate needs refreshing";
  if (state === "failed") return "Estimate unavailable";
  if (nutrition?.status === "manual") return "Manual values";
  if (nutrition?.status === "source_provided") return "From the recipe source";
  const coverage = Number(nutrition?.coverageRatio ?? 0);
  return coverage >= 0.9 ? "Complete estimate" : coverage >= 0.4 ? "Partial estimate" : "Limited estimate";
}

export function RecipeNutritionOverview({
  nutrition,
  nutritionState,
  ingredientReviewCount,
  reviewHref,
}: {
  nutrition: ResolvedNutrition | null | undefined;
  nutritionState: string;
  ingredientReviewCount: number;
  reviewHref: string;
}) {
  const coverage = nutrition ? Math.round(Number(nutrition.coverageRatio) * 100) : 0;
  const label = estimateLabel(nutrition, nutritionState);

  return (
    <section className="recipe-nutrition-overview" aria-labelledby="nutrition-overview-heading">
      <div className="recipe-nutrition-overview__heading">
        <div>
          <p className="eyebrow">The useful part first</p>
          <h2 id="nutrition-overview-heading">Nutrition at a glance</h2>
          <p>Per serving · {nutrition ? `${Number(nutrition.basisServings).toLocaleString()} servings in this recipe` : "Waiting for the first estimate"}</p>
        </div>
        <span className={`nutrition-state nutrition-state--${nutritionState}`}>{label}</span>
      </div>
      <dl className="recipe-nutrition-overview__metrics" aria-label="Nutrition per serving">
        <div><dt>Calories</dt><dd>{display(nutrition?.caloriesKcal, 0)} <small>kcal</small></dd></div>
        <div><dt>Protein</dt><dd>{display(nutrition?.proteinG, 1)} <small>g</small></dd></div>
        <div><dt>Carbs</dt><dd>{display(nutrition?.carbohydrateG, 1)} <small>g</small></dd></div>
        <div><dt>Fat</dt><dd>{display(nutrition?.fatG, 1)} <small>g</small></dd></div>
      </dl>
      <div className="recipe-nutrition-overview__coverage">
        <div><span>Ingredient coverage</span><strong>{nutrition ? `${coverage}%` : "Not ready"}</strong></div>
        <progress aria-label={nutrition ? `${coverage}% ingredient coverage` : "Nutrition estimate pending"} value={nutrition ? coverage : undefined} max="100" />
        <p>{nutrition ? `${label}. Values are planning guidance, not medical advice.` : "Cookfully will show the estimate here as soon as it is ready."}</p>
      </div>
      {ingredientReviewCount ? <Link className="recipe-nutrition-overview__review" to={reviewHref}>Review {ingredientReviewCount} ingredient match{ingredientReviewCount === 1 ? "" : "es"} to improve this estimate</Link> : null}
    </section>
  );
}
