import type { PeriodTotal, UserGoal } from "./types";

const NUTRIENTS = [
  ["caloriesKcal", "Calories", "kcal", "calories"],
  ["proteinG", "Protein", "g", "protein"],
  ["carbohydrateG", "Carbohydrate", "g", "carbs"],
  ["fatG", "Fat", "g", "fat"],
] as const;

function formatNumber(value: number, unit: string) {
  return new Intl.NumberFormat("en-CA", { maximumFractionDigits: unit === "kcal" ? 0 : 1 }).format(value);
}

function balanceLabel(percentage: number) {
  if (percentage < 80) return `${Math.round(percentage)}% of guide`;
  if (percentage <= 110) return "Around your guide";
  return `${Math.round(percentage - 100)}% above guide`;
}

export function NutritionPulse({ total, target, plannedDays }: { total?: PeriodTotal; target: UserGoal; plannedDays: number }) {
  if (!total || !plannedDays) {
    return (
      <section className="nutrition-pulse nutrition-pulse--empty" aria-label="Weekly nutrition guidance">
        <div><p className="eyebrow">Nutrition guidance</p><h2>Balance appears as the week takes shape</h2></div>
        <p>Add a meal and Cookfully will compare the average planned day with your guide.</p>
      </section>
    );
  }

  const coverage = Math.round(Number(total.coverageRatio) * 100);
  return (
    <section className="nutrition-pulse" aria-label="Weekly nutrition guidance">
      <div className="nutrition-pulse__heading">
        <div><p className="eyebrow">Nutrition guidance</p><h2>A typical planned day</h2></div>
        <p>Daily average across {plannedDays} {plannedDays === 1 ? "day" : "days"} with meals—not a score for unfinished days.</p>
      </div>
      <div className="nutrition-pulse__grid">
        {NUTRIENTS.map(([field, label, unit, className]) => {
          const average = Number(total[field]) / plannedDays;
          const guide = Number(target[field]);
          const percentage = guide ? average / guide * 100 : 0;
          return (
            <div className={`nutrition-pulse__item nutrition-pulse__item--${className}`} key={field}>
              <div><strong>{label}</strong><span>{balanceLabel(percentage)}</span></div>
              <div className="nutrition-pulse__track" role="progressbar" aria-label={`${label} average across planned days`} aria-valuemin={0} aria-valuemax={guide} aria-valuenow={Math.min(guide, average)} aria-valuetext={`${formatNumber(average, unit)} ${unit} average; guide ${formatNumber(guide, unit)} ${unit}`}><span style={{ width: `${Math.min(100, Math.max(0, percentage))}%` }} /></div>
              <small><span className="data-value">{formatNumber(average, unit)} {unit}</span> average</small>
            </div>
          );
        })}
      </div>
      <details className="nutrition-pulse__evidence">
        <summary>{coverage >= 90 ? "Nutrition estimates are well supported" : "Some nutrition estimates are incomplete"}</summary>
        <p>{coverage}% of the planned nutrition values are supported by available source data. Open a recipe for ingredient-level evidence.</p>
      </details>
    </section>
  );
}
