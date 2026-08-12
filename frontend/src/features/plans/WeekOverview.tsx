import { ArrowRight, Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { formatCookingNumber } from "../recipes/formatCooking";
import { longDate } from "./dates";
import type { MealPlanEntry, RecipePage } from "./types";

const SLOT_ORDER = new Map(["breakfast", "lunch", "dinner", "snack"].map((slot, index) => [slot, index]));
type Recipe = RecipePage["items"][number];

function weekday(value: string) {
  return new Intl.DateTimeFormat("en-CA", { weekday: "long", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

export function WeekOverview({ dates, entries, recipesById, selectedDate, onOpenDay }: { dates: string[]; entries: MealPlanEntry[]; recipesById: Map<string, Recipe>; selectedDate: string; onOpenDay: (date: string) => void }) {
  const plannedDays = new Set(entries.map((entry) => entry.localDate)).size;
  const usedSlots = new Set(entries.map((entry) => `${entry.localDate}:${entry.mealSlot}`)).size;
  return (
    <section className="week-overview" aria-labelledby="week-overview-title">
      <header className="week-overview__heading">
        <div><p className="eyebrow">Week view</p><h2 id="week-overview-title">See the food, not just the count</h2></div>
        <p>{entries.length ? `${entries.length} meals across ${plannedDays} ${plannedDays === 1 ? "day" : "days"}. ${Math.max(0, 28 - usedSlots)} meal slots are still open.` : "The week is open. Start with the meals that matter most to you."}</p>
      </header>
      <div className="week-board" aria-label="Meals across the week">
        {dates.map((date) => {
          const dayEntries = entries.filter((entry) => entry.localDate === date).sort((a, b) => (SLOT_ORDER.get(a.mealSlot) ?? 9) - (SLOT_ORDER.get(b.mealSlot) ?? 9) || a.position - b.position);
          const daySlots = new Set(dayEntries.map((entry) => entry.mealSlot)).size;
          return (
            <article className={`week-day${date === selectedDate ? " week-day--selected" : ""}`} key={date}>
              <button className="week-day__header" onClick={() => onOpenDay(date)} aria-label={`Edit ${weekday(date)}, ${longDate(date)}`}>
                <span>{weekday(date)}</span><strong>{longDate(date)}</strong>
              </button>
              {dayEntries.length ? (
                <ul className="week-day__meals">
                  {dayEntries.map((entry) => {
                    const recipe = entry.recipeId ? recipesById.get(entry.recipeId) : undefined;
                    return (
                      <li key={entry.id}>
                        {entry.recipeId ? <Link className="week-meal__media" to={`/app/recipes/${entry.recipeId}`} aria-label={`Open ${entry.recipeTitle}`}>{recipe?.imageUrl ? <img src={recipe.imageUrl} alt="" loading="lazy" decoding="async" /> : <RecipeFallbackArt title={entry.recipeTitle} />}</Link> : <span className="week-meal__media"><RecipeFallbackArt title={entry.recipeTitle} /></span>}
                        <div><small>{entry.mealSlot}</small><strong>{entry.recipeTitle}</strong><span>{formatCookingNumber(entry.servings)} {Number(entry.servings) === 1 ? "serving" : "servings"}</span></div>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className="week-day__empty"><span>Nothing decided yet</span><button onClick={() => onOpenDay(date)}><Plus aria-hidden="true" />Plan this day</button></div>
              )}
              {dayEntries.length ? <button className="week-day__footer" onClick={() => onOpenDay(date)}><span>{Math.max(0, 4 - daySlots)} {4 - daySlots === 1 ? "slot" : "slots"} open</span><span>Edit day <ArrowRight aria-hidden="true" /></span></button> : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
