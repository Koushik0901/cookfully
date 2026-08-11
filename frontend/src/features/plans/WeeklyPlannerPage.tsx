import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Button, EmptyState, ErrorRecovery, Field, PageHeader, Skeleton } from "../../components";
import { ApiProblem } from "../recipes/api";
import { planningApi } from "./api";
import { addDays, longDate, todayInTimezone, weekDates, weekStartFor } from "./dates";
import { DayTabs } from "./DayTabs";
import { MacroSummary } from "./MacroSummary";
import { MealPlanEntry } from "./MealPlanEntry";

const SLOTS = ["breakfast", "lunch", "dinner", "snack"];

function multiplyDecimal(value: string, multiplier: bigint): string {
  const [whole, fraction = ""] = value.split(".");
  const scale = fraction.length;
  const product = BigInt(`${whole}${fraction}`) * multiplier;
  if (!scale) return product.toString();
  const padded = product.toString().padStart(scale + 1, "0");
  return `${padded.slice(0, -scale)}.${padded.slice(-scale)}`;
}

export function WeeklyPlannerPage() {
  const queryClient = useQueryClient();
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const goal = useQuery({ queryKey: ["current-goal"], queryFn: () => planningApi.goal(), retry: false });
  const [weekStart, setWeekStart] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [recipeId, setRecipeId] = useState("");
  const [addMessage, setAddMessage] = useState("");

  useEffect(() => {
    if (!preferences.data || weekStart) return;
    const start = weekStartFor(todayInTimezone(preferences.data.timezone), preferences.data.weekStartsOn);
    setWeekStart(start);
    setSelectedDate(start);
  }, [preferences.data, weekStart]);

  const plan = useQuery({ queryKey: ["meal-plan", weekStart], queryFn: () => planningApi.plan(weekStart), enabled: Boolean(weekStart), retry: false });
  const recipes = useQuery({ queryKey: ["planning-recipes"], queryFn: planningApi.recipes });
  const dates = useMemo(() => weekStart ? weekDates(weekStart) : [], [weekStart]);
  const planMissing = plan.error instanceof ApiProblem && plan.error.status === 404;
  const goalMissing = goal.error instanceof ApiProblem && goal.error.status === 404;
  const add = useMutation({
    mutationFn: (mealSlot: string) => {
      if (!recipeId) throw new Error("Select a recipe first.");
      return planningApi.addEntry(weekStart, { localDate: selectedDate, mealSlot, recipeId, servings: "1.000", refreshNutrition: false });
    },
    onSuccess: () => { setAddMessage("Recipe added to plan"); void queryClient.invalidateQueries({ queryKey: ["meal-plan", weekStart] }); },
  });

  function changeWeek(days: number) {
    const next = addDays(weekStart, days);
    setWeekStart(next);
    setSelectedDate(next);
    setAddMessage("");
  }

  if (preferences.isPending || goal.isPending || !weekStart) return <Skeleton label="Loading weekly planner" lines={8} />;
  if (preferences.isError) return <ErrorRecovery title="Calendar preferences could not be loaded" onRetry={() => void preferences.refetch()} />;
  if (goal.isError && !goalMissing) return <ErrorRecovery title="Goal could not be loaded" onRetry={() => void goal.refetch()} />;
  if (goalMissing || !goal.data) return <main className="page-shell"><EmptyState title="Set your daily targets first" description="A goal anchors daily and weekly nutrition budgets." action={<Button asChild><Link to="/app/goals">Configure targets</Link></Button>} /></main>;
  if (plan.isError && !planMissing) return <ErrorRecovery title="Weekly plan could not be loaded" onRetry={() => void plan.refetch()} />;
  const entries = plan.data?.entries ?? [];
  const selectedEntries = entries.filter((entry) => entry.localDate === selectedDate);
  const totals = plan.data?.dayTotals ?? {};

  return (
    <main className="page-shell">
      <PageHeader eyebrow={preferences.data.timezone} title={`Week of ${longDate(weekStart)}`} description="Immutable entry snapshots keep displayed totals honest even when recipes change later." actions={<><Button className="button--secondary" onClick={() => changeWeek(-7)}>Previous week</Button><Button className="button--secondary" onClick={() => changeWeek(7)}>Next week</Button><Button asChild><Link to="/app/goals">Edit targets</Link></Button></>} />
      <DayTabs dates={dates} selected={selectedDate} onSelect={setSelectedDate} totals={totals} />
      <MacroSummary label={`${longDate(selectedDate)} budget`} total={totals[selectedDate]} target={goal.data} />
      <section className="planner-day" aria-label={`Plan for ${longDate(selectedDate)}`}>
        {SLOTS.map((slot) => <section className="meal-slot" key={slot}><div className="section-heading"><h2>{slot[0].toUpperCase()}{slot.slice(1)}</h2><div className="add-entry"><Field label={`${slot[0].toUpperCase()}${slot.slice(1)} recipe to add`}><select className="input" value={recipeId} onChange={(event) => setRecipeId(event.target.value)}><option value="">Select recipe</option>{recipes.data?.items.filter((recipe) => recipe.status !== "archived" && !["failed", "pending"].includes(recipe.nutritionState)).map((recipe) => <option key={recipe.id} value={recipe.id}>{recipe.title}</option>)}</select></Field><Button onClick={() => add.mutate(slot)} disabled={!recipeId || add.isPending}>Add to {slot}</Button></div></div>{selectedEntries.filter((entry) => entry.mealSlot === slot).length ? <div className="entry-list">{selectedEntries.filter((entry) => entry.mealSlot === slot).sort((a, b) => a.position - b.position).map((entry) => <MealPlanEntry key={entry.id} entry={entry} weekStart={weekStart} />)}</div> : <p className="muted">No entries in this meal.</p>}</section>)}
      </section>
      {add.error instanceof Error ? <p className="error-text" role="alert">{add.error.message}</p> : null}
      {addMessage ? <p className="success-text" role="status">{addMessage}</p> : null}
      <MacroSummary label="Weekly total" total={plan.data?.weekTotal} target={{ ...goal.data, caloriesKcal: multiplyDecimal(goal.data.caloriesKcal, 7n), proteinG: multiplyDecimal(goal.data.proteinG, 7n), carbohydrateG: multiplyDecimal(goal.data.carbohydrateG, 7n), fatG: multiplyDecimal(goal.data.fatG, 7n) }} />
    </main>
  );
}
