import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Button, DecimalInput, ErrorRecovery, Field, PageHeader, Skeleton } from "../../components";
import { ApiProblem } from "../recipes/api";
import { planningApi } from "../plans/api";
import { todayInTimezone } from "../plans/dates";
import type { MealTarget, UserGoalWrite } from "../plans/types";

const MEAL_SLOTS = ["breakfast", "lunch", "dinner", "snack"] as const;
const TIMEZONES = ["UTC", "America/Vancouver", "America/New_York", "Europe/London"];
const decimal = /^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/;

type TargetFields = Record<string, { caloriesKcal: string; proteinG: string; carbohydrateG: string; fatG: string }>;

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
    },
  });

  function mealValue(slot: string, field: keyof TargetFields[string], value: string) {
    setMealTargets((current) => ({ ...current, [slot]: { ...current[slot], [field]: value } }));
  }

  function onCaloriesChange(value: string) {
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
  const difference = currentGoal.data?.macroCalorieDifference;

  return (
    <main className="page-shell">
      <PageHeader eyebrow="Personal targets" title="Goals and calendar" description="Set exact daily budgets and local-week preferences. Meal targets remain optional." actions={<Button asChild><Link to="/app/plan">Weekly plan</Link></Button>} />
      {difference ? <p className="notice">Macro targets account for {difference.startsWith("-") ? difference.slice(1) : difference} {difference.startsWith("-") ? "fewer" : "more"} calories than the daily calorie target. The app keeps both values visible.</p> : null}
      <form className="goal-form" onSubmit={submit} noValidate>
        <section className="settings-section"><h2>Calendar preferences</h2><div className="form-grid"><Field label="Timezone"><select className="input" value={timezone} onChange={(event) => setTimezone(event.target.value)}>{!TIMEZONES.includes(timezone) ? <option value={timezone}>{timezone}</option> : null}{TIMEZONES.map((value) => <option key={value} value={value}>{value}</option>)}</select></Field><Field label="Week starts on"><select className="input" value={weekStartsOn} onChange={(event) => setWeekStartsOn(event.target.value)}><option value="1">Monday</option><option value="7">Sunday</option><option value="6">Saturday</option></select></Field></div></section>
        <section className="settings-section"><h2>Daily targets</h2><div className="form-grid"><Field label="Goal mode"><select className="input" value={mode} onChange={(event) => setMode(event.target.value as UserGoalWrite["mode"])}><option value="cut">Cut</option><option value="maintain">Maintain</option><option value="bulk">Bulk</option></select></Field><Field label="Maintenance calories" error={errors.maintenanceKcal}><DecimalInput value={maintenanceKcal} onInput={(event) => setMaintenanceKcal(event.currentTarget.value)} /></Field><Field label="Daily calories" error={errors.caloriesKcal}><DecimalInput value={caloriesKcal} onInput={(event) => onCaloriesChange(event.currentTarget.value)} /></Field><Field label="Daily protein" error={errors.proteinG}><DecimalInput value={proteinG} onInput={(event) => setProteinG(event.currentTarget.value)} /></Field><Field label="Daily carbohydrate" error={errors.carbohydrateG}><DecimalInput value={carbohydrateG} onInput={(event) => setCarbohydrateG(event.currentTarget.value)} /></Field><Field label="Daily fat" error={errors.fatG}><DecimalInput value={fatG} onInput={(event) => setFatG(event.currentTarget.value)} /></Field><Field label="Effective from" error={errors.effectiveFrom}><input className="input" type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} /></Field><Field label="Effective to (optional)" error={errors.effectiveTo}><input className="input" type="date" value={effectiveTo} onChange={(event) => setEffectiveTo(event.target.value)} /></Field></div></section>
        <section className="settings-section"><h2>Optional meal targets</h2><details className="disclosure"><summary>Show optional meal targets</summary><div className="meal-targets">{MEAL_SLOTS.map((slot) => <fieldset key={slot}><legend>{slot}</legend><div className="form-grid"><Field label={`${slot[0].toUpperCase()}${slot.slice(1)} calories (optional)`}><DecimalInput value={mealTargets[slot].caloriesKcal} onInput={(event) => mealValue(slot, "caloriesKcal", event.currentTarget.value)} /></Field><Field label={`${slot[0].toUpperCase()}${slot.slice(1)} protein (optional)`}><DecimalInput value={mealTargets[slot].proteinG} onInput={(event) => mealValue(slot, "proteinG", event.currentTarget.value)} /></Field><Field label={`${slot[0].toUpperCase()}${slot.slice(1)} carbohydrate (optional)`}><DecimalInput value={mealTargets[slot].carbohydrateG} onInput={(event) => mealValue(slot, "carbohydrateG", event.currentTarget.value)} /></Field><Field label={`${slot[0].toUpperCase()}${slot.slice(1)} fat (optional)`}><DecimalInput value={mealTargets[slot].fatG} onInput={(event) => mealValue(slot, "fatG", event.currentTarget.value)} /></Field></div></fieldset>)}</div></details></section>
        {save.error instanceof Error ? <p className="error-text" role="alert">{save.error.message}</p> : null}
        {saved ? <p className="success-text" role="status">Targets saved</p> : null}
        <Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save targets"}</Button>
      </form>
    </main>
  );
}

