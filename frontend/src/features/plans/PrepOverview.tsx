import { ArrowRight, Check, ShoppingBasket } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { formatCookingNumber } from "../recipes/formatCooking";
import type { MealPlanEntry, RecipePage } from "./types";

type Recipe = RecipePage["items"][number];
type PrepGroup = { key: string; title: string; recipeId: string | null; recipe?: Recipe; entries: MealPlanEntry[]; servings: number };

function shortDay(value: string) {
  return new Intl.DateTimeFormat("en-CA", { weekday: "short", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function groceryLabel(status?: string) {
  if (status === "current") return "Grocery list ready";
  if (status === "generating") return "Grocery list is updating";
  if (status === "failed") return "Grocery list needs attention";
  if (status === "dirty") return "Grocery list needs a refresh";
  return "Grocery list not made yet";
}

export function PrepOverview({ entries, recipesById, groceryStatus }: { entries: MealPlanEntry[]; recipesById: Map<string, Recipe>; groceryStatus?: string }) {
  const groups = new Map<string, PrepGroup>();
  entries.forEach((entry) => {
    const key = entry.recipeId ?? `snapshot:${entry.recipeTitle}`;
    const current = groups.get(key) ?? { key, title: entry.recipeTitle, recipeId: entry.recipeId, recipe: entry.recipeId ? recipesById.get(entry.recipeId) : undefined, entries: [], servings: 0 };
    current.entries.push(entry);
    current.servings += Number(entry.servings);
    groups.set(key, current);
  });
  const prepGroups = [...groups.values()].sort((a, b) => b.entries.length - a.entries.length || a.title.localeCompare(b.title));
  const repeatGroups = prepGroups.filter((group) => group.entries.length > 1);
  const plannedDays = new Set(entries.map((entry) => entry.localDate)).size;

  if (!entries.length) {
    return <section className="prep-empty"><RecipeFallbackArt title="fresh produce" /><div><p className="eyebrow">Prep view</p><h2>Your cooking list will gather here</h2><p>Plan a few meals first. Cookfully will combine repeated dishes and total the servings to prepare.</p></div></section>;
  }

  return (
    <section className="prep-overview" aria-labelledby="prep-title">
      <header className="prep-overview__heading">
        <div><p className="eyebrow">Prep view</p><h2 id="prep-title">Cook {prepGroups.length} {prepGroups.length === 1 ? "dish" : "dishes"} for {entries.length} {entries.length === 1 ? "meal" : "meals"}</h2></div>
        <p>{repeatGroups.length ? `${repeatGroups.length} ${repeatGroups.length === 1 ? "dish appears" : "dishes appear"} more than once—good candidates to batch.` : "Each dish appears once. Repeating a favorite can make prep lighter."}</p>
      </header>
      <div className="prep-layout">
        <ol className="prep-list">
          {prepGroups.map((group, index) => (
            <li className="prep-item" key={group.key}>
              <span className="prep-item__number data-value">{String(index + 1).padStart(2, "0")}</span>
              {group.recipeId ? <Link className="prep-item__media" to={`/app/recipes/${group.recipeId}`} aria-label={`Open ${group.title}`}>{group.recipe?.imageUrl ? <img src={group.recipe.imageUrl} alt="" loading="lazy" decoding="async" /> : <RecipeFallbackArt title={group.title} />}</Link> : <span className="prep-item__media"><RecipeFallbackArt title={group.title} /></span>}
              <div className="prep-item__body">
                <div><h3>{group.title}</h3>{group.entries.length > 1 ? <span className="prep-item__batch"><Check aria-hidden="true" />Batch-friendly</span> : null}</div>
                <strong>{formatCookingNumber(String(group.servings))} total {group.servings === 1 ? "serving" : "servings"}</strong>
                <p>{group.entries.map((entry) => `${shortDay(entry.localDate)} ${entry.mealSlot}`).join(" · ")}</p>
              </div>
              {group.recipeId ? <Link className="prep-item__open" to={`/app/recipes/${group.recipeId}`}>Review recipe <ArrowRight aria-hidden="true" /></Link> : null}
            </li>
          ))}
        </ol>
        <aside className="prep-readiness" aria-label="Preparation readiness">
          <p className="eyebrow">Before you cook</p><h2>Your week is taking shape</h2>
          <dl><div><dt>Days covered</dt><dd>{plannedDays} of 7</dd></div><div><dt>Meals planned</dt><dd>{entries.length}</dd></div><div><dt>Batch opportunities</dt><dd>{repeatGroups.length}</dd></div><div><dt>Groceries</dt><dd>{groceryLabel(groceryStatus)}</dd></div></dl>
          <Button asChild><Link to="/app/grocery"><ShoppingBasket aria-hidden="true" />Review groceries</Link></Button>
          <p>Quantities come from the servings already in your plan. Adjust a meal in Day view when the batch size changes.</p>
        </aside>
      </div>
    </section>
  );
}
