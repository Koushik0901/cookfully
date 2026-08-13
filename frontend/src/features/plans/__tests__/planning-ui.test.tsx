import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GoalSettingsPage } from "../../goals/GoalSettingsPage";
import { unavailableMicronutrients } from "../../../test/fixtures";
import { DayTabs } from "../DayTabs";
import { MacroSummary } from "../MacroSummary";
import { WeeklyPlannerPage } from "../WeeklyPlannerPage";
import type { MealPlan, OwnerPreferences, UserGoal } from "../types";

const preferences: OwnerPreferences = { displayName: "Owner", timezone: "America/Vancouver", weekStartsOn: 1, version: 2 };
const planMicronutrients = {
  ...unavailableMicronutrients,
  dietaryFiberG: { ...unavailableMicronutrients.dietaryFiberG, value: "12.5", coverageRatio: "0.95", source: "reference" as const },
};
const goal: UserGoal = {
  id: "00000000-0000-4000-8000-000000000010",
  mode: "cut",
  maintenanceKcal: "2500.000000",
  caloriesKcal: "2200.000000",
  proteinG: "180.000000",
  carbohydrateG: "220.000000",
  fatG: "65.000000",
  effectiveFrom: "2026-03-01",
  effectiveTo: null,
  mealTargets: [{ mealSlot: "breakfast", caloriesKcal: "500.000000", proteinG: null, carbohydrateG: null, fatG: null }],
  macroCalorieDifference: "-15.000000",
  version: 1,
};
const entry = {
  id: "00000000-0000-4000-8000-000000000020",
  localDate: "2026-03-09",
  mealSlot: "breakfast",
  recipeId: "00000000-0000-4000-8000-000000000001",
  recipeTitle: "Protein oats",
  servings: "1.500",
  position: 0,
  refreshNutrition: false,
  nutrition: { basisServings: "1.500", caloriesKcal: "752", proteinG: "60.1", carbohydrateG: "90.1", fatG: "16.7", status: "estimated" as const, coverageRatio: "0.950000", micronutrients: planMicronutrients },
  origin: "manual" as const,
  version: 1,
};
const total = {
  caloriesKcal: "752",
  proteinG: "60.1",
  carbohydrateG: "90.1",
  fatG: "16.7",
  status: "estimated" as const,
  coverageRatio: "0.950000",
  micronutrients: planMicronutrients,
  targetDifference: { caloriesKcal: "-1448", proteinG: "-119.9", carbohydrateG: "-129.9", fatG: "-48.3" },
};
const plan: MealPlan = {
  id: "00000000-0000-4000-8000-000000000030",
  weekStart: "2026-03-09",
  timezone: "America/Vancouver",
  goal,
  entries: [entry],
  dayTotals: { "2026-03-09": total },
  weekTotal: total,
  groceryStatus: "absent",
  version: 2,
};

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

function renderPage(page: React.ReactNode, path = "/app/plan") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path="/app/plan" element={page} /><Route path="/app/goals" element={page} /></Routes></MemoryRouter></QueryClientProvider>);
}

