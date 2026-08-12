import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SuggestionPage } from "../SuggestionPage";
import type { SuggestionResult } from "../types";
import { unavailableMicronutrients } from "../../../test/fixtures";

const recipeOne = "00000000-0000-4000-8000-000000000101";
const recipeTwo = "00000000-0000-4000-8000-000000000102";
const suggestionId = "00000000-0000-4000-8000-000000000201";
const itemOne = "00000000-0000-4000-8000-000000000301";
const itemTwo = "00000000-0000-4000-8000-000000000302";

const result: SuggestionResult = {
  id: suggestionId,
  status: "feasible",
  request: {
    scope: "day",
    weekStart: "2026-03-09",
    localDate: "2026-03-11",
    mealSlot: null,
    tolerances: { caloriesKcal: "100", proteinG: "10", carbohydrateG: "15", fatG: "5" },
    excludedRecipeIds: [],
    requiredRecipeIds: [recipeOne],
    maxRecipeRepetitions: 2,
  },
  target: { caloriesKcal: "1200", proteinG: "100", carbohydrateG: "120", fatG: "35" },
  items: [
    {
      id: itemOne,
      recipeId: recipeOne,
      recipeTitle: "Protein oats",
      localDate: "2026-03-11",
      mealSlot: "breakfast",
      servings: "1.000",
      projectedNutrition: { basisServings: "1.000", caloriesKcal: "500", proteinG: "45.0", carbohydrateG: "60.0", fatG: "12.0", status: "estimated", coverageRatio: "0.95", micronutrients: unavailableMicronutrients },
      accepted: false,
    },
    {
      id: itemTwo,
      recipeId: recipeTwo,
      recipeTitle: "Chicken rice bowl",
      localDate: "2026-03-11",
      mealSlot: "dinner",
      servings: "1.000",
      projectedNutrition: { basisServings: "1.000", caloriesKcal: "700", proteinG: "55.0", carbohydrateG: "60.0", fatG: "23.0", status: "estimated", coverageRatio: "0.98", micronutrients: unavailableMicronutrients },
      accepted: false,
    },
  ],
  projectedDayTotals: {
    "2026-03-11": { caloriesKcal: "1200", proteinG: "100.0", carbohydrateG: "120.0", fatG: "35.0", status: "estimated", coverageRatio: "0.96", micronutrients: unavailableMicronutrients },
  },
  projectedWeekTotal: { caloriesKcal: "4300", proteinG: "360.0", carbohydrateG: "450.0", fatG: "130.0", status: "estimated", coverageRatio: "0.95", micronutrients: unavailableMicronutrients },
  missedConstraints: [],
  unmetConstraintCount: 0,
  objectiveScore: "0",
  distanceComponents: { calories: "0", protein: "0", carbohydrates: "0", fat: "0", repetitionOverage: 0, missingRequiredRecipes: 0 },
  planVersion: 4,
  failureCode: null,
  ranking: "fewest-unmet,weighted-4-3-1-1-2-5,fewer-entries,ordered-recipe-ids",
  planningNotice: "Planning aid only—not medical advice.",
  createdAt: "2026-03-11T18:00:00Z",
  expiresAt: "2026-03-11T19:00:00Z",
};

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

function renderPage(path = "/app/suggestions") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><SuggestionPage /></MemoryRouter></QueryClientProvider>);
}

