import { type FormEvent, useState } from "react";

import { Button, DecimalInput, Field, PollingStatusBadge } from "../../components";
import type { Job, NutritionCorrectionWrite, ResolvedNutrition } from "./types";

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

export function NutritionPanel({
  nutrition,
  nutritionState,
  job,
  servingsScale = 1,
  onCorrect,
  onResetCorrection,
  onRecalculate,
}: {
  nutrition: ResolvedNutrition | null | undefined;
  nutritionState: string;
  job?: Job | null;
  servingsScale?: number;
  onCorrect: (value: NutritionCorrectionWrite) => Promise<void>;
  onResetCorrection: (correctionId: string) => Promise<void>;
  onRecalculate: (resetCorrections?: boolean) => Promise<void>;
}) {
  const [field, setField] = useState<NutritionCorrectionWrite["field"]>("protein_g");
  const [decimalValue, setDecimalValue] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const displayedNutritionState = ["stale", "pending", "failed"].includes(nutritionState)
    ? nutritionState
    : nutrition?.status === "manual" ? "manual" : nutritionState;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!/^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/.test(decimalValue)) {
      setError("Use a non-negative decimal with up to six decimal places.");
      return;
    }
    setError("");
    await onCorrect({ field, decimalValue, reason: reason || null });
    setDecimalValue("");
    setReason("");
  }

  return (
    <section className="nutrition-panel" aria-labelledby="nutrition-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Resolved nutrition</p>
          <h2 id="nutrition-heading">Nutrition and evidence</h2>
        </div>
        <span className={`nutrition-state nutrition-state--${displayedNutritionState}`}>{displayedNutritionState.replace("_", " ")}</span>
      </div>

      <p className="advisory">Estimated nutrition is a planning aid, not medical advice. Verify values when clinical precision matters.</p>

      <details className="nutrition-state-guide">
        <summary>What the nutrition status means</summary>
        <dl>
          <div><dt>Estimated</dt><dd>Calculated from matched ingredients and recorded assumptions.</dd></div>
          <div><dt>Partial</dt><dd>Some ingredients, quantities, or reference nutrients could not be resolved.</dd></div>
          <div><dt>Source provided</dt><dd>Published by the recipe source rather than calculated ingredient by ingredient.</dd></div>
          <div><dt>Manual</dt><dd>Entered or corrected by you; provenance and prior values remain recorded.</dd></div>
          <div><dt>Stale</dt><dd>The recipe changed after calculation; recalculate before relying on it.</dd></div>
          <div><dt>Pending or failed</dt><dd>Calculation is in progress or needs the recovery action shown below.</dd></div>
        </dl>
        <p className="muted">Coverage is the percentage of quantified ingredients contributing evidence. Lower coverage means more of the recipe is unresolved; unavailable values are not treated as zero.</p>
      </details>

      {job ? (
        <div className="job-panel" aria-label="Nutrition processing status">
          <div className="section-heading">
            <PollingStatusBadge status={job.status} />
            <span className="data-value">Attempt {job.attempt} of {job.maxAttempts}</span>
          </div>
          {job.progressTotal ? <progress value={job.progressCurrent ?? 0} max={job.progressTotal}>Processing</progress> : null}
          {job.nextRetryAt ? <p>Next retry: <time dateTime={job.nextRetryAt}>{new Date(job.nextRetryAt).toLocaleString()}</time></p> : null}
          <p>Deadline: <time dateTime={job.terminalDeadlineAt}>{new Date(job.terminalDeadlineAt).toLocaleString()}</time></p>
          {job.failureMessage ? <p className="error-text">{job.failureMessage}</p> : null}
          {job.status === "superseded" ? <p>This result was superseded by newer recipe inputs. Reloading the current recipe state.</p> : null}
          {!TERMINAL.has(job.status) ? <p className="muted">Processing continues safely if you leave or reload this page.</p> : null}
        </div>
      ) : null}

      {nutritionState === "stale" ? (
        <div className="notice" role="status">
          <p>Nutrition is stale because the recipe yield or ingredients changed.</p>
          <Button onClick={() => void onRecalculate()}>Recalculate nutrition</Button>
        </div>
      ) : null}
      {nutritionState === "pending" ? <p className="notice" role="status">Nutrition is pending. You can leave this page while processing continues.</p> : null}
      {nutritionState === "failed" && !job ? (
        <div className="notice notice--error" role="alert">
          <p>Nutrition processing failed. Edit the recipe, retry, or enter a manual correction.</p>
          <Button onClick={() => void onRecalculate()}>Retry nutrition</Button>
        </div>
      ) : null}

      {nutrition ? (
        <>
          <dl className="macro-grid">
            <div className="macro macro--calories"><dt>Calories</dt><dd>{nutrition.caloriesKcal ?? "—"}<span> kcal</span></dd></div>
            <div className="macro macro--protein"><dt>Protein</dt><dd>{nutrition.proteinG ?? "—"}<span> g</span></dd></div>
            <div className="macro macro--carbs"><dt>Carbohydrate</dt><dd>{nutrition.carbohydrateG ?? "—"}<span> g</span></dd></div>
            <div className="macro macro--fat"><dt>Fat</dt><dd>{nutrition.fatG ?? "—"}<span> g</span></dd></div>
          </dl>
          <p className="data-value">Basis: {nutrition.basisServings} servings · Coverage: {Math.round(Number(nutrition.coverageRatio) * 100)}%</p>
          {servingsScale !== 1 && (
            <p className="muted">
              Scaled to {Number(servingsScale).toFixed(1).replace(/\.0$/, "")} servings: {nutrition.caloriesKcal != null ? `${Math.round(Number(nutrition.caloriesKcal) * servingsScale).toLocaleString()} kcal` : "— kcal"}, {nutrition.proteinG != null ? `${(Number(nutrition.proteinG) * servingsScale).toFixed(1)}g P` : "— P"}, {nutrition.carbohydrateG != null ? `${(Number(nutrition.carbohydrateG) * servingsScale).toFixed(1)}g C` : "— C"}, {nutrition.fatG != null ? `${(Number(nutrition.fatG) * servingsScale).toFixed(1)}g F` : "— F"}
            </p>
          )}

          <section className="micronutrient-panel" aria-labelledby="micronutrient-heading">
            <div><h3 id="micronutrient-heading">Micronutrients</h3><p className="muted">Missing reference values stay unavailable; they are never displayed as zero.</p></div>
            <dl className="micronutrient-grid">
              {MICRONUTRIENTS.map(([key, label]) => {
                const nutrient = nutrition.micronutrients?.[key];
                return <div className="micronutrient" key={key}><dt>{label}</dt><dd><span className="data-value">{nutrient?.value == null ? "Unavailable" : `${nutrient.value} ${nutrient.unit}`}{nutrient?.explicitZero ? " · source-reported zero" : ""}</span><small>{nutrient ? `${Math.round(Number(nutrient.coverageRatio) * 100)}% coverage · ${nutrient.source} · USDA ${nutrient.usdaNutrientId} · ${nutrient.mappingVersion}` : "No micronutrient evidence returned"}</small></dd></div>;
              })}
            </dl>
          </section>

          <div className="evidence-grid">
            <section><h3>Provenance</h3>{nutrition.provenance.length ? <ul>{nutrition.provenance.map((item, index) => <li key={`${item.kind}-${item.label}-${index}`}><strong>{item.label}</strong>{item.version ? ` · ${item.version}` : ""}{item.sourceUrl ? <> · <a href={item.sourceUrl} rel="noreferrer">source</a></> : null}</li>)}</ul> : <p className="muted">No external provenance recorded.</p>}</section>
            <section><h3>Assumptions</h3>{nutrition.assumptions?.length ? <ul>{nutrition.assumptions.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">No conversion assumptions recorded.</p>}</section>
          </div>

          <section className="corrections"><h3>Active corrections</h3>
            {nutrition.corrections.length ? <ul>{nutrition.corrections.filter((item) => item.active).map((item) => <li key={item.id}><span><strong>{item.field}</strong>: {item.decimalValue ?? item.textValue ?? item.referenceIdValue}{item.reason ? ` · ${item.reason}` : ""}</span><Button className="button--text" aria-label={`Reset ${item.field} correction`} onClick={() => void onResetCorrection(item.id)}>Reset</Button></li>)}</ul> : <p className="muted">No active corrections.</p>}
          </section>
        </>
      ) : null}

      <form className="correction-form" onSubmit={(event) => void submit(event)}>
        <h3>Correct a nutrition value</h3>
        <Field label="Nutrition field"><select className="input" value={field} onChange={(event) => setField(event.target.value as NutritionCorrectionWrite["field"])}><option value="calories_kcal">Calories</option><option value="protein_g">Protein</option><option value="carbohydrate_g">Carbohydrate</option><option value="fat_g">Fat</option><option value="yield_quantity">Yield quantity</option></select></Field>
        <Field label="Corrected decimal value" error={error}><DecimalInput value={decimalValue} onValueChange={setDecimalValue} onInput={(event) => setDecimalValue(event.currentTarget.value)} /></Field>
        <Field label="Correction reason"><input className="input" value={reason} onChange={(event) => setReason(event.target.value)} /></Field>
        <Button type="submit">Apply correction</Button>
      </form>
    </section>
  );
}
