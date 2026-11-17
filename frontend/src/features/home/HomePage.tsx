import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { ArrowRight, CalendarDays, Check, ChefHat, Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { Button, ErrorRecovery, RecipeMedia, Skeleton } from "../../components";
import { FoodCategoryIcon } from "../../components/FoodCategoryIcon";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import type { PantryRecipeMatch } from "../pantry/types";
import { todayInTimezone, weekDates, weekStartFor } from "../plans/dates";
import type { MealPlanEntry } from "../plans/types";
import { formatCookingNumber } from "../recipes/formatCooking";
import { RecipeMetadata } from "../recipes/RecipeMetadata";
import { recipeTimeLabel } from "../recipes/recipeMetadataUtils";
import type { Recipe } from "../recipes/types";
import { isRecipePlannable } from "../recipes/recipeEligibility";
import { homeApi } from "./api";
import { prefetchRecipeIntent } from "../../app/routeIntent";

const DAY_MS = 86_400_000;
const MEAL_ORDER = new Map(["breakfast", "lunch", "dinner", "snack"].map((slot, index) => [slot, index]));

function weekday(value: string, length: "long" | "short" = "long") {
  return new Intl.DateTimeFormat("en-CA", { weekday: length, timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function fullDate(value: string) {
  return new Intl.DateTimeFormat("en-CA", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function greetingFor(timezone: string) {
  const hour = Number(new Intl.DateTimeFormat("en-CA", { hour: "numeric", hourCycle: "h23", timeZone: timezone }).format(new Date()));
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function byMealOrder(a: MealPlanEntry, b: MealPlanEntry) {
  return (MEAL_ORDER.get(a.mealSlot) ?? 99) - (MEAL_ORDER.get(b.mealSlot) ?? 99) || a.position - b.position;
}

function slotLabel(slot: string) {
  return slot ? slot[0].toUpperCase() + slot.slice(1) : "Meal";
}

function daysUntil(today: string, date: string) {
  return Math.round((Date.parse(`${date}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / DAY_MS);
}

function relativeUseBy(today: string, useBy: string) {
  const days = daysUntil(today, useBy);
  if (days < 0) return "Check before using";
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  return `In ${days} days`;
}

function recommendationReason(recipe: Recipe, match: PantryRecipeMatch | undefined, plannedRecipeIds: Set<string>) {
  if (match?.availability === "full") return "Everything you need is in your pantry";
  if (match?.availability === "partial" && match.missingIngredients.length <= 2) {
    const count = match.missingIngredients.length;
    return `Only ${count} ${count === 1 ? "ingredient" : "ingredients"} left to pick up`;
  }
  if (match && Number(match.coverageRatio) >= 0.5) return "Uses most of what you already have";
  if (recipe.favorite && !plannedRecipeIds.has(recipe.id)) return "A favourite that is not on this week’s plan";
  if ((recipe.mealRoles ?? []).includes("dinner")) return "Saved for an open dinner this week";
  return "A good next choice from your recipe box";
}

function recommendationRank(recipe: Recipe, match: PantryRecipeMatch | undefined, plannedRecipeIds: Set<string>) {
  let score = match?.availability === "full" ? 50 : match?.availability === "partial" ? 30 : 0;
  score += Math.round(Number(match?.coverageRatio ?? 0) * 10);
  if (recipe.favorite) score += 5;
  if (!plannedRecipeIds.has(recipe.id)) score += 4;
  if ((recipe.mealRoles ?? []).includes("dinner")) score += 2;
  return score;
}

function WeekDay({ date, entries, recipesById, today }: { date: string; entries: MealPlanEntry[]; recipesById: Map<string, Recipe>; today: string }) {
  const ordered = [...entries].sort(byMealOrder);
  // Dinner is the meal most people plan a week around, so it represents the day.
  const meal = ordered.find((entry) => entry.mealSlot === "dinner") ?? ordered[0];
  const recipe = meal?.recipeId ? recipesById.get(meal.recipeId) : undefined;
  const label = meal ? `${weekday(date)}: ${meal.recipeTitle}${entries.length > 1 ? ` and ${entries.length - 1} more` : ""}` : `${weekday(date)}: nothing planned`;
  return (
    <Link className={`home-week-day${date === today ? " is-today" : ""}${meal ? " is-planned" : ""}`} to={`/app/plan?date=${date}`} aria-label={label}>
      <span className="home-week-day__label">{date === today ? "Today" : `${weekday(date, "short")} ${Number(date.slice(8))}`}</span>
      {meal ? <>
        <span className="home-week-day__media home-media" aria-hidden="true">{recipe ? <RecipeMedia recipe={recipe} sizes="160px" /> : <RecipeFallbackArt title={meal.recipeTitle} />}</span>
        <span className="home-week-day__title">{meal.recipeTitle}</span>
        {entries.length > 1 ? <small>+{entries.length - 1} more</small> : null}
      </> : <span className="home-week-day__open"><Plus aria-hidden="true" /><span>Plan</span></span>}
    </Link>
  );
}

export function HomePage() {
  const queryClient = useQueryClient();
  const home = useQuery({
    queryKey: ["home-bootstrap"],
    queryFn: homeApi.get,
    staleTime: 15_000,
    retry: 1,
  });
  const preferences = home.data?.preferences;
  const recipePage = home.data?.recipes;
  const pantryItems = home.data?.pantry;
  const plan = home.data?.plan;
  const grocery = home.data?.grocery;
  const pantryMatches = home.data?.pantryMatches;
  const today = preferences ? todayInTimezone(preferences.timezone) : "";
  const weekStart = preferences ? weekStartFor(today, preferences.weekStartsOn) : "";

  const activeRecipes = useMemo(() => recipePage?.items.filter((recipe) => recipe.status !== "archived") ?? [], [recipePage?.items]);
  const readyRecipes = useMemo(() => activeRecipes.filter(isRecipePlannable), [activeRecipes]);
  const recipesById = useMemo(() => new Map(activeRecipes.map((recipe) => [recipe.id, recipe])), [activeRecipes]);

  if (home.isPending) return <main className="page-shell home-page"><Skeleton label="Preparing your kitchen" lines={7} /></main>;
  if (home.isError || !preferences || !recipePage || !pantryItems) return <main className="page-shell home-page"><ErrorRecovery title="Your kitchen could not be prepared" onRetry={() => void home.refetch()} /></main>;

  const groceryMissing = !grocery;
  const entries = plan?.entries ?? [];
  const todayEntries = entries.filter((entry) => entry.localDate === today).sort(byMealOrder);
  const dinner = todayEntries.find((entry) => entry.mealSlot === "dinner") ?? todayEntries[0];
  const focusSlot = dinner?.mealSlot ?? "dinner";
  const focusTimeLabel = dinner?.cookingStatus === "cooking" ? "Cooking now" : dinner?.cookingStatus === "cooked" ? "Made today" : focusSlot === "dinner" ? "Tonight" : slotLabel(focusSlot);
  const dinnerRecipe = dinner?.recipeId ? recipesById.get(dinner.recipeId) : undefined;
  const days = weekStart ? weekDates(weekStart) : [];
  const entriesByDate = new Map(days.map((date) => [date, entries.filter((entry) => entry.localDate === date)]));
  const plannedDates = new Set(entries.filter((entry) => days.includes(entry.localDate)).map((entry) => entry.localDate));
  const plannedRecipeIds = new Set(entries.flatMap((entry) => entry.recipeId ? [entry.recipeId] : []));
  const matchesByRecipeId = new Map((pantryMatches ?? []).map((match) => [match.recipeId, match]));
  const dinnerMatch = dinner?.recipeId ? matchesByRecipeId.get(dinner.recipeId) : undefined;
  const missing = dinnerMatch?.missingIngredients ?? [];
  const recommendations = [...readyRecipes]
    .filter((recipe) => recipe.id !== dinner?.recipeId)
    .sort((a, b) => recommendationRank(b, matchesByRecipeId.get(b.id), plannedRecipeIds) - recommendationRank(a, matchesByRecipeId.get(a.id), plannedRecipeIds) || new Date(b.updatedAt ?? 0).getTime() - new Date(a.updatedAt ?? 0).getTime())
    .slice(0, 3);
  const savedLeftovers = entries
    .filter((entry) => entry.cookingStatus === "cooked" && Number(entry.leftoverServings ?? 0) > 0 && entry.leftoversExpireOn)
    .sort((a, b) => String(a.leftoversExpireOn).localeCompare(String(b.leftoversExpireOn)))
    .slice(0, 3);
  const useSoon = pantryItems
    .filter((item) => item.expiresOn && daysUntil(today, item.expiresOn) <= 7)
    .sort((a, b) => String(a.expiresOn).localeCompare(String(b.expiresOn)))
    .slice(0, Math.max(0, 3 - savedLeftovers.length));
  const activeGroceryItems = grocery?.items.filter((item) => !item.checked) ?? [];
  const purchasedCount = grocery?.items.filter((item) => item.checked).length ?? 0;
  const groceryHeading = grocery?.status === "generating" ? "Updating your list…"
    : groceryMissing || !grocery ? "No list yet"
    : activeGroceryItems.length ? `${activeGroceryItems.length} ${activeGroceryItems.length === 1 ? "thing" : "things"} to pick up`
    : "Nothing waiting to buy";
  const heroFacts = dinner ? [
    dinnerRecipe ? recipeTimeLabel(dinnerRecipe) : "Time not set",
    `${formatCookingNumber(dinner.servings)} ${Number(dinner.servings) === 1 ? "serving" : "servings"}`,
    dinner.nutrition?.caloriesKcal ? `${Math.round(Number(dinner.nutrition.caloriesKcal))} kcal` : null,
    dinner.nutrition?.proteinG ? `${Math.round(Number(dinner.nutrition.proteinG))} g protein` : null,
    dinner.cookingStatus === "cooked" && Number(dinner.leftoverServings ?? 0) > 0 ? `${dinner.leftoverServings} leftover ${Number(dinner.leftoverServings) === 1 ? "serving" : "servings"}` : null,
  ].filter((value): value is string => Boolean(value)) : [];
  const dinnerCookUrl = dinner?.recipeId ? `/app/recipes/${dinner.recipeId}/cook?entry=${dinner.id}&week=${weekStart}` : "";
  const todayCalories = Math.round(todayEntries.reduce((sum, entry) => sum + Number(entry.nutrition?.caloriesKcal ?? 0), 0));
  const todayProtein = Math.round(todayEntries.reduce((sum, entry) => sum + Number(entry.nutrition?.proteinG ?? 0), 0));
  const recipeIntent = (recipeId: string) => ({
    onMouseEnter: () => prefetchRecipeIntent(queryClient, recipeId),
    onFocus: () => prefetchRecipeIntent(queryClient, recipeId),
    onPointerDown: () => prefetchRecipeIntent(queryClient, recipeId),
  });

  return (
    <main className="page-shell home-page">
      <header className="home-intro">
        <div><p className="home-intro__date">{fullDate(today)}</p><h1>{greetingFor(preferences.timezone)}</h1></div>
        <div className="home-intro__actions">
          <Button variant="secondary" asChild><Link to="/app/recipes/new"><Plus aria-hidden="true" />Add recipe</Link></Button>
          <Button variant="secondary" asChild><Link to="/app/grocery?add=1"><Plus aria-hidden="true" />Grocery item</Link></Button>
        </div>
      </header>

      <div className="home-dashboard">
        <article className="home-tonight" aria-labelledby="tonight-heading">
          <div className="home-tonight__media home-media" aria-hidden="true">{dinnerRecipe ? <RecipeMedia recipe={dinnerRecipe} loading="eager" /> : <RecipeFallbackArt title={dinner?.recipeTitle ?? "Tonight’s dinner"} loading="eager" />}</div>
          <div className="home-tonight__copy">
            <p className="eyebrow" id="tonight-heading">{dinner ? `${focusTimeLabel} · ${slotLabel(focusSlot)}` : focusTimeLabel}</p>
            {dinner ? <>
              <h2>{dinner.recipeTitle}</h2>
              {heroFacts.length ? <ul className="home-tonight__facts">{heroFacts.map((fact) => <li key={fact}>{fact}</li>)}</ul> : null}
              {dinnerMatch?.availability === "full" ? <p className="home-tonight__availability"><Check aria-hidden="true" /><span>Everything you need is already in the pantry.</span></p> : missing.length ? <p className="home-tonight__availability"><span>Still needed: {missing.slice(0, 3).join(", ")}{missing.length > 3 ? ` and ${missing.length - 3} more` : ""}. <Link to="/app/grocery">Check groceries</Link></span></p> : null}
              <div className="home-tonight__actions">
                {dinner.recipeId ? <>
                  <Button size="lg" asChild><Link to={dinnerCookUrl} {...recipeIntent(dinner.recipeId)}><ChefHat aria-hidden="true" />{dinner.cookingStatus === "cooking" ? "Resume cooking" : dinner.cookingStatus === "cooked" ? "See cooked meal" : "Start cooking"}</Link></Button>
                  <Button variant="secondary" size="lg" asChild><Link to={`/app/recipes/${dinner.recipeId}`} {...recipeIntent(dinner.recipeId)}>View recipe</Link></Button>
                </> : <Button size="lg" asChild><Link to="/app/plan">Review dinner</Link></Button>}
              </div>
            </> : readyRecipes.length ? <>
              <h2>Nothing planned for tonight yet</h2>
              <p>Pick one dish now and the grocery list will follow.</p>
              <div className="home-tonight__actions"><Button size="lg" asChild><Link to={`/app/plan?date=${today}&slot=${focusSlot}`}><CalendarDays aria-hidden="true" />Plan tonight</Link></Button></div>
            </> : <>
              <h2>Save your first recipe</h2>
              <p>Start with a dish you already love.</p>
              <div className="home-tonight__actions"><Button size="lg" asChild><Link to="/app/recipes/new">Add a recipe</Link></Button></div>
            </>}
          </div>
        </article>

        <section className="home-today" aria-labelledby="home-today-heading">
          <h2 id="home-today-heading">Today’s meals</h2>
          {todayEntries.length ? <ol className="home-today__list">{todayEntries.map((entry) => {
            const recipe = entry.recipeId ? recipesById.get(entry.recipeId) : undefined;
            const status = entry.cookingStatus === "cooked" ? "cooked" : entry.cookingStatus === "cooking" ? "cooking now" : entry.id === dinner?.id ? "up next" : "planned";
            return (
              <li key={entry.id} className={entry.id === dinner?.id ? "is-focus" : undefined}>
                <span className="home-today__media home-media" aria-hidden="true">{recipe ? <RecipeMedia recipe={recipe} sizes="52px" /> : <RecipeFallbackArt title={entry.recipeTitle} />}</span>
                <span className="home-today__meal"><small>{slotLabel(entry.mealSlot)} · {status}</small><strong>{entry.recipeTitle}</strong></span>
                {entry.cookingStatus === "cooked" ? <Check role="img" aria-label="Cooked" /> : null}
              </li>
            );
          })}</ol> : <div className="home-module-empty"><strong>Nothing on the calendar today</strong><p>Meals you plan for today line up here in order.</p><Link to={`/app/plan?date=${today}`}>Open today’s plan</Link></div>}
          {todayCalories ? <p className="home-today__total">{todayCalories.toLocaleString("en-CA")} kcal planned today{todayProtein ? ` · ${todayProtein} g protein` : ""}</p> : null}
        </section>
      </div>

      <section className="home-week" aria-labelledby="home-week-heading">
        <div className="home-section-heading"><div><h2 id="home-week-heading">This week</h2><p>{plannedDates.size} of 7 days planned</p></div><Link to="/app/plan">Open plan <ArrowRight aria-hidden="true" /></Link></div>
        <div className="home-week-grid" aria-label={`${plannedDates.size} of 7 days have planned meals`}>{days.map((date) => <WeekDay key={date} date={date} entries={entriesByDate.get(date) ?? []} recipesById={recipesById} today={today} />)}</div>
      </section>

      <div className="home-priorities">
        <section className="home-use-soon" aria-labelledby="home-use-soon-heading">
          <div className="home-section-heading"><div><h2 id="home-use-soon-heading">Use soon</h2></div><Link to="/app/pantry">Open pantry <ArrowRight aria-hidden="true" /></Link></div>
          {savedLeftovers.length || useSoon.length ? <ul className="home-list">
            {savedLeftovers.map((entry) => <li key={`leftovers-${entry.id}`}><span className="home-use-soon__produce" aria-hidden="true"><ChefHat /></span><span className="home-list__name"><strong>{entry.recipeTitle}</strong><small>{entry.leftoverServings} leftover {Number(entry.leftoverServings) === 1 ? "serving" : "servings"}</small></span><em className={daysUntil(today, entry.leftoversExpireOn!) <= 1 ? "is-urgent" : undefined}>{relativeUseBy(today, entry.leftoversExpireOn!)}</em></li>)}
            {useSoon.map((item) => <li key={item.id}><span className="home-use-soon__produce" aria-hidden="true"><FoodCategoryIcon name={item.displayName} size="row" /></span><span className="home-list__name"><strong>{item.displayName}</strong><small>{formatCookingNumber(item.quantity)} {item.unit}</small></span><em className={daysUntil(today, item.expiresOn!) <= 1 ? "is-urgent" : undefined}>{relativeUseBy(today, item.expiresOn!)}</em></li>)}
          </ul> : pantryItems.length ? <div className="home-module-empty"><strong>No use-by dates yet</strong><p>Add a date to fresh food and Cookfully will bring it here before it gets forgotten.</p><Link to="/app/pantry">Add dates in Pantry</Link></div> : <div className="home-module-empty"><strong>Your shelf can help decide dinner</strong><p>Add a few things you already have. Rough quantities are enough.</p><Link to="/app/pantry">Add pantry items</Link></div>}
        </section>

        <section className="home-grocery" aria-labelledby="home-grocery-heading">
          <div className="home-section-heading"><div><h2 id="home-grocery-heading">Grocery</h2><p>{groceryHeading}</p></div><Link to="/app/grocery">{groceryMissing ? "Start a list" : "Open list"} <ArrowRight aria-hidden="true" /></Link></div>
          {grocery?.status === "generating" ? <div className="home-module-empty"><strong>Building your list</strong><p>Your latest plan is being turned into a shopping list.</p></div>
            : groceryMissing || !grocery ? <div className="home-module-empty"><strong>Shop from your plan</strong><p>Build a list from this week’s meals, or start with one thing you need.</p><Link to="/app/grocery">Start a grocery list</Link></div>
            : activeGroceryItems.length ? <>
              <ul className="home-list">
                {activeGroceryItems.slice(0, 3).map((item) => <li key={item.id}><span className="home-list__name"><strong>{item.displayName}</strong><small>{formatCookingNumber(item.quantity)} {item.unit}</small></span></li>)}
                {activeGroceryItems.length > 3 ? <li className="home-list__more">and {activeGroceryItems.length - 3} more</li> : null}
              </ul>
              <p className="home-grocery__status">{purchasedCount ? `${purchasedCount} already in your basket.` : grocery.status === "dirty" ? "Your plan changed. Refresh the list before shopping." : "Ready for your next shop."}</p>
            </> : <div className="home-module-empty"><strong>{purchasedCount ? `${purchasedCount} picked up` : "Your list is clear"}</strong><p>Anything new from your plan will show up here.</p></div>}
        </section>
      </div>

      <section className="home-for-you" aria-labelledby="home-for-you-heading">
        <div className="home-section-heading"><div><h2 id="home-for-you-heading">Cook next</h2></div><Link to="/app/recipes">Browse recipes <ArrowRight aria-hidden="true" /></Link></div>
        {recommendations.length ? <div className="home-for-you__grid">{recommendations.map((recipe) => (
          <article className="home-recommendation" key={recipe.id}>
            <Link to={`/app/recipes/${recipe.id}`} aria-label={recipe.title} viewTransition {...recipeIntent(recipe.id)}>
              <span className="home-recommendation__media home-media"><RecipeMedia recipe={recipe} sizes="(max-width: 47.99rem) 120px, 34vw" /></span>
              <span className="home-recommendation__body"><span className="home-recommendation__reason">{recommendationReason(recipe, matchesByRecipeId.get(recipe.id), plannedRecipeIds)}</span><h3>{recipe.title}</h3><RecipeMetadata recipe={recipe} compact /></span>
            </Link>
          </article>
        ))}</div> : <div className="home-module-empty"><strong>Ideas need a recipe box</strong><p>Save a few dishes and Cookfully will surface useful next choices here.</p><Link to="/app/recipes/new">Add a recipe</Link></div>}
      </section>
    </main>
  );
}