describe("suggestion UI", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=suggestion-csrf; path=/";
    vi.setSystemTime(new Date("2026-03-11T18:00:00Z"));
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "00000000-0000-4000-8000-000000000999") });
    vi.stubGlobal("fetch", vi.fn((input, init) => {
      const path = String(input);
      if (path.includes("/owner/preferences")) return json({ timezone: "America/Vancouver", weekStartsOn: 1, version: 1 });
      if (path.includes("/recipes")) return json({ items: [
        { id: recipeOne, title: "Protein oats", yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 },
        { id: recipeTwo, title: "Chicken rice bowl", yieldQuantity: "4", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 },
      ], nextCursor: null });
      if (path.endsWith("/suggestions") && init?.method === "POST") return json({ jobId: "00000000-0000-4000-8000-000000000401", resourceId: suggestionId, status: "queued" }, 202);
      if (path.endsWith(`/suggestions/${suggestionId}`)) return json(result);
      if (path.endsWith(`/suggestions/${suggestionId}/accept`)) return json({ id: "plan", weekStart: "2026-03-09", timezone: "America/Vancouver", entries: [], dayTotals: result.projectedDayTotals, weekTotal: result.projectedWeekTotal, version: 5 });
      return json({}, 404);
    }));
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("opens in the meal-planning context carried from an empty slot", async () => {
    renderPage("/app/suggestions?scope=meal&localDate=2026-03-13&mealSlot=dinner");
    expect(await screen.findByRole("radio", { name: /One meal/i })).toBeChecked();
    expect(screen.getByLabelText("Day to plan")).toHaveValue("2026-03-13");
    expect(screen.getByLabelText("Meal")).toHaveValue("dinner");
  });

  it("edits meal/day/week constraints and explains a feasible deterministic preview", async () => {
    renderPage();
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "What would make your plan easier?" })).toBeVisible();
    expect(screen.getByText("Nothing changes yet")).toBeVisible();
    await user.click(screen.getByText("Fine-tune the nutrition fit", { selector: "strong" }));
    await user.click(screen.getByText("Use or avoid specific recipes", { selector: "strong" }));
    await user.click(screen.getByRole("radio", { name: /One meal/i }));
    expect(screen.getByLabelText("Meal")).toBeVisible();
    await user.click(screen.getByRole("radio", { name: /Fill my week/i }));
    expect(screen.queryByLabelText("Day to plan")).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /A full day/i }));
    await user.clear(screen.getByLabelText("Calories tolerance"));
    await user.type(screen.getByLabelText("Calories tolerance"), "100.000000");
    await user.click(screen.getByLabelText("Use Protein oats"));
    await user.click(screen.getByLabelText("Avoid Chicken rice bowl"));
    await user.click(screen.getByRole("button", { name: "Find meal ideas" }));

    expect(await screen.findByText("Here’s a plan that fits")).toBeVisible();
    await user.click(screen.getByText("How Cookfully chose this", { selector: "summary" }));
    expect(screen.getByRole("heading", { name: "How Cookfully chose this" })).toBeVisible();
    expect(screen.getByText(/fewest unmet constraints.*weighted macro distance.*fewer entries.*recipe IDs/i)).toBeVisible();
    await user.click(screen.getByText("Nutrition fit for this day", { selector: "summary" }));
    expect(screen.getByText("1200 kcal")).toBeVisible();
    expect(screen.getByText("100.0 g protein")).toBeVisible();
    expect(screen.getByLabelText("Accept Protein oats")).toBeChecked();
    expect(screen.getByLabelText("Accept Chicken rice bowl")).toBeChecked();

    const createCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input).endsWith("/suggestions") && init?.method === "POST");
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      scope: "day",
      tolerances: { caloriesKcal: "100.000000" },
      requiredRecipeIds: [recipeOne],
      excludedRecipeIds: [recipeTwo],
    });
  });

  it("selectively accepts preview items and reports exact accepted-total parity", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Find meal ideas" }));
    await screen.findByText("Here’s a plan that fits");
    await user.click(screen.getByLabelText("Accept Chicken rice bowl"));
    await user.click(screen.getByRole("button", { name: "Accept 1 selected item" }));
    expect(await screen.findByText(/1 meal is ready in your plan/i)).toBeVisible();
    expect(screen.getByText(/accepted day total: 1200 kcal.*matches the preview/i)).toBeVisible();
    const acceptCall = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input).endsWith("/accept") && init?.method === "POST");
    expect(JSON.parse(String(acceptCall?.[1]?.body))).toEqual({ selectedItemIds: [itemOne], expectedPlanVersion: 4 });
  });

  it("names infeasible blockers and withholds acceptance", async () => {
    vi.mocked(fetch).mockImplementation((input, init) => {
      const path = String(input);
      if (path.includes("/owner/preferences")) return json({ timezone: "America/Vancouver", weekStartsOn: 1, version: 1 });
      if (path.includes("/recipes")) return json({ items: [{ id: recipeOne, title: "Protein oats", yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 }], nextCursor: null });
      if (path.endsWith("/suggestions") && init?.method === "POST") return json({ jobId: "job", resourceId: suggestionId, status: "queued" }, 202);
      if (path.endsWith(`/suggestions/${suggestionId}`)) return json({ ...result, status: "infeasible", items: [], missedConstraints: ["protein tolerance", "required recipe unavailable"], unmetConstraintCount: 2 });
      return json({}, 404);
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Find meal ideas" }));
    expect(await screen.findByText("We couldn’t fit every preference")).toBeVisible();
    const blockers = screen.getByRole("region", { name: "Preferences to loosen" });
    expect(within(blockers).getByText("Protein tolerance")).toBeVisible();
    expect(within(blockers).getByText("Required recipe unavailable")).toBeVisible();
    expect(screen.queryByRole("button", { name: /accept/i })).not.toBeInTheDocument();
  });

  it("recovers explicitly when the plan changed before acceptance", async () => {
    vi.mocked(fetch).mockImplementation((input, init) => {
      const path = String(input);
      if (path.includes("/owner/preferences")) return json({ timezone: "America/Vancouver", weekStartsOn: 1, version: 1 });
      if (path.includes("/recipes")) return json({ items: [{ id: recipeOne, title: "Protein oats", yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 }], nextCursor: null });
      if (path.endsWith("/suggestions") && init?.method === "POST") return json({ jobId: "job", resourceId: suggestionId, status: "queued" }, 202);
      if (path.endsWith(`/suggestions/${suggestionId}`)) return json(result);
      if (path.endsWith("/accept")) return json({ code: "stale_plan", detail: "The meal plan changed." }, 409);
      return json({}, 404);
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Find meal ideas" }));
    await user.click(await screen.findByRole("button", { name: "Accept 2 selected items" }));
    expect(await screen.findByText(/plan changed before acceptance/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Create a fresh suggestion" })).toBeVisible();
  });
});
