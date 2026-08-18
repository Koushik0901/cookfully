import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarDays, ChevronLeft, ChevronRight, CookingPot, HeartPulse, LayoutGrid, Plus, Sparkles } from "lucide-react";

import { Button, ErrorRecovery, PageHeader, Skeleton } from "../../components";
import { ApiProblem } from "../recipes/api";
import { planningApi } from "./api";
import { addDays, longDate, todayInTimezone, weekDates, weekStartFor } from "./dates";
import { DayTabs } from "./DayTabs";
import { MacroSummary } from "./MacroSummary";
import { MealPlanEntry } from "./MealPlanEntry";
import { NutritionPulse } from "./NutritionPulse";
import { PrepOverview } from "./PrepOverview";
import { RecipePickerSheet } from "./RecipePickerSheet";
import { WeekOverview } from "./WeekOverview";

const SLOTS = ["breakfast", "lunch", "dinner", "snack"];
type PlannerView = "week" | "day" | "prep";

export function WeeklyPlannerPage() {
  const queryClient = useQueryClient();
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const goal = useQuery({ queryKey: ["current-goal"], queryFn: () => planningApi.goal(), retry: false });
  const [weekStart, setWeekStart] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerSlot, setPickerSlot] = useState("dinner");
  const [addMessage, setAddMessage] = useState("");
  const [view, setView] = useState<PlannerView>("week");

  useEffect(() => {
    if (!preferences.data || weekStart) return;
    const start = weekStartFor(todayInTimezone(preferences.data.timezone), preferences.data.weekStartsOn);
    const today = todayInTimezone(preferences.data.timezone);
    setWeekStart(start);
    setSelectedDate(weekDates(start).includes(today) ? today : start);
  }, [preferences.data, weekStart]);

  const plan = useQuery({ queryKey: ["meal-plan", weekStart], queryFn: () => planningApi.plan(weekStart), enabled: Boolean(weekStart), retry: false });
  const recipes = useQuery({ queryKey: ["planning-recipes"], queryFn: planningApi.recipes });
  const dates = useMemo(() => weekStart ? weekDates(weekStart) : [], [weekStart]);
  const planMissing = plan.error instanceof ApiProblem && plan.error.status === 404;
  const goalMissing = goal.error instanceof ApiProblem && goal.error.status === 404;
  const add = useMutation({
    mutationFn: ({ recipeId, mealSlot }: { recipeId: string; mealSlot: string }) => {
      return planningApi.addEntry(weekStart, { localDate: selectedDate, mealSlot, recipeId, servings: "1.000", refreshNutrition: false });
    },
    onSuccess: () => { setAddMessage("Meal added to your plan."); setPickerOpen(false); void queryClient.invalidateQueries({ queryKey: ["meal-plan", weekStart] }); },
  });

  function changeWeek(days: number) {
    const next = addDays(weekStart, days);
    const today = todayInTimezone(preferences.data!.timezone);
    setWeekStart(next);
    setSelectedDate(weekDates(next).includes(today) ? today : next);
    setAddMessage("");
  }

  if (preferences.isPending || goal.isPending || !weekStart) return <Skeleton label="Loading weekly planner" lines={8} />;
  if (preferences.isError) return <ErrorRecovery title="Calendar preferences could not be loaded" onRetry={() => void preferences.refetch()} />;
  if (goal.isError && !goalMissing) return <ErrorRecovery title="Goal could not be loaded" onRetry={() => void goal.refetch()} />;
  if (plan.isError && !planMissing) return <ErrorRecovery title="Weekly plan could not be loaded" onRetry={() => void plan.refetch()} />;
  const entries = plan.data?.entries ?? [];
  const selectedEntries = entries.filter((entry) => entry.localDate === selectedDate);
  const openSlots = SLOTS.filter((slot) => !selectedEntries.some((entry) => entry.mealSlot === slot));
  const totals = plan.data?.dayTotals ?? {};
  const availableRecipes = recipes.data?.items.filter((recipe) => recipe.status !== "archived" && !["failed", "pending", "stale"].includes(recipe.nutritionState)) ?? [];
  const recipesById = new Map(availableRecipes.map((recipe) => [recipe.id, recipe]));
  const plannedDays = new Set(entries.map((entry) => entry.localDate)).size;
  const entryCounts = Object.fromEntries(dates.map((date) => [date, entries.filter((entry) => entry.localDate === date).length]));

  return (
    <main className="page-shell planner-page">
      <PageHeader eyebrow="Meal plan" title={`Week of ${longDate(weekStart)}`} description="Choose the food, balance the week, then turn the plan into one practical prep list." actions={<div className="week-stepper" aria-label="Change planning week"><Button variant="secondary" aria-label="Previous week" onClick={() => changeWeek(-7)}><ChevronLeft aria-hidden="true" />Previous</Button><Button variant="secondary" aria-label="Next week" onClick={() => changeWeek(7)}>Next<ChevronRight aria-hidden="true" /></Button></div>} />
      <div className="planner-toolbar">
        <div className="planner-views" role="tablist" aria-label="Planning views">
           <button id="planner-tab-week" role="tab" aria-controls="planner-panel-week" aria-selected={view === "week"} onClick={() => setView("week")}><LayoutGrid aria-hidden="true" />Week</button>
           <button id="planner-tab-day" role="tab" aria-controls="planner-panel-day" aria-selected={view === "day"} onClick={() => setView("day")}><CalendarDays aria-hidden="true" />Day</button>
           <button id="planner-tab-prep" role="tab" aria-controls="planner-panel-prep" aria-selected={view === "prep"} onClick={() => setView("prep")}><CookingPot aria-hidden="true" />Prep</button>
        </div>
        {goal.data ? <Button asChild><Link to={`/app/suggestions?scope=week&weekStart=${weekStart}`}><Sparkles aria-hidden="true" />Help fill this week</Link></Button> : <Button variant="secondary" asChild><Link to="/app/goals"><HeartPulse aria-hidden="true" />Add nutrition guide</Link></Button>}
      </div>

       {view === "week" ? <section id="planner-panel-week" role="tabpanel" aria-labelledby="planner-tab-week">
         <WeekOverview dates={dates} entries={entries} recipesById={recipesById} selectedDate={selectedDate} onOpenDay={(date) => { setSelectedDate(date); setAddMessage(""); setView("day"); }} />
         {goal.data ? <NutritionPulse total={plan.data?.weekTotal} target={goal.data} plannedDays={plannedDays} /> : null}
       </section> : null}

       {view === "day" ? <section id="planner-panel-day" role="tabpanel" aria-labelledby="planner-tab-day">
         <DayTabs dates={dates} selected={selectedDate} onSelect={(date) => { setSelectedDate(date); setAddMessage(""); }} totals={totals} entryCounts={entryCounts} />
        <div className={`plan-workspace${goal.data ? "" : " plan-workspace--single"}`}>
        <section className="planner-day" aria-label={`Plan for ${longDate(selectedDate)}`}>
          <div className="planner-day__heading"><div><p className="eyebrow">Selected day</p><h2>{longDate(selectedDate)}</h2></div><span>{selectedEntries.length} {selectedEntries.length === 1 ? "meal" : "meals"}</span></div>
          {addMessage ? <p className="planner-day__feedback success-text" role="status">{addMessage}</p> : null}
          {SLOTS.map((slot) => {
            const slotEntries = selectedEntries.filter((entry) => entry.mealSlot === slot).sort((a, b) => a.position - b.position);
            const slotLabel = slot[0].toUpperCase() + slot.slice(1);
             return <section className="meal-slot" key={slot}><div className="section-heading"><h3>{slotLabel}</h3><span>{slotEntries.length ? `${slotEntries.length} planned` : "Open"}</span></div>{slotEntries.length ? <div className="entry-list">{slotEntries.map((entry) => <MealPlanEntry key={entry.id} entry={entry} weekStart={weekStart} recipe={entry.recipeId ? recipesById.get(entry.recipeId) : undefined} />)}</div> : <div className="meal-slot__empty"><div><strong>Nothing planned yet</strong><span>{goal.data ? "Choose a recipe you know, or ask Cookfully for a useful fit." : "Choose any recipe. Nutrition guidance can be added later."}</span></div><div className="meal-slot__empty-actions"><Button variant="secondary" aria-label={`Add a recipe to ${slotLabel}`} onClick={() => { add.reset(); setPickerSlot(slot); setAddMessage(""); setPickerOpen(true); }}><Plus aria-hidden="true" />Add a recipe</Button></div></div>}</section>;
           })}
           {goal.data && openSlots.length ? <div className="planner-day__gap-action"><div><strong>{openSlots.length} open meal {openSlots.length === 1 ? "spot" : "spots"}</strong><span>Let Cookfully suggest a practical fit for the gaps.</span></div><Link to={`/app/suggestions?scope=day&localDate=${selectedDate}`}><Sparkles aria-hidden="true" />Suggest meals for open spots</Link></div> : null}
         </section>
        {goal.data ? <aside className="plan-nutrition" aria-label="Nutrition guidance">
          <div className="plan-nutrition__intro"><p className="eyebrow">Nutrition guidance</p><h2>Shape the day as you plan</h2><p>Use the remaining amounts to adjust servings or choose the next meal—not to grade the food you’ve already chosen.</p></div>
          <MacroSummary label="Nutrition balance" total={totals[selectedDate]} target={goal.data} />
          <Button variant="ghost" asChild><Link to="/app/goals">Adjust nutrition targets</Link></Button>
        </aside> : null}
        </div>
       </section> : null}

       {view === "prep" ? <section id="planner-panel-prep" role="tabpanel" aria-labelledby="planner-tab-prep"><PrepOverview entries={entries} recipesById={recipesById} groceryStatus={plan.data?.groceryStatus} /></section> : null}
      <RecipePickerSheet open={pickerOpen} onOpenChange={setPickerOpen} recipes={availableRecipes} mealSlot={pickerSlot} dateLabel={longDate(selectedDate)} pendingRecipeId={add.isPending ? add.variables?.recipeId : undefined} error={add.error instanceof Error ? add.error.message : undefined} loading={recipes.isPending} unavailableRecipeCount={Math.max(0, (recipes.data?.items.length ?? 0) - availableRecipes.length)} libraryError={recipes.error instanceof Error ? recipes.error.message : undefined} onRetry={() => void recipes.refetch()} onChoose={(chosenRecipeId) => add.mutate({ recipeId: chosenRecipeId, mealSlot: pickerSlot })} />
    </main>
  );
}
