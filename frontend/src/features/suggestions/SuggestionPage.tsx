import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { Button, DecimalInput, ErrorRecovery, Field, PageHeader, Skeleton } from "../../components";
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

function MacroTotals({ total, testId }: { total: PeriodTotal | undefined | null; testId?: string }) {
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
      <h2 id="ranking-title">Why this result ranks first</h2>
      <p>
        Results minimize the fewest unmet constraints first, then weighted macro distance
        (calories 4, protein 3, carbohydrates 1, fat 1, repetition 2, required recipes 5),
        then fewer entries, then ordered recipe IDs. The same inputs therefore produce the same ranking.
      </p>
      <dl className="objective-grid">
        <div><dt>Unmet constraints</dt><dd>{result.unmetConstraintCount ?? "—"}</dd></div>
        <div><dt>Objective score</dt><dd>{result.objectiveScore ?? "—"}</dd></div>
        <div><dt>Calorie distance</dt><dd>{result.distanceComponents?.calories ?? "—"}</dd></div>
        <div><dt>Protein distance</dt><dd>{result.distanceComponents?.protein ?? "—"}</dd></div>
      </dl>
    </section>
  );
}

function primaryTotal(result: SuggestionResult): PeriodTotal | undefined | null {
  if (result.request.scope === "week") return result.projectedWeekTotal;
  const localDate = result.request.localDate;
  return localDate ? result.projectedDayTotals?.[localDate] : undefined;
}

