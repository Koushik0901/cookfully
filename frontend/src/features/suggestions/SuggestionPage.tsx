import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, CalendarDays, CalendarRange, Check, ChefHat, ShieldCheck, SlidersHorizontal, Soup, UtensilsCrossed } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { Button, DecimalInput, ErrorRecovery, Field, KitchenCompanion, PageHeader, Select, Skeleton } from "../../components";
import { RecipeFallbackArt } from "../../components/cookfully/RecipeFallbackArt";
import { RecipeMetadata } from "../recipes/RecipeMetadata";
import { Checkbox } from "@/components/ui/checkbox";
import { todayInTimezone, weekStartFor } from "../plans/dates";
import { suggestionsApi } from "./api";
import type { PeriodTotal, SuggestionMacroValues, SuggestionResult } from "./types";
import { useAcceptSuggestion } from "./useAcceptSuggestion";

const ACTIVE_STATUSES = new Set(["queued", "running"]);
const MEAL_SLOTS = ["breakfast", "lunch", "dinner", "snack"];
const DEFAULT_TOLERANCES: SuggestionMacroValues = {
  caloriesKcal: "100.000000",
  proteinG: "10.000000",
  carbohydrateG: "15.000000",
  fatG: "5.000000",
};

const SCOPES = [
  { value: "meal", title: "One meal", description: "Fill a single breakfast, lunch, dinner, or snack.", Icon: UtensilsCrossed },
  { value: "day", title: "A full day", description: "Build a balanced day around your nutrition guide.", Icon: CalendarDays },
  { value: "week", title: "Fill my week", description: "Find a practical set of meals with sensible repetition.", Icon: CalendarRange },
] as const;

type MacroTotalsValue = Pick<PeriodTotal, "caloriesKcal" | "proteinG" | "carbohydrateG" | "fatG">;

function MacroTotals({ total, testId }: { total: MacroTotalsValue | undefined | null; testId?: string }) {
  if (!total) return <p className="muted">No projected total is available.</p>;
  return (
    <dl className="suggestion-macros" data-testid={testId}>
      <div className="macro macro--calories"><dt>Calories</dt><dd>{total.caloriesKcal ?? "—"} kcal</dd></div>
      <div className="macro macro--protein"><dt>Protein</dt><dd>{total.proteinG ?? "—"} g protein</dd></div>
      <div className="macro macro--carbs"><dt>Carbohydrates</dt><dd>{total.carbohydrateG ?? "—"} g carbs</dd></div>
      <div className="macro macro--fat"><dt>Fat</dt><dd>{total.fatG ?? "—"} g fat</dd></div>
    </dl>
  );
}

function ResultExplanation({ result }: { result: SuggestionResult }) {
  return (
    <section className="suggestion-explanation" aria-labelledby="ranking-title">
      <h2 id="ranking-title">A practical fit, explained</h2>
      <p>Cookfully first protects the preferences you set, then looks for a useful nutrition fit with repetition that feels realistic for the week.</p>
      <details className="suggestion-ranking-details">
        <summary>See planning details</summary>
        <p>When there are several possible plans, Cookfully consistently favors fewer unmet preferences, then balances energy and protein ahead of other nutrition targets, then avoids unnecessary repetition.</p>
        <dl className="objective-grid">
          <div><dt>Unmet preferences</dt><dd>{result.unmetConstraintCount ?? "—"}</dd></div>
          <div><dt>Plan score</dt><dd>{result.objectiveScore ?? "—"}</dd></div>
          <div><dt>Energy distance</dt><dd>{result.distanceComponents?.calories ?? "—"}</dd></div>
          <div><dt>Protein distance</dt><dd>{result.distanceComponents?.protein ?? "—"}</dd></div>
        </dl>
      </details>
    </section>
  );
}

function primaryTotal(result: SuggestionResult): PeriodTotal | undefined | null {
  if (result.request.scope === "week") return result.projectedWeekTotal;
  const localDate = result.request.localDate;
  return localDate ? result.projectedDayTotals?.[localDate] : undefined;
}

