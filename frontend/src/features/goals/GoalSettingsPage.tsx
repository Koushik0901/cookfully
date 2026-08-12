import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarDays, Check, Gauge, Leaf, PencilLine, Sprout, TrendingDown, TrendingUp } from "lucide-react";

import { Button, DecimalInput, ErrorRecovery, Field, PageHeader, Skeleton } from "../../components";
import { ApiProblem } from "../recipes/api";
import { planningApi } from "../plans/api";
import { todayInTimezone } from "../plans/dates";
import type { MealTarget, UserGoalWrite } from "../plans/types";
import { formatCookingNumber } from "../recipes/formatCooking";

const MEAL_SLOTS = ["breakfast", "lunch", "dinner", "snack"] as const;
const TIMEZONES = ["UTC", "America/Vancouver", "America/New_York", "Europe/London"];
const decimal = /^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/;

type TargetFields = Record<string, { caloriesKcal: string; proteinG: string; carbohydrateG: string; fatG: string }>;

const DIRECTIONS = [
  { value: "cut", title: "Eat a little lighter", description: "Create a measured energy deficit while keeping meals satisfying.", Icon: TrendingDown },
  { value: "maintain", title: "Stay steady", description: "Support everyday health and maintain your current direction.", Icon: Leaf },
  { value: "bulk", title: "Fuel growth", description: "Plan enough energy and protein for growth, training, or recovery.", Icon: TrendingUp },
] as const;

function emptyTargets(): TargetFields {
  return Object.fromEntries(MEAL_SLOTS.map((slot) => [slot, { caloriesKcal: "", proteinG: "", carbohydrateG: "", fatG: "" }]));
}