export function SuggestionPage() {
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: suggestionsApi.preferences });
  const recipes = useQuery({ queryKey: ["suggestion-recipes"], queryFn: suggestionsApi.recipes });
  const [scope, setScope] = useState<"meal" | "day" | "week">("day");
  const [weekStart, setWeekStart] = useState("");
  const [localDate, setLocalDate] = useState("");
  const [mealSlot, setMealSlot] = useState("breakfast");
  const [tolerances, setTolerances] = useState(DEFAULT_TOLERANCES);
  const [maxRepetitions, setMaxRepetitions] = useState(3);
  const [requiredIds, setRequiredIds] = useState<string[]>([]);
  const [excludedIds, setExcludedIds] = useState<string[]>([]);
  const [suggestionId, setSuggestionId] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  useEffect(() => {
    if (!preferences.data || weekStart) return;
    const today = todayInTimezone(preferences.data.timezone);
    setLocalDate(today);
    setWeekStart(weekStartFor(today, preferences.data.weekStartsOn));
  }, [preferences.data, weekStart]);

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
    <main className="page-shell">
      <PageHeader eyebrow="Deterministic planning assistant" title="Meal suggestions" description="Set hard recipe constraints and macro tolerances, then preview exact changes before accepting any item." />
      <p className="advisory" role="note">Planning aid only—not medical advice.</p>

      <section className="suggestion-form" aria-labelledby="constraint-title">
        <div className="section-heading"><div><h2 id="constraint-title">Constraints</h2><p className="muted">Exclusions and unavailable recipes are never relaxed.</p></div></div>
        <div className="suggestion-fields">
          <Field label="Suggestion scope"><select className="input" value={scope} onChange={(event) => setScope(event.target.value as typeof scope)}><option value="meal">Meal</option><option value="day">Day</option><option value="week">Week</option></select></Field>
          <Field label="Week start"><input className="input data-value" type="date" value={weekStart} onChange={(event) => setWeekStart(event.target.value)} /></Field>
          {scope !== "week" ? <Field label="Local date"><input className="input data-value" type="date" value={localDate} onChange={(event) => setLocalDate(event.target.value)} /></Field> : null}
          {scope === "meal" ? <Field label="Meal slot"><select className="input" value={mealSlot} onChange={(event) => setMealSlot(event.target.value)}>{MEAL_SLOTS.map((slot) => <option key={slot} value={slot}>{slot[0].toUpperCase()}{slot.slice(1)}</option>)}</select></Field> : null}
          <Field label="Maximum recipe repetitions"><input className="input data-value" type="number" min="1" max="21" value={maxRepetitions} onChange={(event) => setMaxRepetitions(Number(event.target.value))} /></Field>
        </div>
        <details className="disclosure"><summary>Macro tolerances</summary><fieldset className="tolerance-grid"><legend>Allowed macro distance</legend>
          <Field label="Calories tolerance"><DecimalInput value={tolerances.caloriesKcal} onValueChange={(value) => updateTolerance("caloriesKcal", value)} /></Field>
          <Field label="Protein tolerance"><DecimalInput value={tolerances.proteinG} onValueChange={(value) => updateTolerance("proteinG", value)} /></Field>
          <Field label="Carbohydrate tolerance"><DecimalInput value={tolerances.carbohydrateG} onValueChange={(value) => updateTolerance("carbohydrateG", value)} /></Field>
          <Field label="Fat tolerance"><DecimalInput value={tolerances.fatG} onValueChange={(value) => updateTolerance("fatG", value)} /></Field>
        </fieldset></details>
        <details className="disclosure"><summary>Recipe rules</summary><fieldset className="recipe-constraints"><legend>Recipe rules</legend>
          {availableRecipes.length ? availableRecipes.map((recipe) => <div className="recipe-rule" key={recipe.id}><strong>{recipe.title}</strong><label><input type="checkbox" checked={requiredIds.includes(recipe.id)} onChange={(event) => toggleRequired(recipe.id, event.target.checked)} /> Require <span className="visually-hidden">{recipe.title}</span></label><label><input type="checkbox" checked={excludedIds.includes(recipe.id)} onChange={(event) => toggleExcluded(recipe.id, event.target.checked)} /> Exclude <span className="visually-hidden">{recipe.title}</span></label></div>) : <p className="muted">No nutrition-ready recipes are available.</p>}
        </fieldset></details>
        <div className="actions"><Button disabled={create.isPending || !availableRecipes.length} onClick={() => create.mutate()}>Generate suggestions</Button></div>
        {create.error instanceof Error ? <p className="error-text" role="alert">{create.error.message}</p> : null}
      </section>

      {(create.isPending || (result && ACTIVE_STATUSES.has(result.status))) ? <section className="job-panel" role="status" aria-live="polite"><h2>Building suggestions</h2><p>{result?.status === "running" ? "Optimizing exact constraints…" : "Queued for optimization…"}</p><progress aria-label="Suggestion progress" /></section> : null}
      {resultQuery.isError ? <ErrorRecovery title="Suggestion progress could not be loaded" onRetry={() => void resultQuery.refetch()} /> : null}
      {result?.status === "failed" || result?.status === "expired" ? <ErrorRecovery title={result.status === "expired" ? "Suggestion expired" : "Suggestion failed"} description={result.failureCode ?? "Create a fresh suggestion from the current plan."} actionLabel="Create a fresh suggestion" onRetry={freshSuggestion} /> : null}

      {result && ["feasible", "infeasible"].includes(result.status) ? <section className="suggestion-results" aria-labelledby="result-title">
        <div className={`result-banner result-banner--${result.status}`}><p className="eyebrow">Solver result</p><h2 id="result-title">{result.status === "feasible" ? "Feasible within your tolerances" : "No feasible result"}</h2><p>{result.status === "feasible" ? "All hard constraints were preserved." : `${result.unmetConstraintCount ?? result.missedConstraints.length} constraints could not be met without violating your rules.`}</p></div>
        {result.missedConstraints.length ? <section className="blockers" aria-labelledby="blocker-title"><h2 id="blocker-title">Constraints to review</h2><ul>{result.missedConstraints.map((constraint) => <li key={constraint}>{constraint[0].toUpperCase()}{constraint.slice(1)}</li>)}</ul></section> : null}
        <ResultExplanation result={result} />
        <section className="suggestion-preview" aria-labelledby="preview-title"><h2 id="preview-title">Projected {result.request.scope === "week" ? "week" : "day"} total</h2><MacroTotals total={previewTotal} testId="preview-primary-total" /></section>
        {result.items.length ? <section aria-labelledby="items-title"><h2 id="items-title">Suggested plan entries</h2><div className="suggestion-items">{result.items.map((item) => <article className="suggestion-item" key={item.id}><label className="suggestion-item__select"><input type="checkbox" checked={selectedIds.includes(item.id)} disabled={item.accepted} aria-label={`Accept ${item.recipeTitle}`} onChange={(event) => setSelectedIds((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} /><span><strong>{item.recipeTitle}</strong><small>{item.localDate} · {item.mealSlot} · {item.servings} servings</small></span></label><MacroTotals total={item.projectedNutrition} /></article>)}</div></section> : null}
        {result.status === "feasible" && result.items.length ? <div className="accept-panel"><Button disabled={!selectedIds.length || accept.isPending} onClick={() => accept.mutate()}>Accept {selectedIds.length} selected {selectedIds.length === 1 ? "item" : "items"}</Button><p className="muted">Only checked entries are added. Your plan version is verified before any change.</p></div> : null}
      </section> : null}

      {accept.isSuccess && accept.acceptedTotal ? <section className="success-panel" role="status"><h2>Accepted {selectedIds.length} {selectedIds.length === 1 ? "item" : "items"}</h2><div data-testid="accepted-primary-total"><p>Accepted {result?.request.scope === "week" ? "week" : "day"} total: {accept.acceptedTotal.caloriesKcal} kcal, {accept.acceptedTotal.proteinG} g protein — matches the preview.</p></div></section> : null}
      {accept.conflict ? <ErrorRecovery title="Plan changed before acceptance" description="Nothing was accepted. Create a fresh suggestion from the current plan so the preview and accepted totals remain identical." actionLabel="Create a fresh suggestion" onRetry={freshSuggestion} /> : null}
      {accept.error instanceof Error && !accept.conflict ? <p className="error-text" role="alert">{accept.error.message}</p> : null}
    </main>
  );
}
