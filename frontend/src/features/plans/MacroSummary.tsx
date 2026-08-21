import { SectionHeading } from "../../components";
import type { PeriodTotal, UserGoal } from "./types";
import { nutritionConfidenceLabel } from "./nutritionConfidence";

const MACROS = [
  ["caloriesKcal", "Calories", "kcal", "calories"],
  ["proteinG", "Protein", "g", "protein"],
  ["carbohydrateG", "Carbohydrate", "g", "carbs"],
  ["fatG", "Fat", "g", "fat"],
] as const;

const MICRONUTRIENTS = [
  ["dietaryFiberG", "Fiber"],
  ["sodiumMg", "Sodium"],
  ["potassiumMg", "Potassium"],
  ["calciumMg", "Calcium"],
  ["ironMg", "Iron"],
  ["magnesiumMg", "Magnesium"],
  ["vitaminCMg", "Vitamin C"],
  ["vitaminDUg", "Vitamin D"],
  ["vitaminB12Ug", "Vitamin B12"],
] as const;

function formatTargetDifference(value: string | null | undefined, unit: string) {
  if (value == null) return "No difference available";
  const unsigned = value.replace(/^[+-]/, "");
  if (/^0(?:\.0+)?$/.test(unsigned)) return "Target met";
  if (value.startsWith("-")) return `${unsigned} ${unit} remaining`;
  return `${unsigned} ${unit} over target`;
}

export function MacroSummary({ total, target, label }: { total?: PeriodTotal; target: UserGoal; label: string }) {
  return (
    <section className="macro-summary" aria-label={label}>
      <SectionHeading title={label} action={total ? <details className="nutrition-confidence"><summary>{nutritionConfidenceLabel(total.status, total.coverageRatio)}</summary><p>{total.status.replace("_", " ")} nutrition · {Math.round(Number(total.coverageRatio) * 100)}% source coverage</p></details> : <span className="nutrition-confidence__empty">No meals planned</span>} />
      <div className="budget-grid">
        {MACROS.map(([field, name, unit, className]) => {
          const consumed = total?.[field] ?? "0";
          const targetValue = target[field];
          const percentage = Math.min(100, Math.max(0, Number(consumed) / Number(targetValue || 1) * 100));
          const difference = total?.targetDifference?.[field] ?? (total ? undefined : `-${targetValue}`);
          const differenceLabel = formatTargetDifference(difference, unit);
          return <div className={`budget budget--${className}`} key={field}><strong className="budget__name">{name}</strong><span className="budget__value data-value">{consumed} / {targetValue} {unit}</span><div role="progressbar" aria-label={`${name} budget used`} aria-valuemin={0} aria-valuemax={Number(targetValue)} aria-valuenow={Math.min(Number(targetValue), Number(consumed))} aria-valuetext={`${consumed} of ${targetValue} ${unit}; ${differenceLabel}`} className="budget__track"><span style={{ width: `${percentage}%` }} /></div><small className="budget__remaining data-value">{differenceLabel}</small></div>;
        })}
      </div>
      <details className="plan-micronutrients">
        <summary>Micronutrient planning view</summary>
        <p className="advisory">Micronutrients are a planning aid, not medical advice. Unavailable source values are not zero and totals inherit the least complete entry.</p>
        <dl className="micronutrient-grid">
          {MICRONUTRIENTS.map(([field, name]) => {
            const nutrient = total?.micronutrients?.[field];
            return <div className="micronutrient" key={field}><dt>{name}</dt><dd className="data-value">{nutrient?.value == null ? "Unavailable" : `${nutrient.value} ${nutrient.unit}`}{nutrient?.explicitZero ? " · source-reported zero" : ""}</dd><small>{nutrient ? `${Math.round(Number(nutrient.coverageRatio) * 100)}% coverage · ${nutrient.source} · USDA ${nutrient.usdaNutrientId}` : "No entries"}</small></div>;
          })}
        </dl>
      </details>
    </section>
  );
}