export function GoalSettingsPage() {
  const queryClient = useQueryClient();
  const preferences = useQuery({ queryKey: ["owner-preferences"], queryFn: planningApi.preferences });
  const currentGoal = useQuery({ queryKey: ["current-goal"], queryFn: () => planningApi.goal(), retry: false });
  const [timezone, setTimezone] = useState("UTC");
  const [weekStartsOn, setWeekStartsOn] = useState("1");
  const [mode, setMode] = useState<UserGoalWrite["mode"]>("maintain");
  const [maintenanceKcal, setMaintenanceKcal] = useState("");
  const [caloriesKcal, setCaloriesKcal] = useState("");
  const [proteinG, setProteinG] = useState("");
  const [carbohydrateG, setCarbohydrateG] = useState("");
  const [fatG, setFatG] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [effectiveTo, setEffectiveTo] = useState("");
  const [mealTargets, setMealTargets] = useState<TargetFields>(emptyTargets);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [editingTargets, setEditingTargets] = useState(false);
  const [changed, setChanged] = useState(false);

  useEffect(() => {
    if (!preferences.data) return;
    setTimezone(preferences.data.timezone);
    setWeekStartsOn(String(preferences.data.weekStartsOn));
  }, [preferences.data]);

  useEffect(() => {
    if (!currentGoal.data) return;
    const value = currentGoal.data;
    setMode(value.mode);
    setMaintenanceKcal(value.maintenanceKcal);
    setCaloriesKcal(value.caloriesKcal);
    setProteinG(value.proteinG);
    setCarbohydrateG(value.carbohydrateG);
    setFatG(value.fatG);
    setEffectiveFrom(value.effectiveFrom);
    setEffectiveTo(value.effectiveTo ?? "");
    const targets = emptyTargets();
    for (const target of value.mealTargets ?? []) {
      targets[target.mealSlot] = {
        caloriesKcal: target.caloriesKcal ?? "",
        proteinG: target.proteinG ?? "",
        carbohydrateG: target.carbohydrateG ?? "",
        fatG: target.fatG ?? "",
      };
    }
    setMealTargets(targets);
    setChanged(false);
  }, [currentGoal.data]);

  useEffect(() => {
    if (currentGoal.data || effectiveFrom || !preferences.data) return;
    setEffectiveFrom(todayInTimezone(preferences.data.timezone));
  }, [preferences.data, currentGoal.data, effectiveFrom]);

  const save = useMutation({
    mutationFn: async (value: UserGoalWrite) => {
      if (!preferences.data) throw new Error("Preferences are unavailable.");
      if (timezone !== preferences.data.timezone || Number(weekStartsOn) !== preferences.data.weekStartsOn) {
        await planningApi.updatePreferences({ timezone, weekStartsOn: Number(weekStartsOn), version: preferences.data.version });
      }
      return planningApi.updateGoal(value, currentGoal.data?.version);
    },
    onSuccess: (value) => {
      queryClient.setQueryData(["current-goal"], value);
      void queryClient.invalidateQueries({ queryKey: ["owner-preferences"] });
      setSaved(true);
      setEditingTargets(false);
      setChanged(false);
    },
  });

  function markChanged() {
    setSaved(false);
    setChanged(true);
  }

  function mealValue(slot: string, field: keyof TargetFields[string], value: string) {
    markChanged();
    setMealTargets((current) => ({ ...current, [slot]: { ...current[slot], [field]: value } }));
  }

  function onCaloriesChange(value: string) {
    markChanged();
    setCaloriesKcal(value);
    if (!currentGoal.data && !maintenanceKcal) setMaintenanceKcal(value);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    const required = { maintenanceKcal, caloriesKcal, proteinG, carbohydrateG, fatG };
    const labels: Record<keyof typeof required, string> = { maintenanceKcal: "Maintenance calories", caloriesKcal: "Daily calories", proteinG: "Daily protein", carbohydrateG: "Daily carbohydrate", fatG: "Daily fat" };
    const next: Record<string, string> = {};
    for (const [field, value] of Object.entries(required) as [keyof typeof required, string][]) {
      if (!value) next[field] = `${labels[field]} is required.`;
      else if (!decimal.test(value) || (field === "maintenanceKcal" || field === "caloriesKcal") && Number(value) <= 0) next[field] = `${labels[field]} must be a valid positive decimal.`;
    }
    if (!effectiveFrom) next.effectiveFrom = "Effective from is required.";
    if (effectiveTo && effectiveTo < effectiveFrom) next.effectiveTo = "Effective to cannot precede effective from.";
    setErrors(next);
    if (Object.keys(next).length) return;
    const targets: MealTarget[] = MEAL_SLOTS.flatMap((slot) => {
      const item = mealTargets[slot];
      return Object.values(item).some(Boolean)
        ? [{ mealSlot: slot, caloriesKcal: item.caloriesKcal || null, proteinG: item.proteinG || null, carbohydrateG: item.carbohydrateG || null, fatG: item.fatG || null }]
        : [];
    });
    save.mutate({ mode, maintenanceKcal, caloriesKcal, proteinG, carbohydrateG, fatG, effectiveFrom, effectiveTo: effectiveTo || null, mealTargets: targets });
  }

  const goalMissing = currentGoal.error instanceof ApiProblem && currentGoal.error.status === 404;
  if (preferences.isPending || currentGoal.isPending) return <Skeleton label="Loading goal settings" lines={8} />;
  if (preferences.isError) return <ErrorRecovery title="Preferences could not be loaded" onRetry={() => void preferences.refetch()} />;
  if (currentGoal.isError && !goalMissing) return <ErrorRecovery title="Targets could not be loaded" onRetry={() => void currentGoal.refetch()} />;
  const showTargetInputs = !currentGoal.data || editingTargets;
  const showSaveAction = !currentGoal.data || editingTargets || changed;
  const macroEnergy = [proteinG, carbohydrateG, fatG, caloriesKcal].every((value) => decimal.test(value))
    ? Number(proteinG) * 4 + Number(carbohydrateG) * 4 + Number(fatG) * 9
    : null;
  const difference = macroEnergy == null ? null : macroEnergy - Number(caloriesKcal);

  return (
    <main className="page-shell">
      <PageHeader eyebrow="Your nutrition guide" title="Shape how Cookfully plans for you" description="Give Cookfully flexible daily guidance. It will use these numbers to shape meal plans—not to judge individual meals." actions={<Button className="button--secondary" asChild><Link to="/app/plan">Back to meal plan</Link></Button>} />
      <form className="goal-form" onSubmit={submit} noValidate>
        <section className="goal-direction" aria-labelledby="direction-title">
          <div className="goal-section-heading"><div><p className="eyebrow">Energy direction</p><h2 id="direction-title">How should energy support you?</h2></div><p>You can change this whenever life changes.</p></div>
          <p className="goal-direction__principle"><Leaf aria-hidden="true" /><span><strong>Balanced eating is always the baseline.</strong> This choice only tells Cookfully whether to plan a little below, around, or above your maintenance needs.</span></p>
          <div className="direction-options" role="radiogroup" aria-label="Goal mode">
            {DIRECTIONS.map(({ value, title, description, Icon }) => <label className={`direction-option ${mode === value ? "direction-option--selected" : ""}`} key={value}><input type="radio" name="goal-mode" value={value} checked={mode === value} onChange={() => { markChanged(); setMode(value); }} /><Icon aria-hidden="true" /><span><strong>{title}</strong><small>{description}</small></span>{mode === value ? <Check className="choice-check" aria-hidden="true" /> : null}</label>)}
          </div>
        </section>

        <section className="goal-targets" aria-labelledby="daily-guide-title">
          <div className="goal-section-heading"><div><p className="eyebrow">Then, the daily guide</p><h2 id="daily-guide-title">Nutrition to plan around</h2></div><div className="goal-targets__heading-side"><p>Useful targets for balancing a day and week—not pass/fail scores.</p>{!showTargetInputs ? <Button type="button" className="button--secondary" onClick={() => { setSaved(false); setEditingTargets(true); }}><PencilLine aria-hidden="true" />Adjust daily guide</Button> : null}</div></div>
          {showTargetInputs ? <div className="target-grid">
            <div className="target-field target-field--calories"><span className="target-field__icon"><Gauge aria-hidden="true" /></span><Field label="Daily calories" error={errors.caloriesKcal}><DecimalInput value={caloriesKcal} onInput={(event) => onCaloriesChange(event.currentTarget.value)} /></Field><span className="target-field__unit">kcal</span></div>
            <div className="target-field target-field--protein"><span className="target-field__dot" aria-hidden="true" /><Field label="Daily protein" error={errors.proteinG}><DecimalInput value={proteinG} onInput={(event) => { markChanged(); setProteinG(event.currentTarget.value); }} /></Field><span className="target-field__unit">grams</span></div>
            <div className="target-field target-field--carbs"><span className="target-field__dot" aria-hidden="true" /><Field label="Daily carbohydrate" error={errors.carbohydrateG}><DecimalInput value={carbohydrateG} onInput={(event) => { markChanged(); setCarbohydrateG(event.currentTarget.value); }} /></Field><span className="target-field__unit">grams</span></div>
            <div className="target-field target-field--fat"><span className="target-field__dot" aria-hidden="true" /><Field label="Daily fat" error={errors.fatG}><DecimalInput value={fatG} onInput={(event) => { markChanged(); setFatG(event.currentTarget.value); }} /></Field><span className="target-field__unit">grams</span></div>
          </div> : <dl className="goal-guide-summary" aria-label="Current daily nutrition guide">
            <div><dt>Energy</dt><dd>{formatCookingNumber(caloriesKcal, 0)} <small>kcal</small></dd></div>
            <div><dt><i className="nutrient-dot nutrient-dot--protein" aria-hidden="true" />Protein</dt><dd>{formatCookingNumber(proteinG, 1)} <small>g</small></dd></div>
            <div><dt><i className="nutrient-dot nutrient-dot--carbohydrate" aria-hidden="true" />Carbohydrate</dt><dd>{formatCookingNumber(carbohydrateG, 1)} <small>g</small></dd></div>
            <div><dt><i className="nutrient-dot nutrient-dot--fat" aria-hidden="true" />Fat</dt><dd>{formatCookingNumber(fatG, 1)} <small>g</small></dd></div>
          </dl>}
          {difference != null ? <div className="goal-balance-note"><Sprout aria-hidden="true" /><p>{Math.abs(difference) < 1 ? <>Your macro guide closely matches your daily energy target.</> : <>This guide adds up to about <strong>{formatCookingNumber(Math.abs(difference), 1)} kcal {difference < 0 ? "below" : "above"}</strong> daily energy. That can be intentional; adjust either value if you want them closer.</>}</p></div> : null}
        </section>

        <section className="goal-advanced" aria-label="Advanced goal settings">
          <details className="goal-disclosure"><summary><span><Gauge aria-hidden="true" /><span><strong>Energy baseline and dates</strong><small>Maintenance estimate and when this guide applies</small></span></span></summary><div className="form-grid goal-disclosure__content"><Field label="Maintenance calories" error={errors.maintenanceKcal}><DecimalInput value={maintenanceKcal} onInput={(event) => { markChanged(); setMaintenanceKcal(event.currentTarget.value); }} /></Field><Field label="Effective from" error={errors.effectiveFrom}><input className="input" type="date" value={effectiveFrom} onChange={(event) => { markChanged(); setEffectiveFrom(event.target.value); }} /></Field><Field label="Effective to (optional)" error={errors.effectiveTo}><input className="input" type="date" value={effectiveTo} onChange={(event) => { markChanged(); setEffectiveTo(event.target.value); }} /></Field></div></details>
          <details className="goal-disclosure"><summary><span><CalendarDays aria-hidden="true" /><span><strong>Calendar preferences</strong><small>Timezone and the first day of your planning week</small></span></span></summary><div className="form-grid goal-disclosure__content"><Field label="Timezone"><select className="input" value={timezone} onChange={(event) => { markChanged(); setTimezone(event.target.value); }}>{!TIMEZONES.includes(timezone) ? <option value={timezone}>{timezone}</option> : null}{TIMEZONES.map((value) => <option key={value} value={value}>{value}</option>)}</select></Field><Field label="Week starts on"><select className="input" value={weekStartsOn} onChange={(event) => { markChanged(); setWeekStartsOn(event.target.value); }}><option value="1">Monday</option><option value="7">Sunday</option><option value="6">Saturday</option></select></Field></div></details>
          <details className="goal-disclosure"><summary><span><Sprout aria-hidden="true" /><span><strong>Meal-by-meal targets</strong><small>Optional guidance for breakfast, lunch, dinner, or snacks</small></span></span></summary><div className="meal-targets goal-disclosure__content">{MEAL_SLOTS.map((slot) => <fieldset key={slot}><legend>{slot}</legend><div className="form-grid"><Field label={`${slot[0].toUpperCase()}${slot.slice(1)} calories (optional)`}><DecimalInput value={mealTargets[slot].caloriesKcal} onInput={(event) => mealValue(slot, "caloriesKcal", event.currentTarget.value)} /></Field><Field label={`${slot[0].toUpperCase()}${slot.slice(1)} protein (optional)`}><DecimalInput value={mealTargets[slot].proteinG} onInput={(event) => mealValue(slot, "proteinG", event.currentTarget.value)} /></Field><Field label={`${slot[0].toUpperCase()}${slot.slice(1)} carbohydrate (optional)`}><DecimalInput value={mealTargets[slot].carbohydrateG} onInput={(event) => mealValue(slot, "carbohydrateG", event.currentTarget.value)} /></Field><Field label={`${slot[0].toUpperCase()}${slot.slice(1)} fat (optional)`}><DecimalInput value={mealTargets[slot].fatG} onInput={(event) => mealValue(slot, "fatG", event.currentTarget.value)} /></Field></div></fieldset>)}</div></details>
        </section>
        {save.error instanceof Error ? <p className="error-text" role="alert">{save.error.message}</p> : null}
        {saved ? <p className="success-text goal-saved-status" role="status">Your planning guide is saved.</p> : null}
        {showSaveAction ? <div className="goal-save"><div><p><strong>Ready when you are.</strong><span>Your existing meal plan will use the updated guide.</span></p></div><Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save my guide"}</Button></div> : null}
      </form>
    </main>
  );
}

