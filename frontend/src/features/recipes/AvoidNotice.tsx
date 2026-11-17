import { TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { formatCookingText } from "./formatCooking";
import type { RecipeDetail } from "./types";

type Warning = NonNullable<RecipeDetail["avoidWarnings"]>[number];

/** Ingredients that name (or may contain) something on the owner's avoid list. */
export function AvoidNotice({ recipe }: { recipe: RecipeDetail }) {
  const warnings = recipe.avoidWarnings ?? [];
  if (!warnings.length) return null;
  const lines = new Map(recipe.ingredients.map((item) => [item.id, item.originalText]));
  const named = warnings.filter((warning) => warning.source === "ingredient");
  const suspected = warnings.filter((warning) => warning.source !== "ingredient");
  const describe = (warning: Warning) => {
    const line = lines.get(warning.ingredientId);
    const probability = warning.probability != null ? ` (${Math.round(Number(warning.probability) * 100)}%)` : "";
    return `${warning.item}: ${line ? formatCookingText(line) : "an ingredient"}${probability}`;
  };
  return (
    <section className="avoid-notice" aria-labelledby="avoid-notice-title">
      <TriangleAlert aria-hidden="true" />
      <div>
        <strong id="avoid-notice-title">On your avoid list</strong>
        <ul>
          {named.map((warning) => <li key={`${warning.ingredientId}-${warning.item}`}>{describe(warning)}</li>)}
          {suspected.map((warning) => <li key={`${warning.ingredientId}-${warning.item}-model`}>May contain {describe(warning)}, suggested by a decision model</li>)}
        </ul>
        <small>Based on the ingredient text. Check labels yourself. <Link to="/app/goals">Edit avoid list</Link></small>
      </div>
    </section>
  );
}
