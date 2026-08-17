import { CheckCircle2, LoaderCircle, TriangleAlert } from "lucide-react";

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

export function RecipeProcessingBanner({ job, nutritionState }: { job?: Job | null; nutritionState: string }) {
  if (!job) return null;
  const retrying = job.status === "retry_wait";
  const failed = job.status === "failed";
  const complete = job.status === "succeeded" && nutritionState !== "pending";
  const stage = STAGES[job.kind] ?? "Updating your recipe";
  const message = failed
    ? job.failureMessage ?? "Cookfully could not finish this step."
    : retrying
      ? "Cookfully will try this step again automatically."
      : complete
        ? "Your recipe is ready to use."
        : "You can keep using the recipe while Cookfully works.";
  const progress = progressLabel(job);

  return (
    <section className={`recipe-processing-banner recipe-processing-banner--${failed ? "failed" : retrying ? "retrying" : complete ? "complete" : "active"}`} role={failed ? "alert" : "status"} aria-live="polite">
      {failed ? <TriangleAlert aria-hidden="true" /> : complete ? <CheckCircle2 aria-hidden="true" /> : <LoaderCircle className="recipe-processing-banner__spinner" aria-hidden="true" />}
      <div>
        <p className="eyebrow">Recipe update</p>
        <strong>{failed ? "Nutrition needs attention" : complete ? "Nutrition is ready" : stage}</strong>
        <p>{message}</p>
        {progress ? <div className="recipe-processing-banner__progress"><progress aria-label={progress} value={job.progressCurrent ?? undefined} max={job.progressTotal ?? undefined}>{progress}</progress><small>{progress}</small></div> : null}
        {job.nextRetryAt ? <small>Next try: {new Date(job.nextRetryAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</small> : null}
      </div>
    </section>
  );
}