function humanizeConstraint(value: string) {
  const words = value.replaceAll("_", " ").trim();
  return words ? `${words[0].toUpperCase()}${words.slice(1)}` : value;
}

export function SuggestionPage() {
  const [searchParams] = useSearchParams();
  const requestedScope = searchParams.get("scope");
  const initialScope = requestedScope === "meal" || requestedScope === "week" ? requestedScope : "day";
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: suggestionsApi.preferences });
  const recipes = useQuery({ queryKey: ["suggestion-recipes"], queryFn: suggestionsApi.recipes });
  const [scope, setScope] = useState<"meal" | "day" | "week">(initialScope);
  const [weekStart, setWeekStart] = useState(searchParams.get("weekStart") ?? "");
  const [localDate, setLocalDate] = useState(searchParams.get("localDate") ?? "");
  const [mealSlot, setMealSlot] = useState(searchParams.get("mealSlot") ?? "breakfast");
  const [tolerances, setTolerances] = useState(DEFAULT_TOLERANCES);
  const [maxRepetitions, setMaxRepetitions] = useState(3);
  const [requiredIds, setRequiredIds] = useState<string[]>([]);
  const [excludedIds, setExcludedIds] = useState<string[]>([]);
  const [recipeRuleQuery, setRecipeRuleQuery] = useState("");
  const [suggestionId, setSuggestionId] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    if (!preferences.data) return;
    const today = todayInTimezone(preferences.data.timezone);
    setLocalDate((current) => current || today);
    setWeekStart((current) => current || weekStartFor(today, preferences.data.weekStartsOn));
  }, [preferences.data]);

  const create = useMutation({
    mutationFn: () => suggestionsApi.create({
      scope,
      weekStart,
      localDate: scope === "week" ? null : localDate,
      mealSlot: scope === "meal" ? mealSlot : null,
      tolerances,
      excludedRecipeIds: excludedIds,
      requiredRecipeIds: requiredIds,
      maxRecipeRepetitions: maxRepetitions,
    }),
    onSuccess: (accepted) => {
      setSelectedIds([]);
      setSuggestionId(accepted.resourceId ?? "");
    },
  });
  const resultQuery = useQuery({
    queryKey: ["suggestion", suggestionId],
    queryFn: () => suggestionsApi.get(suggestionId),
    enabled: Boolean(suggestionId),
    refetchInterval: (query) => ACTIVE_STATUSES.has(query.state.data?.status ?? "") ? 2_000 : false,
  });
  const result = resultQuery.data;
  useEffect(() => {
    if (!result || !["feasible", "infeasible"].includes(result.status)) return;
    setSelectedIds(result.items.filter((item) => !item.accepted).map((item) => item.id));
  }, [result]);
  const accept = useAcceptSuggestion(result, selectedIds);
  const availableRecipes = useMemo(
    () => recipes.data?.items.filter((recipe) => recipe.status !== "archived" && !["failed", "pending"].includes(recipe.nutritionState)) ?? [],
    [recipes.data],
  );
  const visibleRuleRecipes = useMemo(() => {
    const query = recipeRuleQuery.trim().toLocaleLowerCase();
    return availableRecipes
      .filter((recipe) => requiredIds.includes(recipe.id) || excludedIds.includes(recipe.id) || !query || recipe.title.toLocaleLowerCase().includes(query))
      .sort((a, b) => Number(requiredIds.includes(b.id) || excludedIds.includes(b.id)) - Number(requiredIds.includes(a.id) || excludedIds.includes(a.id)))
      .slice(0, query ? 30 : 8);
  }, [availableRecipes, excludedIds, recipeRuleQuery, requiredIds]);

  function updateTolerance(key: keyof SuggestionMacroValues, value: string) {
    setTolerances((current) => ({ ...current, [key]: value }));
  }

  function toggleRequired(recipeId: string, checked: boolean) {
    setRequiredIds((current) => checked ? [...current, recipeId] : current.filter((id) => id !== recipeId));
    if (checked) setExcludedIds((current) => current.filter((id) => id !== recipeId));
  }

  function toggleExcluded(recipeId: string, checked: boolean) {
    setExcludedIds((current) => checked ? [...current, recipeId] : current.filter((id) => id !== recipeId));
    if (checked) setRequiredIds((current) => current.filter((id) => id !== recipeId));
  }

  function freshSuggestion() {
    accept.reset();
    setSuggestionId("");
    setSelectedIds([]);
  }

  if (preferences.isPending || recipes.isPending || !weekStart) return <Skeleton label="Loading suggestion workspace" lines={8} />;
  if (preferences.isError) return <ErrorRecovery title="Calendar preferences could not be loaded" onRetry={() => void preferences.refetch()} />;
  if (recipes.isError) return <ErrorRecovery title="Recipes could not be loaded" onRetry={() => void recipes.refetch()} />;

  const previewTotal = result ? primaryTotal(result) : undefined;
  return (
    <main className="page-shell suggestions-page">
      <PageHeader eyebrow="Cookfully ideas" title="What would make your plan easier?" description="Choose the gap you want to fill. Cookfully will look through your recipes and find a nutritionally useful fit." />

      <section className="suggestion-form" aria-labelledby="idea-size-title">
        <div className="suggestion-form__heading"><div><p className="eyebrow">Start with one choice</p><h2 id="idea-size-title">How much help do you want?</h2></div><p>{availableRecipes.length} {availableRecipes.length === 1 ? "recipe is" : "recipes are"} ready to consider.</p></div>
        <div className="suggestion-scope-options" role="radiogroup" aria-label="Suggestion scope">
          {SCOPES.map(({ value, title, description, Icon }) => <label className={`suggestion-scope ${scope === value ? "suggestion-scope--selected" : ""}`} key={value}><input type="radio" name="suggestion-scope" value={value} checked={scope === value} onChange={() => setScope(value)} /><Icon aria-hidden="true" /><span><strong>{title}</strong><small>{description}</small></span>{scope === value ? <Check className="choice-check" aria-hidden="true" /> : null}</label>)}
        </div>
        <div className="suggestion-when">
          {scope === "week" ? <Field label="Planning week"><input className="input data-value" type="date" value={weekStart} onChange={(event) => setWeekStart(event.target.value)} /></Field> : <Field label="Day to plan"><input className="input data-value" type="date" value={localDate} onChange={(event) => setLocalDate(event.target.value)} /></Field>}
          {scope === "meal" ? <Field label="Meal"><Select value={mealSlot} onChange={(event) => setMealSlot(event.target.value)}>{MEAL_SLOTS.map((slot) => <option key={slot} value={slot}>{slot[0].toUpperCase()}{slot.slice(1)}</option>)}</Select></Field> : null}
          <div className="suggestion-when__promise"><ShieldCheck aria-hidden="true" /><span><strong>Nothing changes yet</strong><small>You’ll preview every meal before it joins your plan.</small></span></div>
        </div>
        <details className="suggestion-tune"><summary><SlidersHorizontal aria-hidden="true" /><span><strong>Fine-tune the nutrition fit</strong><small>Optional tolerances and repetition limits</small></span></summary><div className="suggestion-tune__body"><Field label="Maximum recipe repetitions"><input className="input data-value" type="number" min="1" max="21" value={maxRepetitions} onChange={(event) => setMaxRepetitions(Number(event.target.value))} /></Field><fieldset className="tolerance-grid"><legend>How close should the plan get?</legend>
          <Field label="Calories tolerance"><DecimalInput value={tolerances.caloriesKcal} onValueChange={(value) => updateTolerance("caloriesKcal", value)} /></Field>
          <Field label="Protein tolerance"><DecimalInput value={tolerances.proteinG} onValueChange={(value) => updateTolerance("proteinG", value)} /></Field>
          <Field label="Carbohydrate tolerance"><DecimalInput value={tolerances.carbohydrateG} onValueChange={(value) => updateTolerance("carbohydrateG", value)} /></Field>
          <Field label="Fat tolerance"><DecimalInput value={tolerances.fatG} onValueChange={(value) => updateTolerance("fatG", value)} /></Field>
        </fieldset></div></details>
        <details className="suggestion-tune"><summary><ChefHat aria-hidden="true" /><span><strong>Use or avoid specific recipes</strong><small>Optional rules that Cookfully will always respect</small></span></summary><fieldset className="recipe-constraints suggestion-tune__body"><legend>Recipe preferences</legend>
          {availableRecipes.length ? <><Field label="Find a recipe"><input className="input" type="search" value={recipeRuleQuery} onChange={(event) => setRecipeRuleQuery(event.target.value)} placeholder="Search your recipe library" /></Field><div className="recipe-rule-list">{visibleRuleRecipes.map((recipe) => <div className="recipe-rule" key={recipe.id}><strong>{recipe.title}</strong><label><Checkbox checked={requiredIds.includes(recipe.id)} onCheckedChange={(checked) => toggleRequired(recipe.id, checked === true)} /> Use <span className="visually-hidden">{recipe.title}</span></label><label><Checkbox checked={excludedIds.includes(recipe.id)} onCheckedChange={(checked) => toggleExcluded(recipe.id, checked === true)} /> Avoid <span className="visually-hidden">{recipe.title}</span></label></div>)}</div>{recipeRuleQuery && !visibleRuleRecipes.length ? <p className="muted">No recipes match that search.</p> : null}{availableRecipes.length > visibleRuleRecipes.length ? <p className="muted">Showing {visibleRuleRecipes.length} of {availableRecipes.length}. Search to find another recipe.</p> : null}</> : <p className="muted">No nutrition-ready recipes are available.</p>}
        </fieldset></details>
        <div className="suggestion-create"><div><Soup aria-hidden="true" /><p><strong>Ready to find a good fit</strong><span>Uses your saved recipes, current plan, and nutrition guide.</span></p></div><Button disabled={create.isPending || !availableRecipes.length} onClick={() => create.mutate()}>{create.isPending ? "Finding ideas…" : "Find meal ideas"}</Button></div>
        {create.error instanceof Error ? <p className="error-text" role="alert">{create.error.message}</p> : null}
      </section>

      {(create.isPending || (result && ACTIVE_STATUSES.has(result.status))) ? <section className="job-panel" role="status" aria-live="polite"><h2>Building suggestions</h2><p>{result?.status === "running" ? "Optimizing exact constraints…" : "Queued for optimization…"}</p><progress aria-label="Suggestion progress" /></section> : null}
      {resultQuery.isError ? <ErrorRecovery title="Suggestion progress could not be loaded" onRetry={() => void resultQuery.refetch()} /> : null}
      {result?.status === "failed" || result?.status === "expired" ? <ErrorRecovery title={result.status === "expired" ? "Suggestion expired" : "Suggestion failed"} description={result.failureCode ?? "Create a fresh suggestion from the current plan."} actionLabel="Create a fresh suggestion" onRetry={freshSuggestion} /> : null}

      {result && ["feasible", "infeasible"].includes(result.status) ? <section className="suggestion-results" aria-labelledby="result-title">
        <div className={`result-banner result-banner--${result.status}`}><p className="eyebrow">Your ideas are ready</p><h2 id="result-title">{result.status === "feasible" ? "Here’s a plan that fits" : "We couldn’t fit every preference"}</h2><p>{result.status === "feasible" ? "Your nutrition guide and recipe preferences are all respected." : `${result.unmetConstraintCount ?? result.missedConstraints.length} preferences need a little more flexibility.`}</p></div>
        {result.missedConstraints.length ? <section className="blockers" aria-labelledby="blocker-title"><h2 id="blocker-title">Preferences to loosen</h2><ul>{result.missedConstraints.map((constraint) => <li key={constraint}>{humanizeConstraint(constraint)}</li>)}</ul></section> : null}
        {result.items.length ? <section className="suggested-dishes" aria-labelledby="items-title"><div className="section-heading"><div><p className="eyebrow">Cookfully’s pick</p><h2 id="items-title">Meals for your plan</h2></div><p>Keep the dishes you want. Everything stays a preview until you add it.</p></div><div className="suggestion-items">{result.items.map((item) => {
          const recipe = availableRecipes.find((candidate) => candidate.id === item.recipeId);
          const mealName = item.mealSlot[0].toUpperCase() + item.mealSlot.slice(1);
          return <article className="suggestion-item" key={item.id}>
            <Link className="suggestion-item__media" to={`/app/recipes/${item.recipeId}`} aria-label={`Open ${item.recipeTitle}`}>{recipe?.imageUrl ? <img src={recipe.imageUrl} alt="" loading="lazy" decoding="async" /> : <RecipeFallbackArt title={item.recipeTitle} />}</Link>
            <label className="suggestion-item__select"><Checkbox checked={selectedIds.includes(item.id)} disabled={item.accepted} aria-label={`Accept ${item.recipeTitle}`} onCheckedChange={(checked) => setSelectedIds((current) => checked === true ? [...current, item.id] : current.filter((id) => id !== item.id))} /><span className="visually-hidden">Add {item.recipeTitle}</span></label>
            <div className="suggestion-item__body"><p className="eyebrow">{mealName} · {item.localDate}</p><h3><Link to={`/app/recipes/${item.recipeId}`}>{item.recipeTitle}</Link></h3><p className="suggestion-item__servings">{Number(item.servings)} {Number(item.servings) === 1 ? "serving" : "servings"}</p><RecipeMetadata recipe={recipe ?? { title: item.recipeTitle, prepMinutes: null, cookMinutes: null, nutrition: item.projectedNutrition }} compact /><p className="suggestion-item__reason">A practical fit for this {item.mealSlot}, balanced against the rest of your plan.</p><MacroTotals total={item.projectedNutrition} /><Link className="suggestion-item__open" to={`/app/recipes/${item.recipeId}`}>See recipe <ArrowRight aria-hidden="true" /></Link></div>
          </article>;
        })}</div></section> : null}
        <details className="suggestion-preview"><summary>Nutrition fit for this {result.request.scope === "week" ? "week" : "day"}</summary><div aria-label={`Projected ${result.request.scope === "week" ? "week" : "day"} total`}><MacroTotals total={previewTotal} testId="preview-primary-total" /></div></details>
        <details className="structured-review"><summary>Why this fits your plan</summary><ResultExplanation result={result} /></details>
        {result.status === "feasible" && result.items.length ? <div className="accept-panel"><Button disabled={!selectedIds.length || accept.isPending} onClick={() => accept.mutate()}>Accept {selectedIds.length} selected {selectedIds.length === 1 ? "item" : "items"}</Button><p className="muted">Only checked entries are added. Your plan version is verified before any change.</p></div> : null}
      </section> : null}

      {accept.isSuccess && accept.acceptedTotal ? <section className="success-panel suggestion-success" role="status" data-testid="success-panel"><KitchenCompanion moment="success" size="md" className="suggestion-success__companion" /><div className="suggestion-success__copy"><p className="eyebrow">Plan updated</p><h2>{selectedIds.length} {selectedIds.length === 1 ? "meal is" : "meals are"} ready in your plan</h2><p>Cookfully added the selected dishes exactly where you previewed them.</p><div className="actions"><Button asChild><Link to="/app/plan">View meal plan</Link></Button><Button variant="secondary" asChild><Link to="/app/grocery">Review groceries</Link></Button></div></div><div className="suggestion-success__evidence" data-testid="accepted-primary-total"><p>Accepted {result?.request.scope === "week" ? "week" : "day"} total: {accept.acceptedTotal.caloriesKcal} kcal, {accept.acceptedTotal.proteinG} g protein — matches the preview.</p></div></section> : null}
      {accept.conflict ? <ErrorRecovery title="Plan changed before acceptance" description="Nothing was accepted. Create a fresh suggestion from the current plan so the preview and accepted totals remain identical." actionLabel="Create a fresh suggestion" onRetry={freshSuggestion} /> : null}
      {accept.error instanceof Error && !accept.conflict ? <p className="error-text" role="alert">{accept.error.message}</p> : null}
    </main>
  );
}
