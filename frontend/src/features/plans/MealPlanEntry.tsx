import { useEffect, useState } from "react";
import { Copy, RefreshCw, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import { Button, DecimalInput, Field, Select } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { formatCookingInput, formatCookingNumber } from "../recipes/formatCooking";
import { RecipeMetadata } from "../recipes/RecipeMetadata";
import type { MealPlanEntry as Entry, RecipePage } from "./types";
import { nutritionConfidenceLabel } from "./nutritionConfidence";
import { useMealPlanMutations } from "./useMealPlanMutations";

const SLOTS = ["breakfast", "lunch", "dinner", "snack"];

type Recipe = RecipePage["items"][number];

export function MealPlanEntry({ entry, weekStart, recipe }: { entry: Entry; weekStart: string; recipe?: Recipe }) {
  const [servings, setServings] = useState(formatCookingInput(entry.servings));
  const [mealSlot, setMealSlot] = useState(entry.mealSlot);
  useEffect(() => setServings(formatCookingInput(entry.servings)), [entry.servings]);
  const mutations = useMealPlanMutations(weekStart);
  const payload = (refreshNutrition = false) => ({ localDate: entry.localDate, mealSlot, recipeId: entry.recipeId!, servings, position: entry.position, refreshNutrition });
  const disabled = !entry.recipeId;
  return (
    <article className="plan-entry">
      <div className="plan-entry__main">
        {entry.recipeId ? <Link className={`plan-entry__media ${recipe?.imageUrl ? "" : "plan-entry__media--fallback"}`} to={`/app/recipes/${entry.recipeId}`} aria-label={`Open ${entry.recipeTitle}`}>{recipe?.imageUrl ? <img src={recipe.imageUrl} alt="" loading="lazy" decoding="async" /> : <RecipeFallbackArt title={entry.recipeTitle} />}</Link> : <span className="plan-entry__media plan-entry__media--fallback"><RecipeFallbackArt title={entry.recipeTitle} /></span>}
        <div className="plan-entry__body">
          <div className="plan-entry__heading"><div className="plan-entry__title"><h4>{entry.recipeId ? <Link to={`/app/recipes/${entry.recipeId}`}>{entry.recipeTitle}</Link> : entry.recipeTitle}</h4></div><details className="nutrition-confidence nutrition-confidence--meal"><summary>{nutritionConfidenceLabel(entry.nutrition.status, entry.nutrition.coverageRatio)}</summary><p>{entry.nutrition.status.replace("_", " ")} nutrition · {Math.round(Number(entry.nutrition.coverageRatio) * 100)}% source coverage</p></details></div>
          <div className="plan-entry__nutrition" aria-label={`${entry.recipeTitle} plan contribution`}><span><strong>{formatCookingNumber(entry.servings)}</strong> {Number(entry.servings) === 1 ? "serving" : "servings"}</span><RecipeMetadata recipe={recipe ?? { title: entry.recipeTitle, prepMinutes: null, cookMinutes: null, nutrition: entry.nutrition }} compact /></div>
        </div>
      </div>
      {!entry.recipeId ? <p className="notice">Historical snapshot retained; the source recipe was deleted.</p> : null}
      {mutations.error instanceof Error ? <p className="error-text" role="alert">{mutations.conflict ? "The plan changed elsewhere. Reload before trying again." : mutations.error.message}</p> : null}
      {mutations.message ? <p className="success-text" role="status">{mutations.message}</p> : null}
      <div className="plan-entry__actions"><details className="plan-entry__adjust"><summary>Adjust meal</summary><div className="entry-controls"><Field label={`${entry.recipeTitle} servings`}><DecimalInput value={servings} disabled={disabled} onInput={(event) => setServings(event.currentTarget.value)} /></Field><Field label={`${entry.recipeTitle} meal slot`}><Select value={mealSlot} disabled={disabled} onChange={(event) => setMealSlot(event.target.value)}>{SLOTS.map((slot) => <option key={slot} value={slot}>{slot}</option>)}</Select></Field></div><div className="plan-entry__adjust-actions"><Button variant="secondary" disabled={disabled || mutations.update.isPending} onClick={() => mutations.update.mutate({ entry, value: payload() })}>Save changes</Button><Button variant="ghost" disabled={disabled} onClick={() => mutations.update.mutate({ entry, value: payload(true), action: "refresh" })}><RefreshCw aria-hidden="true" />Refresh nutrition</Button><Button variant="ghost" className="plan-entry__remove" onClick={() => mutations.remove.mutate(entry)}><Trash2 aria-hidden="true" />Remove</Button>{mutations.conflict ? <Button onClick={() => void mutations.reload()}>Reload plan</Button> : null}</div></details><Button variant="ghost" disabled={disabled} onClick={() => mutations.copy.mutate(entry)}><Copy aria-hidden="true" />Copy to next day</Button></div>
    </article>
  );
}
