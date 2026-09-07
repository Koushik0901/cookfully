import { useEffect, useState } from "react";
import { ChefHat, Copy, RefreshCw, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import { Button, ConfirmDialog, DecimalInput, Field, RecipeMedia, Select } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { formatCookingInput, formatCookingNumber } from "../recipes/formatCooking";
import { RecipeMetadata } from "../recipes/RecipeMetadata";
import type { MealPlanEntry as Entry, RecipePage } from "./types";
import { nutritionConfidenceLabel } from "./nutritionConfidence";
import { useMealPlanMutations } from "./useMealPlanMutations";
import { addDays } from "./dates";

const SLOTS = ["breakfast", "lunch", "dinner", "snack"];

type Recipe = RecipePage["items"][number];

export function MealPlanEntry({ entry, weekStart, recipe, readOnly = false }: { entry: Entry; weekStart: string; recipe?: Recipe; readOnly?: boolean }) {
  const [servings, setServings] = useState(formatCookingInput(entry.servings));
  const [mealSlot, setMealSlot] = useState(entry.mealSlot);
  useEffect(() => setServings(formatCookingInput(entry.servings)), [entry.servings]);
  const mutations = useMealPlanMutations(weekStart);
  const canCopyToNextDay = entry.localDate < addDays(weekStart, 6);
  const cooked = entry.cookingStatus === "cooked";
  const disabled = !entry.recipeId || readOnly || cooked;
  const cookUrl = entry.recipeId ? `/app/recipes/${entry.recipeId}/cook?entry=${entry.id}&week=${weekStart}` : "";
  const payload = (refreshNutrition = false) => ({
    localDate: entry.localDate,
    mealSlot,
    recipeId: entry.recipeId!,
    servings,
    position: entry.position,
    refreshNutrition,
  });

  return (
    <article className={`plan-entry${readOnly ? " plan-entry--past" : ""}${cooked ? " plan-entry--cooked" : ""}`}>
      <div className="plan-entry__main">
        {entry.recipeId ? (
          <Link className={`plan-entry__media ${recipe?.imageUrl ? "" : "plan-entry__media--fallback"}`} to={`/app/recipes/${entry.recipeId}`} aria-label={`Open ${entry.recipeTitle}`}>
            {recipe ? <RecipeMedia recipe={recipe} sizes="84px" /> : <RecipeFallbackArt title={entry.recipeTitle} />}
          </Link>
        ) : <span className="plan-entry__media plan-entry__media--fallback"><RecipeFallbackArt title={entry.recipeTitle} /></span>}
        <div className="plan-entry__body">
          <div className="plan-entry__heading">
            <div className="plan-entry__title"><h4>{entry.recipeId ? <Link to={`/app/recipes/${entry.recipeId}`}>{entry.recipeTitle}</Link> : entry.recipeTitle}</h4></div>
            <details className="nutrition-confidence nutrition-confidence--meal">
              <summary>{nutritionConfidenceLabel(entry.nutrition.status, entry.nutrition.coverageRatio)}</summary>
              <p>{entry.nutrition.status === "unavailable" ? "Nutrition is not available yet; the meal is still ready to cook." : `${entry.nutrition.status.replace("_", " ")} nutrition · ${Math.round(Number(entry.nutrition.coverageRatio) * 100)}% source coverage`}</p>
            </details>
          </div>
          <div className="plan-entry__nutrition" aria-label={`${entry.recipeTitle} plan contribution`}>
            <span><strong>{formatCookingNumber(entry.servings)}</strong> {Number(entry.servings) === 1 ? "serving" : "servings"}</span>
            <RecipeMetadata recipe={{ title: entry.recipeTitle, prepMinutes: recipe?.prepMinutes ?? null, cookMinutes: recipe?.cookMinutes ?? null, nutrition: entry.nutrition }} compact />
          </div>
          {entry.cookingStatus === "cooking" ? <p className="plan-entry__cooking-state">Cooking in progress · step {(entry.cookingStep ?? 0) + 1}</p> : cooked ? <p className="plan-entry__cooking-state">Cooked{Number(entry.leftoverServings ?? 0) > 0 ? ` · ${entry.leftoverServings} leftover ${Number(entry.leftoverServings) === 1 ? "serving" : "servings"} until ${entry.leftoversExpireOn}` : ""}</p> : null}
        </div>
      </div>
      {!entry.recipeId ? <p className="notice">Historical snapshot retained; the source recipe was deleted.</p> : null}
      {mutations.error instanceof Error ? <p className="error-text" role="alert">{mutations.conflict ? "The plan changed elsewhere. Reload before trying again." : mutations.error.message}</p> : null}
      {mutations.message ? <p className="success-text" role="status">{mutations.message}</p> : null}
      {readOnly ? <p className="plan-entry__past-note">Past day · this meal is read-only.</p> : (
        <div className="plan-entry__actions">
          {entry.recipeId ? <Button variant={entry.cookingStatus === "cooking" ? "secondary" : "ghost"} asChild><Link to={cookUrl} aria-label={`${entry.cookingStatus === "cooking" ? "Resume cooking" : cooked ? "Review cooked" : "Start cooking"} ${entry.recipeTitle}`}><ChefHat aria-hidden="true" />{entry.cookingStatus === "cooking" ? "Resume" : cooked ? "Cooked" : "Cook"}</Link></Button> : null}
          {!cooked ? <details className="plan-entry__adjust">
            <summary>Adjust meal</summary>
            <div className="entry-controls"><Field label={`${entry.recipeTitle} servings`}><DecimalInput value={servings} disabled={disabled} onInput={(event) => setServings(event.currentTarget.value)} /></Field><Field label={`${entry.recipeTitle} meal slot`}><Select value={mealSlot} disabled={disabled} onChange={(event) => setMealSlot(event.target.value)}>{SLOTS.map((slot) => <option key={slot} value={slot}>{slot}</option>)}</Select></Field></div>
            <div className="plan-entry__adjust-actions"><Button variant="secondary" disabled={disabled || mutations.update.isPending} onClick={() => mutations.update.mutate({ entry, value: payload() })}>Save changes</Button><Button variant="ghost" disabled={disabled} onClick={() => mutations.update.mutate({ entry, value: payload(true), action: "refresh" })}><RefreshCw aria-hidden="true" />Refresh nutrition</Button><ConfirmDialog trigger={<Button variant="ghost" className="plan-entry__remove" disabled={mutations.remove.isPending}><Trash2 aria-hidden="true" />Remove</Button>} title={`Remove ${entry.recipeTitle} from your plan?`} description="This also marks the grocery list for refresh. The meal will be removed from its current day." confirmLabel="Remove meal" onConfirm={() => mutations.remove.mutate(entry)} />{mutations.conflict ? <Button onClick={() => void mutations.reload()}>Reload plan</Button> : null}</div>
          </details> : null}
          {!cooked ? <Button variant="ghost" disabled={disabled || !canCopyToNextDay} title={canCopyToNextDay ? "Copy to next day" : "The next day is outside this planning week"} onClick={() => mutations.copy.mutate(entry)}><Copy aria-hidden="true" />{canCopyToNextDay ? "Copy to next day" : "Next day outside week"}</Button> : null}
        </div>
      )}
    </article>
  );
}
