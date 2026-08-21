import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { ArrowRight, CalendarDays, ChefHat, PackageOpen, Plus, ShoppingBasket } from "lucide-react";
import { Link } from "react-router-dom";

import { Button, ErrorRecovery, RecipeMedia, Skeleton } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { groceryApi } from "../grocery/api";
import { pantryApi } from "../pantry/api";
import type { PantryRecipeMatch } from "../pantry/types";
import { planningApi } from "../plans/api";
import { todayInTimezone, weekDates, weekStartFor } from "../plans/dates";
import type { MealPlanEntry } from "../plans/types";
import { ApiProblem } from "../recipes/api";
import { formatCookingNumber, servingLabel } from "../recipes/formatCooking";
import { RecipeMetadata } from "../recipes/RecipeMetadata";
import { recipeTimeLabel } from "../recipes/recipeMetadataUtils";
import type { Recipe } from "../recipes/types";
import { isRecipeReadyToPlan } from "../recipes/recipeEligibility";

const DAY_MS = 86_400_000;
const MEAL_ORDER = new Map(["breakfast", "lunch", "dinner", "snack"].map((slot, index) => [slot, index]));

function weekday(value: string, length: "long" | "short" = "long") {
  return new Intl.DateTimeFormat("en-CA", { weekday: length, timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function greetingFor(timezone: string) {
  const hour = Number(new Intl.DateTimeFormat("en-CA", { hour: "numeric", hourCycle: "h23", timeZone: timezone }).format(new Date()));
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function mealHeadline(count: number) {
  const words = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven"];
  return `${words[count] ?? count} ${count === 1 ? "meal" : "meals"} planned`;
}

function relativeUseBy(today: string, useBy: string) {
  const days = Math.round((Date.parse(`${useBy}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / DAY_MS);
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
  if (recipe.mealRoles.includes("dinner")) return "Saved for an open dinner this week";
  return "A good next choice from your recipe box";
}

function recommendationRank(recipe: Recipe, match: PantryRecipeMatch | undefined, plannedRecipeIds: Set<string>) {
  let score = match?.availability === "full" ? 50 : match?.availability === "partial" ? 30 : 0;
  score += Math.round(Number(match?.coverageRatio ?? 0) * 10);
  if (recipe.favorite) score += 5;
  if (!plannedRecipeIds.has(recipe.id)) score += 4;
  if (recipe.mealRoles.includes("dinner")) score += 2;
  return score;
}

function WeekDay({ date, entries, recipesById, today }: { date: string; entries: MealPlanEntry[]; recipesById: Map<string, Recipe>; today: string }) {
  const meal = [...entries].sort((a, b) => (MEAL_ORDER.get(a.mealSlot) ?? 99) - (MEAL_ORDER.get(b.mealSlot) ?? 99) || a.position - b.position)[0];
  const recipe = meal?.recipeId ? recipesById.get(meal.recipeId) : undefined;
  const label = meal ? `${weekday(date)}: ${meal.recipeTitle}${entries.length > 1 ? ` and ${entries.length - 1} more` : ""}` : `${weekday(date)}: nothing planned`;
  return (
    <Link className={`home-week-day${date === today ? " is-today" : ""}${meal ? " is-planned" : ""}`} to={`/app/plan?date=${date}`} aria-label={label}>
      <span>{weekday(date, "short")}</span>
      <span className="home-week-day__media" aria-hidden="true">
        {recipe ? <RecipeMedia recipe={recipe} /> : meal ? <RecipeFallbackArt title={meal.recipeTitle} /> : <Plus />}
      </span>
      <small>{entries.length ? entries.length : "Open"}</small>
    </Link>
  );
}

export function HomePage() {
  const commandShortcut = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘ K" : "Ctrl K";
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const recipes = useQuery({ queryKey: ["planning-recipes"], queryFn: planningApi.recipes, retry: 1 });
  const pantry = useQuery({ queryKey: ["pantry-items"], queryFn: pantryApi.list, retry: false });
  const today = preferences.data ? todayInTimezone(preferences.data.timezone) : "";
  const weekStart = preferences.data ? weekStartFor(today, preferences.data.weekStartsOn) : "";
  const plan = useQuery({ queryKey: ["meal-plan", weekStart], queryFn: () => planningApi.plan(weekStart), enabled: Boolean(weekStart), retry: false });
  const grocery = useQuery({ queryKey: ["grocery-list", weekStart], queryFn: () => groceryApi.get(weekStart), enabled: Boolean(weekStart), retry: false });
  const pantryMatches = useQuery({
    queryKey: ["pantry-recipe-matches", "home"],
    queryFn: () => pantryApi.search(),
    enabled: Boolean(pantry.data?.length && recipes.data?.items.length),
    retry: false,
  });

  const activeRecipes = useMemo(() => recipes.data?.items.filter((recipe) => recipe.status !== "archived") ?? [], [recipes.data?.items]);
  const readyRecipes = useMemo(() => activeRecipes.filter(isRecipeReadyToPlan), [activeRecipes]);
  const recipesById = useMemo(() => new Map(activeRecipes.map((recipe) => [recipe.id, recipe])), [activeRecipes]);
  const recentRecipes = useMemo(() => [...activeRecipes].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()).slice(0, 4), [activeRecipes]);

  if (preferences.isPending) return <main className="page-shell home-page"><Skeleton label="Preparing your kitchen" lines={7} /></main>;
  if (preferences.isError) return <main className="page-shell home-page"><ErrorRecovery title="Your kitchen could not be prepared" onRetry={() => void preferences.refetch()} /></main>;

  const planMissing = plan.error instanceof ApiProblem && plan.error.status === 404;
  const groceryMissing = grocery.error instanceof ApiProblem && grocery.error.status === 404;
  const entries = plan.data?.entries ?? [];
  const todayEntries = entries.filter((entry) => entry.localDate === today).sort((a, b) => {
    const order = new Map(["breakfast", "lunch", "dinner", "snack"].map((slot, index) => [slot, index]));
    return (order.get(a.mealSlot) ?? 99) - (order.get(b.mealSlot) ?? 99) || a.position - b.position;
  });
  const dinner = todayEntries.find((entry) => entry.mealSlot === "dinner") ?? todayEntries[0];
  const focusSlot = dinner?.mealSlot ?? "dinner";
  const focusLabel = focusSlot[0].toUpperCase() + focusSlot.slice(1);
  const focusTimeLabel = focusSlot === "dinner" ? "Tonight" : focusLabel;
  const dinnerRecipe = dinner?.recipeId ? recipesById.get(dinner.recipeId) : undefined;
  const days = weekStart ? weekDates(weekStart) : [];
  const entriesByDate = new Map(days.map((date) => [date, entries.filter((entry) => entry.localDate === date)]));
  const plannedDates = new Set(entries.filter((entry) => days.includes(entry.localDate)).map((entry) => entry.localDate));
  const plannedRecipeIds = new Set(entries.flatMap((entry) => entry.recipeId ? [entry.recipeId] : []));
  const matchesByRecipeId = new Map((pantryMatches.data ?? []).map((match) => [match.recipeId, match]));
  const dinnerMatch = dinner?.recipeId ? matchesByRecipeId.get(dinner.recipeId) : undefined;
  const recommendations = [...readyRecipes]
    .filter((recipe) => recipe.id !== dinner?.recipeId)
    .sort((a, b) => recommendationRank(b, matchesByRecipeId.get(b.id), plannedRecipeIds) - recommendationRank(a, matchesByRecipeId.get(a.id), plannedRecipeIds) || new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
    .slice(0, 3);
  const useSoon = (pantry.data ?? [])
    .filter((item) => item.expiresOn && Date.parse(`${item.expiresOn}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`) <= 7 * DAY_MS)
    .sort((a, b) => String(a.expiresOn).localeCompare(String(b.expiresOn)))
    .slice(0, 3);
  const activeGroceryItems = grocery.data?.items.filter((item) => !item.checked) ?? [];
  const purchasedCount = grocery.data?.items.filter((item) => item.checked).length ?? 0;
  const groceryUnavailable = grocery.isError && !groceryMissing;
  const groceryHeading = grocery.isPending || grocery.data?.status === "generating" ? "Updating your list…"
    : groceryUnavailable ? "Your list is out of reach"
    : groceryMissing || !grocery.data ? "Start your grocery list"
    : activeGroceryItems.length ? `${activeGroceryItems.length} ${activeGroceryItems.length === 1 ? "thing" : "things"} to pick up`
    : "Nothing waiting to buy";
  const heroFacts = dinner ? [
    `${formatCookingNumber(dinner.servings)} ${Number(dinner.servings) === 1 ? "serving" : "servings"}`,
    dinnerRecipe ? recipeTimeLabel(dinnerRecipe) : "Time not set",
    dinner.nutrition?.caloriesKcal ? `${Math.round(Number(dinner.nutrition.caloriesKcal))} kcal` : null,
    dinner.nutrition?.proteinG ? `${Math.round(Number(dinner.nutrition.proteinG))} g protein` : null,
    dinner.nutrition?.fatG ? `${Math.round(Number(dinner.nutrition.fatG))} g fat` : null,
  ].filter((value): value is string => Boolean(value)) : [];

  return (
    <main className="page-shell home-page">
      <header className="home-intro">
        <div><p className="eyebrow">Your kitchen · {weekday(today)}</p><h1>{greetingFor(preferences.data.timezone)}</h1><p>Here’s what matters in your kitchen today.</p></div>
        <button type="button" className="home-command-hint" onClick={() => window.dispatchEvent(new Event("cookfully:open-command"))} aria-label="Open quick search"><span>Search or jump to…</span><kbd>{commandShortcut}</kbd></button>
      </header>

      <div className="home-dashboard">
        <article className={`home-tonight${dinnerRecipe?.imageUrl ? " home-tonight--with-image" : ""}`} aria-labelledby="tonight-heading">
          <div className="home-tonight__art" aria-hidden="true">{dinnerRecipe ? <span className="home-tonight__photo"><RecipeMedia recipe={dinnerRecipe} loading="eager" /></span> : <span className="home-plate"><i className="home-plate__greens" /><i className="home-plate__main" /><i className="home-plate__sauce" /></span>}</div>
          <div className="home-tonight__copy">
            <p className="eyebrow" id="tonight-heading">{focusTimeLabel}</p>
            {plan.isPending || recipes.isPending ? <><h2>Checking tonight’s plan…</h2><p>Opening this week.</p></> : plan.isError && !planMissing ? <><h2>Your plan is out of reach</h2><p>Recipes are still safe.</p><Button variant="secondary" onClick={() => void plan.refetch()}>Try again</Button></> : dinner ? <>
              <h2>{dinner.recipeTitle}</h2>
              {heroFacts.length ? <ul className="home-tonight__facts">{heroFacts.map((fact) => <li key={fact}>{fact}</li>)}</ul> : null}
              {dinnerMatch?.availability === "full" ? <p className="home-tonight__availability">Everything you need is already in the pantry.</p> : dinnerMatch?.missingIngredients.length ? <p className="home-tonight__availability">{dinnerMatch.missingIngredients.length} {dinnerMatch.missingIngredients.length === 1 ? "ingredient" : "ingredients"} still needed. <Link to="/app/grocery">Check groceries</Link></p> : null}
              {dinner.recipeId ? <Button asChild><Link to={`/app/recipes/${dinner.recipeId}/cook`}><ChefHat aria-hidden="true" />Start cooking</Link></Button> : <Button asChild><Link to="/app/plan">Review dinner</Link></Button>}
            </> : readyRecipes.length ? <><h2>Plan today’s next meal</h2><p>Make one good decision now.</p><Button asChild><Link to={`/app/plan?date=${today}&slot=${focusSlot}`}><CalendarDays aria-hidden="true" />Plan {focusSlot === "dinner" ? "tonight" : focusSlot}</Link></Button></> : <><h2>Save your first recipe</h2><p>Start with a dish you already love.</p><Button asChild><Link to="/app/recipes/new">Add a recipe</Link></Button></>}
          </div>
        </article>

        <section className="home-week-card" aria-labelledby="home-week-heading">
          <div className="home-week-card__heading"><div><p className="eyebrow">This week</p><h2 id="home-week-heading">{mealHeadline(entries.length)}</h2></div><Link to="/app/plan" aria-label="Open full meal plan"><ArrowRight aria-hidden="true" /></Link></div>
          <div className="home-week-grid" aria-label={`${plannedDates.size} of 7 days have planned meals`}>{days.map((date) => <WeekDay key={date} date={date} entries={entriesByDate.get(date) ?? []} recipesById={recipesById} today={today} />)}</div>
          <div className="home-week-card__next"><span>Next up</span><strong>{dinner ? dinner.recipeTitle : "Nothing planned today"}</strong><Link to={`/app/plan?date=${today}&slot=${focusSlot}`}>{dinner ? "Review today" : "Plan today"} <ArrowRight aria-hidden="true" /></Link></div>
        </section>
      </div>

      <div className="home-priorities">
        <section className="home-use-soon" aria-labelledby="home-use-soon-heading">
          <div className="home-section-heading"><div><p className="eyebrow">Pantry</p><h2 id="home-use-soon-heading">Use soon</h2></div><Link to="/app/pantry">Open pantry <ArrowRight aria-hidden="true" /></Link></div>
          {pantry.isPending ? <Skeleton label="Checking pantry dates" lines={2} /> : pantry.isError ? <p className="muted">Pantry dates are out of reach right now.</p> : useSoon.length ? <ul className="home-use-soon__list">{useSoon.map((item) => <li key={item.id}><span className="home-use-soon__produce" aria-hidden="true">{item.displayName.slice(0, 1)}</span><span><strong>{item.displayName}</strong><small>{formatCookingNumber(item.quantity)} {item.unit}</small></span><em>{relativeUseBy(today, item.expiresOn!)}</em></li>)}</ul> : pantry.data?.length ? <div className="home-module-empty"><strong>No use-by dates yet</strong><p>Add a date to fresh food and Cookfully will bring it here before it gets forgotten.</p><Link to="/app/pantry">Add dates in Pantry</Link></div> : <div className="home-module-empty"><strong>Your shelf can help decide dinner</strong><p>Add a few things you already have. Rough quantities are enough.</p><Link to="/app/pantry">Add pantry items</Link></div>}
        </section>

        <nav className="home-quick-actions" aria-labelledby="home-quick-actions-heading">
          <p className="eyebrow">Keep moving</p><h2 id="home-quick-actions-heading">Quick actions</h2>
          <Link to={`/app/plan?date=${today}&slot=dinner`}><CalendarDays aria-hidden="true" /><span><strong>Plan tonight</strong><small>Put one meal on the calendar</small></span><ArrowRight aria-hidden="true" /></Link>
          <Link to="/app/recipes/new"><Plus aria-hidden="true" /><span><strong>Add a recipe</strong><small>Save a dish you want to make</small></span><ArrowRight aria-hidden="true" /></Link>
          <Link to="/app/grocery?add=1"><ShoppingBasket aria-hidden="true" /><span><strong>Add a grocery item</strong><small>Remember something for the next shop</small></span><ArrowRight aria-hidden="true" /></Link>
        </nav>
      </div>

      <section className="home-for-you" aria-labelledby="home-for-you-heading">
        <div className="home-section-heading"><div><h2 id="home-for-you-heading">Cook next</h2></div><Link to="/app/recipes">Browse recipes <ArrowRight aria-hidden="true" /></Link></div>
        {recipes.isPending ? <Skeleton label="Finding recipe ideas" lines={3} /> : recommendations.length ? <div className="home-for-you__grid">{recommendations.map((recipe, index) => <article className={`home-recommendation${index === 0 ? " is-featured" : ""}`} key={recipe.id}><Link to={`/app/recipes/${recipe.id}`} aria-label={recipe.title}><span className="home-recommendation__media"><RecipeMedia recipe={recipe} /></span><span className="home-recommendation__body"><span className="home-recommendation__reason">{recommendationReason(recipe, matchesByRecipeId.get(recipe.id), plannedRecipeIds)}</span><h3>{recipe.title}</h3><small>Makes {servingLabel(recipe.yieldQuantity, recipe.yieldUnit)}</small><RecipeMetadata recipe={recipe} compact /></span></Link></article>)}</div> : <div className="home-module-empty"><strong>Ideas need a recipe box</strong><p>Save a few dishes and Cookfully will surface useful next choices here.</p><Link to="/app/recipes/new">Add a recipe</Link></div>}
      </section>

      <div className="home-lower-grid">
        <section className="home-recent" aria-labelledby="home-recent-heading">
          <div className="home-section-heading"><div><p className="eyebrow">Recipe box</p><h2 id="home-recent-heading">Recently saved</h2></div><Link to="/app/recipes">See all <ArrowRight aria-hidden="true" /></Link></div>
          {recipes.isPending ? <Skeleton label="Loading recent recipes" lines={2} /> : recipes.isError ? <ErrorRecovery title="Recent recipes could not be loaded" onRetry={() => void recipes.refetch()} /> : recentRecipes.length ? <div className="home-recent__grid">{recentRecipes.map((recipe) => <article className="home-recent-recipe" key={recipe.id}><Link to={`/app/recipes/${recipe.id}`} aria-label={recipe.title} viewTransition><span className="home-recent-recipe__media"><RecipeMedia recipe={recipe} /></span><span><h3>{recipe.title}</h3><small>{recipe.mealRoles[0] ?? `Makes ${formatCookingNumber(recipe.yieldQuantity)}`}</small><RecipeMetadata recipe={recipe} compact /></span></Link></article>)}</div> : <p className="home-recent__empty">Recipes you save will settle here. <Link to="/app/recipes/new">Add your first recipe</Link>.</p>}
        </section>

        <section className="home-grocery" aria-labelledby="home-grocery-heading">
          <div className="home-grocery__mark" aria-hidden="true"><PackageOpen /></div><p className="eyebrow">Grocery</p><h2 id="home-grocery-heading">{groceryHeading}</h2>
          {grocery.isPending || grocery.data?.status === "generating" ? <p>Your latest plan is being turned into a shopping list.</p> : groceryUnavailable ? <p>Nothing was changed. Try opening the list again when the connection settles.</p> : groceryMissing || !grocery.data ? <p>Build a list from this week’s meals, or start with one thing you need.</p> : activeGroceryItems.length ? <><ul>{activeGroceryItems.slice(0, 3).map((item) => <li key={item.id}>{item.displayName}</li>)}{activeGroceryItems.length > 3 ? <li>+{activeGroceryItems.length - 3} more</li> : null}</ul><p>{purchasedCount ? `${purchasedCount} already in your basket.` : grocery.data.status === "dirty" ? "Your plan changed; refresh the list before shopping." : "Ready for your next shop."}</p></> : <p>{purchasedCount ? `${purchasedCount} picked up. Nice work.` : "Your current list is clear."}</p>}
          <Link to="/app/grocery">{groceryMissing ? "Start a grocery list" : "Open grocery list"} <ArrowRight aria-hidden="true" /></Link>
        </section>
      </div>
    </main>
  );
}
