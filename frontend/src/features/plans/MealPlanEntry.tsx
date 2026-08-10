import { useState } from "react";

import { Button, DecimalInput, Field } from "../../components";
import type { MealPlanEntry as Entry } from "./types";
import { useMealPlanMutations } from "./useMealPlanMutations";

const SLOTS = ["breakfast", "lunch", "dinner", "snack"];

export function MealPlanEntry({ entry, weekStart }: { entry: Entry; weekStart: string }) {
  const [servings, setServings] = useState(entry.servings);
  const [mealSlot, setMealSlot] = useState(entry.mealSlot);
  const mutations = useMealPlanMutations(weekStart);
  const payload = (refreshNutrition = false) => ({ localDate: entry.localDate, mealSlot, recipeId: entry.recipeId!, servings, position: entry.position, refreshNutrition });
  const disabled = !entry.recipeId;
  return (
    <article className="plan-entry">
      <div className="plan-entry__heading"><div><h3>{entry.recipeTitle}</h3><p className="data-value">{entry.nutrition.caloriesKcal ?? "—"} kcal · {entry.nutrition.proteinG ?? "—"} g protein</p></div><span className="reliability-badge">{entry.nutrition.status.replace("_", " ")} · {Math.round(Number(entry.nutrition.coverageRatio) * 100)}% coverage</span></div>
      <div className="entry-controls"><Field label={`${entry.recipeTitle} servings`}><DecimalInput value={servings} disabled={disabled} onInput={(event) => setServings(event.currentTarget.value)} /></Field><Field label={`${entry.recipeTitle} meal slot`}><select className="input" value={mealSlot} disabled={disabled} onChange={(event) => setMealSlot(event.target.value)}>{SLOTS.map((slot) => <option key={slot} value={slot}>{slot}</option>)}</select></Field></div>
      {!entry.recipeId ? <p className="notice">Historical snapshot retained; the source recipe was deleted.</p> : null}
      {mutations.error instanceof Error ? <p className="error-text" role="alert">{mutations.conflict ? "The plan changed elsewhere. Reload before trying again." : mutations.error.message}</p> : null}
      {mutations.message ? <p className="success-text" role="status">{mutations.message}</p> : null}
      <div className="actions"><Button className="button--secondary" disabled={disabled || mutations.update.isPending} onClick={() => mutations.update.mutate({ entry, value: payload() })}>Update {entry.recipeTitle}</Button><Button className="button--text" disabled={disabled} onClick={() => mutations.update.mutate({ entry, value: payload(true), action: "refresh" })}>Refresh {entry.recipeTitle} nutrition</Button><Button className="button--text" disabled={disabled} onClick={() => mutations.copy.mutate(entry)}>Copy {entry.recipeTitle} to next day</Button><Button className="button--text" onClick={() => mutations.remove.mutate(entry)}>Remove {entry.recipeTitle}</Button>{mutations.conflict ? <Button onClick={() => void mutations.reload()}>Reload plan</Button> : null}</div>
    </article>
  );
}