describe("goal and weekly planning UI", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=planning-csrf; path=/";
    vi.setSystemTime(new Date("2026-03-11T18:00:00Z"));
    vi.stubGlobal("fetch", vi.fn((input) => {
      const path = String(input);
      if (path.includes("/owner/preferences")) return json(preferences);
      if (path.includes("/goals/current")) return json(goal);
      if (path.includes("/meal-plans/")) return json(plan);
      if (path.includes("/recipes")) return json({ items: [{ id: entry.recipeId, title: entry.recipeTitle, yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 }], nextCursor: null });
      return json({}, 404);
    }));
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("edits required daily targets and optional meal targets", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const path = String(input);
      if (init?.method === "PUT" && path.includes("/goals/current")) return json({ ...goal, caloriesKcal: "2300", version: 2 });
      if (path.includes("/owner/preferences")) return json(preferences);
      return json(goal);
    });
    renderPage(<GoalSettingsPage />, "/app/goals");
    const user = userEvent.setup();
    expect(await screen.findByLabelText("Current daily nutrition guide")).toHaveTextContent("2,200 kcal");
    expect(screen.getByText((_, element) => element?.tagName === "P" && /guide adds up to about.*15 kcal below/i.test(element.textContent ?? ""))).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Adjust daily guide" }));
    expect(await screen.findByDisplayValue("2200.000000")).toBeVisible();
    await user.click(screen.getByText("Meal-by-meal targets", { selector: "strong" }));
    await user.clear(screen.getByLabelText("Daily calories"));
    await user.type(screen.getByLabelText("Daily calories"), "2300.000000");
    expect(screen.getByText((_, element) => element?.tagName === "P" && /115 kcal below/i.test(element.textContent ?? ""))).toBeVisible();
    expect(screen.getByLabelText("Breakfast protein (optional)")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Save my guide" }));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT")).toHaveLength(1));
    const goalCall = fetchMock.mock.calls.find(([input, init]) => String(input).includes("/goals/current") && init?.method === "PUT");
    expect(JSON.parse(String(goalCall?.[1]?.body))).toMatchObject({ caloriesKcal: "2300.000000", mealTargets: [{ proteinG: null }] });
    expect(new Headers(goalCall?.[1]?.headers).get("if-match")).toBe('"1"');
  });

  it("rejects null or invalid required daily targets before saving", async () => {
    renderPage(<GoalSettingsPage />, "/app/goals");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Adjust daily guide" }));
    await screen.findByDisplayValue("2200.000000");
    await user.clear(screen.getByLabelText("Daily protein"));
    await user.click(screen.getByRole("button", { name: "Save my guide" }));
    expect(await screen.findByText("Daily protein is required.")).toBeVisible();
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("moves day-tab focus with arrow keys and announces the selected local date", async () => {
    const user = userEvent.setup();
    render(<DayTabs dates={["2026-03-09", "2026-03-10", "2026-03-11"]} selected="2026-03-09" onSelect={vi.fn()} totals={{}} />);
    const monday = screen.getByRole("tab", { name: /monday.*march 9/i });
    monday.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /tuesday.*march 10/i })).toHaveFocus();
  });

  it("renders exact macro budgets with text reliability, differences, and micronutrient evidence", async () => {
    const user = userEvent.setup();
    render(<MacroSummary total={total} target={goal} label="Monday budget" />);
    expect(screen.getByRole("region", { name: "Monday budget" })).toBeVisible();
    expect(screen.getByText("752 / 2200.000000 kcal")).toBeVisible();
    expect(screen.getByText("60.1 / 180.000000 g")).toBeVisible();
    expect(screen.getByText(/nutrition estimate supported/i)).toBeVisible();
    expect(screen.getByText("119.9 g remaining")).toBeVisible();
    expect(screen.getAllByRole("progressbar")).toHaveLength(4);
    await user.click(screen.getByText("Micronutrient planning view"));
    expect(screen.getByText("12.5 g")).toBeVisible();
    expect(screen.getByText(/planning aid, not medical advice/i)).toBeVisible();
  });

  it("labels signed target differences without reversing their meaning", () => {
    render(<MacroSummary total={{ ...total, targetDifference: { ...total.targetDifference, caloriesKcal: "25.500000", proteinG: "0.000000" } }} target={goal} label="Signed differences" />);
    expect(screen.getByText("25.500000 kcal over target")).toBeVisible();
    expect(screen.getByText("Target met")).toBeVisible();
    expect(screen.getByText("129.9 g remaining")).toBeVisible();
  });

  it("shows full targets remaining when a day has no entries", () => {
    render(<MacroSummary target={goal} label="Empty day" />);
    expect(screen.getByText("2200.000000 kcal remaining")).toBeVisible();
    expect(screen.getByRole("progressbar", { name: "Calories budget used" })).toHaveAttribute("aria-valuetext", "0 of 2200.000000 kcal; 2200.000000 kcal remaining");
  });

  it("renders week/day navigation, meal slots, entry controls, and optimistic mutations", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const path = String(input);
      if (init?.method === "PATCH") return json({ ...entry, servings: "2", nutrition: { ...entry.nutrition, caloriesKcal: "1003" }, version: 2 });
      if (init?.method === "POST" && path.includes("/entries")) return json({ ...entry, id: "copy-id", localDate: "2026-03-10" }, 201);
      if (init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
      if (path.includes("/owner/preferences")) return json(preferences);
      if (path.includes("/goals/current")) return json(goal);
      if (path.includes("/meal-plans/")) return json(plan);
      if (path.includes("/recipes")) return json({ items: [{ id: entry.recipeId, title: entry.recipeTitle, yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 }], nextCursor: null });
      return json({}, 404);
    });
    renderPage(<WeeklyPlannerPage />);
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: /week of march 9/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: "See the food, not just the count" })).toBeVisible();
    expect(screen.getByRole("button", { name: /edit monday.*march 9/i })).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Prep" }));
    expect(screen.getByRole("heading", { name: "Cook 1 dish for 1 meal" })).toBeVisible();
    expect(screen.getByText("1.5 total servings")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Day" }));
    await user.click(screen.getByRole("tab", { name: /monday.*march 9/i }));
    expect(screen.getByRole("tab", { name: /monday.*march 9/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Breakfast" })).toBeVisible();
    expect(await screen.findByRole("heading", { name: "Protein oats" })).toBeVisible();
    expect(screen.getAllByText("Nutrition estimate supported").length).toBeGreaterThan(0);

    await user.click(screen.getByText("Adjust meal", { selector: "summary" }));
    await user.clear(screen.getByLabelText("Protein oats servings"));
    await user.type(screen.getByLabelText("Protein oats servings"), "2.000");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(new Headers(call?.[1]?.headers).get("if-match")).toBe('"1"');
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ servings: "2.000" });
    });
    await user.click(screen.getByRole("button", { name: "Refresh nutrition" }));
    await user.click(screen.getByRole("button", { name: "Next day" }));
    await user.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true));
  });

  it("lets someone plan meals before creating a nutrition guide", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const path = String(input);
      if (init?.method === "POST" && path.includes("/entries")) return json(entry, 201);
      if (path.includes("/owner/preferences")) return json(preferences);
      if (path.includes("/goals/current")) return json({ code: "goal_not_found", title: "No goal" }, 404);
      if (path.includes("/meal-plans/")) return json({ code: "meal_plan_not_found", title: "No plan" }, 404);
      if (path.includes("/recipes")) return json({ items: [{ id: entry.recipeId, title: entry.recipeTitle, yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 }], nextCursor: null });
      return json({}, 404);
    });

    renderPage(<WeeklyPlannerPage />);
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: /week of march 9/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Plan the food now. Add your guide when you’re ready." })).toBeVisible();
    expect(screen.getByRole("link", { name: "Add nutrition guide" })).toBeVisible();

    await user.click(screen.getByRole("tab", { name: "Day" }));
    await user.click(screen.getByRole("button", { name: "Add a recipe to Lunch" }));
    await user.click(await screen.findByRole("button", { name: "Add Protein oats to Lunch" }));

    expect(await screen.findByText("Meal added to your plan.")).toBeVisible();
    const addCall = fetchMock.mock.calls.find(([input, init]) => String(input).includes("/entries") && init?.method === "POST");
    expect(JSON.parse(String(addCall?.[1]?.body))).toMatchObject({ mealSlot: "lunch", recipeId: entry.recipeId });
    expect(screen.queryByText(/set targets first/i)).not.toBeInTheDocument();
  });

  it("keeps stale recipes out of planning selectors until recalculated", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockImplementation((input) => {
      const path = String(input);
      if (path.includes("/owner/preferences")) return json(preferences);
      if (path.includes("/goals/current")) return json(goal);
      if (path.includes("/meal-plans/")) return json(plan);
      if (path.includes("/recipes")) return json({ items: [
        { id: entry.recipeId, title: entry.recipeTitle, yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 },
        { id: "00000000-0000-4000-8000-000000000099", title: "Changed recipe", yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "stale", version: 2 },
      ], nextCursor: null });
      return json({}, 404);
    });
    renderPage(<WeeklyPlannerPage />);
    await user.click(await screen.findByRole("tab", { name: "Day" }));
    await user.click(await screen.findByRole("button", { name: "Add a recipe to Lunch" }));
    expect(screen.getByRole("button", { name: "Add Protein oats to Lunch" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add Changed recipe to Lunch" })).not.toBeInTheDocument();
  });
});
