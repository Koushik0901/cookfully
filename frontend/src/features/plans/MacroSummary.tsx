import type { PeriodTotal, UserGoal } from "./types";

const MACROS = [
  ["caloriesKcal", "Calories", "kcal", "calories"],
  ["proteinG", "Protein", "g", "protein"],
  ["carbohydrateG", "Carbohydrate", "g", "carbs"],
  ["fatG", "Fat", "g", "fat"],
] as const;

export function MacroSummary({ total, target, label }: { total?: PeriodTotal; target: UserGoal; label: string }) {
  return (
    <section className="macro-summary" aria-label={label}>
      <div className="section-heading"><h2>{label}</h2><span className="reliability-badge">{total ? `${total.status.replace("_", " ")} · ${Math.round(Number(total.coverageRatio) * 100)}% coverage` : "No entries · 0% coverage"}</span></div>
      <div className="budget-grid">
        {MACROS.map(([field, name, unit, className]) => {
          const consumed = total?.[field] ?? "0";
          const targetValue = target[field];
          const percentage = Math.min(100, Math.max(0, Number(consumed) / Number(targetValue || 1) * 100));
          const difference = total?.targetDifference?.[field];
          return <div className={`budget budget--${className}`} key={field}><div className="budget__label"><strong>{name}</strong><span className="data-value">{consumed} / {targetValue} {unit}</span></div><div role="progressbar" aria-label={`${name} budget used`} aria-valuemin={0} aria-valuemax={Number(targetValue)} aria-valuenow={Number(consumed)} className="budget__track"><span style={{ width: `${percentage}%` }} /></div><small className="data-value">{difference != null ? `${difference} ${unit} remaining` : "No difference available"}</small></div>;
        })}
      </div>
    </section>
  );
}

