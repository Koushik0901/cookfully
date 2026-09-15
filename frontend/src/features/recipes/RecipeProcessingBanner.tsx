import { ArrowRight, Check, CircleAlert, LoaderCircle } from "lucide-react";
import { Link } from "react-router-dom";

import type { Job } from "./types";

const STAGES: Record<string, string> = {
  recipe_import: "Reading the recipe",
  ingredient_parse: "Understanding ingredients",
  nutrition_match: "Matching nutrition",
  nutrition_rollup: "Finishing your estimate",
};

function progressLabel(job: Job): string | null {
  if (job.progressCurrent == null || job.progressTotal == null) return null;
  const noun = job.progressTotal === 1 ? "ingredient" : "ingredients";
  return `${job.progressCurrent} of ${job.progressTotal} ${noun}`;
}

export function RecipeProcessingBanner({ job, nutritionState, reviewHref }: { job?: Job | null; nutritionState: string; reviewHref?: string }) {
  if (!job) return null;
  const retrying = job.status === "retry_wait";
  const failed = job.status === "failed";
  const complete = job.status === "succeeded" && nutritionState !== "pending";
  const stage = STAGES[job.kind] ?? "Updating your recipe";
  const message = failed
    ? "Add values in the editor or try again when you’re ready."
    : retrying
      ? "Cookfully will try again automatically."
      : complete
        ? "Ready to use."
        : "Working in the background.";
  const progress = progressLabel(job);
  const state = failed ? "failed" : retrying ? "retrying" : complete ? "complete" : "active";

  return (
    <section className={`recipe-processing-status recipe-processing-status--${state}`} role="status" aria-live="polite">
      <span className="recipe-processing-status__mark" aria-hidden="true">
        {failed ? <CircleAlert /> : complete ? <Check /> : <LoaderCircle className="recipe-processing-status__spinner" />}
      </span>
      <div className="recipe-processing-status__copy">
        <strong>{failed ? "Nutrition not available" : complete ? "Nutrition ready" : retrying ? "Nutrition retrying" : stage}</strong>
        <span>{message}</span>
        {progress ? <div className="recipe-processing-status__progress"><progress aria-label={progress} value={job.progressCurrent ?? undefined} max={job.progressTotal ?? undefined} /><small aria-hidden="true">{progress}</small></div> : null}
      </div>
      {failed && reviewHref ? <Link className="recipe-processing-status__action" to={reviewHref}>Review nutrition <ArrowRight aria-hidden="true" /></Link> : null}
    </section>
  );
}
