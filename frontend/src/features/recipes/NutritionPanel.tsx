import { Button, PollingStatusBadge } from "../../components";
import type { Job, ResolvedNutrition } from "./types";

const MICRONUTRIENTS = [
  ["dietaryFiberG", "Dietary fiber"],
  ["sodiumMg", "Sodium"],
  ["potassiumMg", "Potassium"],
  ["calciumMg", "Calcium"],
  ["ironMg", "Iron"],
  ["magnesiumMg", "Magnesium"],
  ["vitaminCMg", "Vitamin C"],
  ["vitaminDUg", "Vitamin D"],
  ["vitaminB12Ug", "Vitamin B12"],
] as const;

const TERMINAL = new Set(["succeeded", "failed", "cancelled", "superseded"]);
const CORRECTION_LABELS: Record<string, { label: string; unit: string }> = {
  calories_kcal: { label: "Calories", unit: "kcal" },
  protein_g: { label: "Protein", unit: "g" },
  carbohydrate_g: { label: "Carbohydrate", unit: "g" },
  fat_g: { label: "Fat", unit: "g" },
  dietary_fiber_g: { label: "Dietary fiber", unit: "g" },
  sodium_mg: { label: "Sodium", unit: "mg" },
  potassium_mg: { label: "Potassium", unit: "mg" },
  calcium_mg: { label: "Calcium", unit: "mg" },
  iron_mg: { label: "Iron", unit: "mg" },
  magnesium_mg: { label: "Magnesium", unit: "mg" },
  vitamin_c_mg: { label: "Vitamin C", unit: "mg" },
  vitamin_d_ug: { label: "Vitamin D", unit: "µg" },
  vitamin_b12_ug: { label: "Vitamin B12", unit: "µg" },
  yield_quantity: { label: "Yield quantity", unit: "" },
};

export function NutritionPanel({
  nutrition,
  nutritionState,
  job,
  onRecalculate,
}: {
  nutrition: ResolvedNutrition | null | undefined;
  nutritionState: string;
  job?: Job | null;
  onRecalculate: () => Promise<void>;
}) {
  const availableMicronutrients = nutrition
    ? MICRONUTRIENTS.flatMap(([key, label]) => {
      const nutrient = nutrition.micronutrients?.[key];
      return nutrient?.value == null ? [] : [{ key, label, nutrient }];
    })
    : [];
  const unavailableMicronutrientCount = MICRONUTRIENTS.length - availableMicronutrients.length;

  return (
    <section className="nutrition-evidence-panel" aria-labelledby="nutrition-evidence-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">How Cookfully got the numbers</p>
          <h2 id="nutrition-evidence-heading">Nutrition details</h2>
        </div>
        <Button variant="secondary" onClick={() => void onRecalculate()}>Recalculate nutrition</Button>
      </div>

      <p className="nutrition-caution">Estimated nutrition is a planning aid, not medical advice. Verify values when clinical precision matters.</p>
      {nutrition ? <p className="muted">Basis: {Number(nutrition.basisServings).toLocaleString()} servings · {Math.round(Number(nutrition.coverageRatio) * 100)}% ingredient coverage</p> : null}

      {job ? (
        <div className="job-panel" aria-label="Nutrition processing status">
          <div className="section-heading">
            <PollingStatusBadge status={job.status} />
            <span className="data-value">Attempt {job.attempt} of {job.maxAttempts}</span>
          </div>
          {job.progressTotal ? <progress value={job.progressCurrent ?? 0} max={job.progressTotal}>Processing</progress> : null}
          {job.failureMessage ? <p className="error-text">{job.failureMessage}</p> : null}
          {job.nextRetryAt ? <p><strong>Next retry:</strong> {new Date(job.nextRetryAt).toLocaleString()}</p> : null}
          {job.terminalDeadlineAt ? <p><strong>Processing deadline:</strong> {new Date(job.terminalDeadlineAt).toLocaleString()}</p> : null}
          {job.status === "superseded" ? <p>This result was replaced by newer recipe inputs.</p> : null}
          {!TERMINAL.has(job.status) ? <p className="muted">Processing continues if you leave this page.</p> : null}
        </div>
      ) : null}

      {nutritionState === "stale" ? <p className="notice">The recipe changed after calculation. Recalculate before relying on these values.</p> : null}
      {nutritionState === "pending" ? <p className="notice">Nutrition is being calculated in the background.</p> : null}

      <details className="nutrition-state-guide">
        <summary>What does this status mean?</summary>
        <dl>
          <div><dt>Estimated</dt><dd>Calculated from matched ingredients and recorded assumptions.</dd></div>
          <div><dt>Partial</dt><dd>Some ingredients, quantities, or reference nutrients could not be resolved.</dd></div>
          <div><dt>Source provided</dt><dd>Published by the recipe source rather than calculated ingredient by ingredient.</dd></div>
          <div><dt>Manual</dt><dd>Entered by you; the automatic values remain in the history.</dd></div>
          <div><dt>Coverage</dt><dd>The percentage of quantified ingredients supported by nutrition evidence.</dd></div>
        </dl>
      </details>

      {nutrition ? (
        <>
          <section className="micronutrient-panel" aria-labelledby="micronutrient-heading">
            <div>
              <h3 id="micronutrient-heading">Micronutrients</h3>
              <p className="muted">
                {unavailableMicronutrientCount
                  ? `${unavailableMicronutrientCount} values are unavailable and are omitted rather than shown as zero.`
                  : "Every tracked micronutrient has source evidence."}
              </p>
            </div>
            {availableMicronutrients.length ? (
              <dl className="micronutrient-grid">
                {availableMicronutrients.map(({ key, label, nutrient }) => (
                  <div className="micronutrient" key={key}>
                    <dt>{label}</dt>
                    <dd>
                      <strong className="data-value">{nutrient.value} {nutrient.unit}</strong>
                      <small>{Math.round(Number(nutrient.coverageRatio) * 100)}% coverage · {nutrient.source}</small>
                    </dd>
                  </div>
                ))}
              </dl>
            ) : <p className="muted">No micronutrient evidence is available for this recipe yet.</p>}
          </section>

          <div className="evidence-grid">
            <section><h3>Sources</h3>{nutrition.provenance.length ? <ul>{nutrition.provenance.map((item, index) => <li key={`${item.kind}-${item.label}-${index}`}><strong>{item.label}</strong>{item.version ? ` · ${item.version}` : ""}{item.sourceUrl ? <> · <a href={item.sourceUrl} rel="noreferrer">source</a></> : null}</li>)}</ul> : <p className="muted">No external sources recorded.</p>}</section>
            <section><h3>Assumptions</h3>{nutrition.assumptions?.length ? <ul>{nutrition.assumptions.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">No conversion assumptions recorded.</p>}</section>
          </div>

          <section className="corrections"><h3>Manual values</h3>
            {nutrition.corrections.filter((item) => item.active && item.ingredientId == null).length ? <ul>{nutrition.corrections.filter((item) => item.active && item.ingredientId == null).map((item) => {
              const display = CORRECTION_LABELS[item.field] ?? { label: item.field.replaceAll("_", " "), unit: "" };
              const corrected = item.decimalValue ?? item.textValue ?? item.referenceIdValue;
              return <li key={item.id}><span><strong>{display.label}</strong>: {corrected}{display.unit ? ` ${display.unit}` : ""}{item.reason ? ` · ${item.reason}` : ""}</span></li>;
            })}</ul> : <p className="muted">No manual nutrition values.</p>}
          </section>
        </>
      ) : null}
    </section>
  );
}
