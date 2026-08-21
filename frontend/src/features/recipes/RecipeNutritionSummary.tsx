import { Link } from "react-router-dom";

import { nutritionPresentation } from "../../components/cookfully/nutritionState";
import type { Job, ResolvedNutrition } from "./types";

const display = (value: string | null | undefined, digits: number) =>
  value == null
    ? "—"
    : new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(Number(value));

export function RecipeNutritionSummary({
  nutrition,
  nutritionState,
  job,
  editTo,
}: {
  nutrition: ResolvedNutrition | null | undefined;
  nutritionState: string;
  job?: Job | null;
  editTo: string;
}) {
  const statePresentation = nutritionPresentation(nutritionState, nutrition?.status);
  const failed = job?.status === "failed";
  const processing = job && ["pending", "running"].includes(job.status);
  const retrying = job?.status === "retry_wait";
  const coverageRatio = nutrition?.coverageRatio != null ? Number(nutrition.coverageRatio) : null;
  const coverageLabel = coverageRatio == null ? null
    : coverageRatio >= 0.9 ? "Coverage: complete"
    : coverageRatio >= 0.7 ? "Coverage: good"
    : coverageRatio >= 0.4 ? "Coverage: partial"
    : "Coverage: limited";

  return (
    <section className="recipe-nutrition-summary" aria-labelledby="recipe-nutrition-summary-heading">
      <div className="recipe-nutrition-summary__heading">
        <div><p className="eyebrow">Per serving</p><h2 id="recipe-nutrition-summary-heading">Nutrition</h2></div>
         <span className={`nutrition-state nutrition-state--${statePresentation.key}`} title={statePresentation.description}>{statePresentation.label}</span>
      </div>
      <dl className="recipe-nutrition-summary__metrics">
        <div className="recipe-nutrition-summary__metric recipe-nutrition-summary__metric--calories"><dt>Calories</dt><dd>{display(nutrition?.caloriesKcal, 0)} <small>kcal</small></dd></div>
        <div className="recipe-nutrition-summary__metric recipe-nutrition-summary__metric--protein"><dt>Protein</dt><dd>{display(nutrition?.proteinG, 1)} <small>g</small></dd></div>
        <div className="recipe-nutrition-summary__metric recipe-nutrition-summary__metric--carbs"><dt>Carbs</dt><dd>{display(nutrition?.carbohydrateG, 1)} <small>g</small></dd></div>
        <div className="recipe-nutrition-summary__metric recipe-nutrition-summary__metric--fat"><dt>Fat</dt><dd>{display(nutrition?.fatG, 1)} <small>g</small></dd></div>
      </dl>
      {failed ? <p className="recipe-nutrition-summary__message" role="alert">{job.failureMessage ?? "Nutrition could not be calculated."}</p> : null}
      {processing ? <p className="recipe-nutrition-summary__message" role="status">Calculating nutrition… You can keep using the recipe.</p> : null}
      {retrying ? <p className="recipe-nutrition-summary__message" role="status">Nutrition will retry automatically.</p> : null}
      {!failed && nutrition && coverageLabel ? <p className="recipe-nutrition-summary__message">{coverageLabel}</p> : null}
      <Link className="text-link" to={`${editTo}#nutrition`}>Edit nutrition</Link>
    </section>
  );
}
