import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CalendarDays, ChevronLeft, ChevronRight, CookingPot, HeartPulse, LayoutGrid, Plus, Sparkles } from "lucide-react";

import { Button, ErrorRecovery, PageHeader, PageState, Skeleton, TabList } from "../../components";
import { ApiProblem } from "../recipes/api";
import { planningApi } from "./api";
import { addDays, longDate, todayInTimezone, weekDates, weekStartFor } from "./dates";
import { DayTabs } from "./DayTabs";
import { ExpiringBanner } from "./ExpiringBanner";
import { MacroSummary } from "./MacroSummary";
import { NutritionPulse } from "./NutritionPulse";
import { PrepOverview } from "./PrepOverview";
import { RecipePickerSheet } from "./RecipePickerSheet";
import { DayMealBoard } from "./DayMealBoard";
import { WeekOverview } from "./WeekOverview";
import type { MealPlan, MealPlanEntry as PlannedEntry } from "./types";
import { isRecipeReadyToPlan } from "../recipes/recipeEligibility";
import { useExpiringPantry } from "./useExpiringPantry";

const SLOTS = ["breakfast", "lunch", "dinner", "snack"];
type PlannerView = "week" | "day" | "prep";

function useMobileLayout() {
  const [mobile, setMobile] = useState(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(max-width: 767.98px)").matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 767.98px)");
    const update = () => setMobile(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return mobile;
}

export function WeeklyPlannerPage() {
  const queryClient = useQueryClient();
  const isMobile = useMobileLayout();
  const [searchParams] = useSearchParams();
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const [weekStart, setWeekStart] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerSlot, setPickerSlot] = useState(searchParams.get("slot") ?? "dinner");
  const [addMessage, setAddMessage] = useState("");
  const [view, setView] = useState<PlannerView>(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(max-width: 767.98px)").matches ? "day" : "week");
  const [shortcutHandled, setShortcutHandled] = useState(false);
  const goal = useQuery({ queryKey: ["current-goal", weekStart], queryFn: () => planningApi.goal(weekStart), enabled: Boolean(weekStart), retry: false });

  useEffect(() => {
    if (isMobile) setView("day");
  }, [isMobile]);

  useEffect(() => {
    if (!preferences.data || weekStart) return;
    const start = weekStartFor(todayInTimezone(preferences.data.timezone), preferences.data.weekStartsOn);
    const today = todayInTimezone(preferences.data.timezone);
    setWeekStart(start);
    const requestedDate = searchParams.get("date");
    setSelectedDate(requestedDate && weekDates(start).includes(requestedDate) ? requestedDate : weekDates(start).includes(today) ? today : start);
  }, [preferences.data, searchParams, weekStart]);

  useEffect(() => {
    const requestedSlot = searchParams.get("slot");
    if (!weekStart || !selectedDate || !requestedSlot || shortcutHandled || !SLOTS.includes(requestedSlot)) return;
    setPickerSlot(requestedSlot);
    setView("day");
    if (selectedDate >= todayInTimezone(preferences.data!.timezone)) setPickerOpen(true);
    else setAddMessage("Past days are read-only. Choose today or a future day.");
    setShortcutHandled(true);
  }, [preferences.data, searchParams, selectedDate, shortcutHandled, weekStart]);

  const plan = useQuery({ queryKey: ["meal-plan", weekStart], queryFn: () => planningApi.plan(weekStart), enabled: Boolean(weekStart), retry: false });
  const recipes = useQuery({ queryKey: ["planning-recipes"], queryFn: ({ signal }) => planningApi.recipes("", signal) });
  const dates = useMemo(() => weekStart ? weekDates(weekStart) : [], [weekStart]);
  const todayForBanner = preferences.data ? todayInTimezone(preferences.data.timezone) : "";
  const { expiring: expiringPantry } = useExpiringPantry(3, todayForBanner);
  const planMissing = plan.error instanceof ApiProblem && plan.error.status === 404;
  const goalMissing = goal.error instanceof ApiProblem && goal.error.status === 404;
  const add = useMutation({
    mutationFn: ({ recipeId, mealSlot }: { recipeId: string; mealSlot: string }) => {
      if (selectedDate < todayInTimezone(preferences.data!.timezone)) throw new Error("Past days are read-only. Choose today or a future day.");
      return planningApi.addEntry(weekStart, { localDate: selectedDate, mealSlot, recipeId, servings: "1.000", refreshNutrition: false });
    },
    onSuccess: () => { setAddMessage("Meal added to your plan."); setPickerOpen(false); void queryClient.invalidateQueries({ queryKey: ["meal-plan", weekStart] }); },
    onError: (error) => { setAddMessage(error instanceof Error ? error.message : "Past days are read-only. Choose today or a future day."); setPickerOpen(true); },
  });
  const move = useMutation({
    mutationFn: ({ entry, date, slot, position }: { entry: PlannedEntry; date: string; slot: string; position: number }) => {
      if (!entry.recipeId) throw new Error("This historical meal no longer has a recipe to move.");
      return planningApi.updateEntry(entry.id, entry.version, {
        localDate: date,
        mealSlot: slot,
        recipeId: entry.recipeId,
        servings: entry.servings,
        position,
        refreshNutrition: false,
      });
    },
    onMutate: async ({ entry, date, slot, position }) => {
      await queryClient.cancelQueries({ queryKey: ["meal-plan", weekStart] });
      const previous = queryClient.getQueryData<MealPlan>(["meal-plan", weekStart]);
      if (previous) {
        queryClient.setQueryData<MealPlan>(["meal-plan", weekStart], {
          ...previous,
          entries: previous.entries.map((item) => item.id === entry.id ? { ...item, localDate: date, mealSlot: slot, position } : item),
        });
      }
      setAddMessage("");
      return { previous };
    },
    onError: (error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(["meal-plan", weekStart], context.previous);
      setAddMessage(error instanceof ApiProblem && error.status === 409 ? "The plan changed elsewhere, so the meal returned to its previous spot. Reload and try again." : "That meal could not be moved, so it returned to its previous spot.");
    },
    onSuccess: (saved) => {
      setAddMessage(`${saved.recipeTitle} moved to ${saved.mealSlot}.`);
      void queryClient.invalidateQueries({ queryKey: ["meal-plan", weekStart] });
    },
  });
  const copy = useMutation({
    mutationFn: ({ entry, date, slot, position }: { entry: PlannedEntry; date: string; slot: string; position: number }) => {
      if (!entry.recipeId) throw new Error("This historical meal no longer has a recipe to copy.");
      return planningApi.addEntry(weekStart, {
        localDate: date,
        mealSlot: slot,
        recipeId: entry.recipeId,
        servings: entry.servings,
        position,
        refreshNutrition: false,
      });
    },
    onMutate: () => setAddMessage(""),
    onError: () => setAddMessage("That meal could not be copied. The original is still in its usual spot."),
    onSuccess: (saved) => {
      setAddMessage(`${saved.recipeTitle} copied to ${saved.mealSlot}.`);
      void queryClient.invalidateQueries({ queryKey: ["meal-plan", weekStart] });
    },
  });
  const swap = useMutation({
    mutationFn: ({ source, target }: { source: PlannedEntry; target: PlannedEntry }) => planningApi.swapEntries(source.id, source.version, target.id, target.version),
    onMutate: async ({ source, target }) => {
      await queryClient.cancelQueries({ queryKey: ["meal-plan", weekStart] });
      const previous = queryClient.getQueryData<MealPlan>(["meal-plan", weekStart]);
      if (previous) {
        queryClient.setQueryData<MealPlan>(["meal-plan", weekStart], {
          ...previous,
          entries: previous.entries.map((item) => item.id === source.id ? { ...item, localDate: target.localDate, mealSlot: target.mealSlot, position: target.position } : item.id === target.id ? { ...item, localDate: source.localDate, mealSlot: source.mealSlot, position: source.position } : item),
        });
      }
      setAddMessage("");
      return { previous };
    },
    onError: (error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(["meal-plan", weekStart], context.previous);
      setAddMessage(error instanceof ApiProblem && error.status === 409 ? "The plan changed elsewhere, so the meals stayed where they were. Reload and try again." : "Those meals could not be swapped, so they stayed where they were.");
    },
    onSuccess: ({ source }) => {
      setAddMessage(`${source.recipeTitle} swapped places.`);
      void queryClient.invalidateQueries({ queryKey: ["meal-plan", weekStart] });
    },
  });
  const remove = useMutation({
    mutationFn: (entry: PlannedEntry) => planningApi.removeEntry(entry.id, entry.version),
    onMutate: async (entry) => {
      await queryClient.cancelQueries({ queryKey: ["meal-plan", weekStart] });
      const previous = queryClient.getQueryData<MealPlan>(["meal-plan", weekStart]);
      if (previous) queryClient.setQueryData<MealPlan>(["meal-plan", weekStart], { ...previous, entries: previous.entries.filter((item) => item.id !== entry.id) });
      setAddMessage("");
      return { previous };
    },
    onError: (_error, _entry, context) => {
      if (context?.previous) queryClient.setQueryData(["meal-plan", weekStart], context.previous);
      setAddMessage("That meal could not be deleted. It stayed on your plan.");
    },
    onSuccess: (_value, entry) => {
      setAddMessage(`${entry.recipeTitle} removed from your plan.`);
      void queryClient.invalidateQueries({ queryKey: ["meal-plan", weekStart] });
    },
  });

  function changeWeek(days: number) {
    const next = addDays(weekStart, days);
    const today = todayInTimezone(preferences.data!.timezone);
    setWeekStart(next);
    setSelectedDate(weekDates(next).includes(today) ? today : next);
    setAddMessage("");
  }

  if (preferences.isPending || goal.isPending || !weekStart) return <PageState><Skeleton label="Loading weekly planner" lines={8} /></PageState>;
  if (preferences.isError) return <PageState><ErrorRecovery title="Calendar preferences could not be loaded" onRetry={() => void preferences.refetch()} /></PageState>;
  if (goal.isError && !goalMissing) return <PageState><ErrorRecovery title="Goal could not be loaded" onRetry={() => void goal.refetch()} /></PageState>;
  if (plan.isError && !planMissing) return <PageState><ErrorRecovery title="Weekly plan could not be loaded" onRetry={() => void plan.refetch()} /></PageState>;
  const entries = plan.data?.entries ?? [];
  const today = todayInTimezone(preferences.data.timezone);
  const selectedDateIsPast = Boolean(selectedDate && selectedDate < today);
  const selectedEntries = entries.filter((entry) => entry.localDate === selectedDate);
  const openSlots = SLOTS.filter((slot) => !selectedEntries.some((entry) => entry.mealSlot === slot));
  const totals = plan.data?.dayTotals ?? {};
  const availableRecipes = recipes.data?.items.filter(isRecipeReadyToPlan) ?? [];
  // Keep historical/stale recipe media available for cards already on the plan;
  // only the picker is restricted to recipes that are safe to add.
  const recipesById = new Map((recipes.data?.items ?? []).map((recipe) => [recipe.id, recipe]));
  const plannedDays = new Set(entries.map((entry) => entry.localDate)).size;
  const entryCounts = Object.fromEntries(dates.map((date) => [date, entries.filter((entry) => entry.localDate === date).length]));
  const selectAdjacentDay = (days: number) => {
    const candidate = addDays(selectedDate, days);
    if (dates.includes(candidate)) setSelectedDate(candidate);
    else changeWeek(days < 0 ? -7 : 7);
    setAddMessage("");
  };

  return (
    <main className="page-shell planner-page">
      {isMobile ? <header className="planner-mobile-top"><div><p className="eyebrow">This week</p><h1>{longDate(selectedDate)}</h1><p>{selectedEntries.length ? `${selectedEntries.length} meals planned` : "A clear day, ready to plan."}</p></div><div className="planner-mobile-top__actions"><button type="button" aria-label="Previous day" onClick={() => selectAdjacentDay(-1)}><ChevronLeft aria-hidden="true" /></button><button type="button" aria-label="Next day" onClick={() => selectAdjacentDay(1)}><ChevronRight aria-hidden="true" /></button><button type="button" aria-label="Plan dinner" onClick={() => { setPickerSlot("dinner"); setPickerOpen(true); }}><Plus aria-hidden="true" /></button></div></header> : <PageHeader eyebrow="Meal plan" title={`Week of ${longDate(weekStart)}`} description="Choose the food, balance the week, then turn the plan into one practical prep list." actions={<div className="week-stepper" aria-label="Change planning week"><Button variant="secondary" aria-label="Previous week" onClick={() => changeWeek(-7)}><ChevronLeft aria-hidden="true" />Previous</Button><Button variant="secondary" aria-label="Next week" onClick={() => changeWeek(7)}>Next<ChevronRight aria-hidden="true" /></Button></div>} />}
      <div className="planner-toolbar">
        <TabList className="planner-views" label="Planning views">
           <button id="planner-tab-week" role="tab" aria-controls="planner-panel-week" aria-selected={view === "week"} tabIndex={view === "week" ? 0 : -1} onClick={() => setView("week")}><LayoutGrid aria-hidden="true" />Week</button>
           <button id="planner-tab-day" role="tab" aria-controls="planner-panel-day" aria-selected={view === "day"} tabIndex={view === "day" ? 0 : -1} onClick={() => setView("day")}><CalendarDays aria-hidden="true" />Day</button>
           <button id="planner-tab-prep" role="tab" aria-controls="planner-panel-prep" aria-selected={view === "prep"} tabIndex={view === "prep" ? 0 : -1} onClick={() => setView("prep")}><CookingPot aria-hidden="true" />Prep</button>
        </TabList>
        {goal.data ? <Button asChild><Link to={`/app/suggestions?scope=week&weekStart=${weekStart}`}><Sparkles aria-hidden="true" />Help fill this week</Link></Button> : <Button variant="secondary" asChild><Link to="/app/goals"><HeartPulse aria-hidden="true" />Add nutrition guide</Link></Button>}
      </div>

        {view === "week" ? <section id="planner-panel-week" role="tabpanel" aria-labelledby="planner-tab-week">
          {addMessage ? <p className={move.isError || copy.isError || swap.isError || remove.isError ? "error-text" : "success-text"} role={move.isError || copy.isError || swap.isError || remove.isError ? "alert" : "status"}>{addMessage}</p> : null}
          <ExpiringBanner pantry={expiringPantry} plan={plan.data ?? { entries: [] }} today={todayForBanner} />
          <WeekOverview
           dates={dates}
           entries={entries}
           recipesById={recipesById}
           selectedDate={selectedDate}
           today={today}
           copyPending={copy.isPending}
           swapPending={swap.isPending}
           deletePending={remove.isPending}
           onOpenDay={(date) => { setSelectedDate(date); setAddMessage(""); setView("day"); }}
           onAdd={(date, slot) => { setSelectedDate(date); setPickerSlot(slot); setAddMessage(""); setPickerOpen(true); }}
           onMove={(entry, date, slot, position) => move.mutate({ entry, date, slot, position })}
           onCopy={(entry, date, slot, position) => copy.mutate({ entry, date, slot, position })}
           onSwap={(source, target) => swap.mutate({ source, target })}
           onDelete={(entry) => remove.mutate(entry)}
         />
         {goal.data ? <NutritionPulse total={plan.data?.weekTotal} target={goal.data} plannedDays={plannedDays} /> : null}
       </section> : null}

       {view === "day" ? <section id="planner-panel-day" role="tabpanel" aria-labelledby="planner-tab-day">
         <DayTabs dates={dates} selected={selectedDate} onSelect={(date) => { setSelectedDate(date); setAddMessage(""); }} totals={totals} entryCounts={entryCounts} today={today} />
        <div className={`plan-workspace${goal.data ? "" : " plan-workspace--single"}`}>
        <section className="planner-day" aria-label={`Plan for ${longDate(selectedDate)}`}>
          <div className="planner-day__heading"><div><p className="eyebrow">Selected day</p><h2>{longDate(selectedDate)}</h2></div><span>{selectedEntries.length} {selectedEntries.length === 1 ? "meal" : "meals"}</span></div>
          {selectedDateIsPast ? <div className="planner-day__readonly" role="status"><strong>Past day</strong><span>This day has already passed. You can review it, but new changes start today.</span></div> : null}
          {addMessage ? <p className={`planner-day__feedback ${move.isError || copy.isError || swap.isError || remove.isError || add.isError ? "error-text" : "success-text"}`} role={move.isError || copy.isError || swap.isError || remove.isError || add.isError ? "alert" : "status"}>{addMessage}</p> : null}
          <DayMealBoard
            date={selectedDate}
            slots={SLOTS.map((slot) => ({ slot, label: slot[0].toUpperCase() + slot.slice(1), entries: selectedEntries.filter((entry) => entry.mealSlot === slot).sort((a, b) => a.position - b.position) }))}
            weekStart={weekStart}
            recipesById={recipesById}
            readOnly={selectedDateIsPast}
            onMove={(entry, targetSlot, position) => move.mutate({ entry, date: selectedDate, slot: targetSlot, position })}
            onSwap={(source, target) => swap.mutate({ source, target })}
            renderEmpty={(slot, readOnly) => { const label = slot[0].toUpperCase() + slot.slice(1); return readOnly ? <div className="meal-slot__past" aria-label={`${label} is in the past`}>Past · no changes</div> : <div className="meal-slot__empty meal-slot__empty--quiet"><Button variant="secondary" aria-label={`Add a recipe to ${label}`} onClick={() => { add.reset(); setPickerSlot(slot); setAddMessage(""); setPickerOpen(true); }}><Plus aria-hidden="true" />Add a recipe</Button></div>; }}
          />
           {goal.data && openSlots.length && !selectedDateIsPast ? <div className="planner-day__gap-action"><div><strong>{openSlots.length} open meal {openSlots.length === 1 ? "spot" : "spots"}</strong><span>Let Cookfully suggest a practical fit for the gaps.</span></div><Link to={`/app/suggestions?scope=day&localDate=${selectedDate}`}><Sparkles aria-hidden="true" />Suggest meals for open spots</Link></div> : null}
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
