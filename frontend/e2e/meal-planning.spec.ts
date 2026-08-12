import { expect, type Page, test } from "@playwright/test";

const recipeId = "00000000-0000-4000-8000-000000000001";
const goalId = "00000000-0000-4000-8000-000000000010";
const planId = "00000000-0000-4000-8000-000000000020";

async function mockPlanningApi(page: Page) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  let preferences = { timezone: "America/Vancouver", weekStartsOn: 1, version: 1 };
  let goal: Record<string, unknown> | null = null;
  let entries: Array<Record<string, unknown>> = [];
  let planVersion = 1;
  await page.context().addCookies([{ name: "cookfully_csrf", value: "plan-e2e-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const fulfill = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/preferences") {
      if (method === "PUT") preferences = { ...request.postDataJSON(), version: preferences.version + 1 };
      return fulfill(preferences);
    }
    if (path === "/api/v1/goals/current") {
      if (method === "GET") return goal ? fulfill(goal) : fulfill({ code: "goal_not_found", title: "No goal" }, 404);
      goal = { id: goalId, ...request.postDataJSON(), macroCalorieDifference: "-15", version: 1 };
      return fulfill(goal);
    }
    if (path === "/api/v1/recipes") return fulfill({ items: [{ id: recipeId, title: "Protein oats", yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 }], nextCursor: null });
    if (path.startsWith("/api/v1/meal-plans/") && path.endsWith("/entries") && method === "POST") {
      const value = request.postDataJSON();
      const item = {
        id: `00000000-0000-4000-8000-${String(entries.length + 30).padStart(12, "0")}`,
        ...value,
        recipeTitle: "Protein oats",
        nutrition: { basisServings: value.servings, caloriesKcal: value.servings === "2.000" ? "1003" : "502", proteinG: value.servings === "2.000" ? "80.1" : "40.1", carbohydrateG: value.servings === "2.000" ? "120.1" : "60.1", fatG: value.servings === "2.000" ? "22.3" : "11.2", status: "estimated", coverageRatio: "0.950000" },
        origin: "manual",
        version: 1,
      };
      entries.push(item);
      planVersion += 1;
      return fulfill(item, 201);
    }
    if (path.startsWith("/api/v1/meal-plan-entries/") && method === "PATCH") {
      const id = path.split("/").at(-1);
      const value = request.postDataJSON();
      const index = entries.findIndex((item) => item.id === id);
      entries[index] = { ...entries[index], ...value, version: Number(entries[index].version) + 1, nutrition: { ...(entries[index].nutrition as object), basisServings: value.servings, caloriesKcal: value.servings === "2.000" ? "1003" : "502" } };
      planVersion += 1;
      return fulfill(entries[index]);
    }
    if (path.startsWith("/api/v1/meal-plan-entries/") && method === "DELETE") {
      const id = path.split("/").at(-1);
      entries = entries.filter((item) => item.id !== id);
      planVersion += 1;
      return route.fulfill({ status: 204 });
    }
    if (path.startsWith("/api/v1/meal-plans/") && method === "GET") {
      if (!entries.length) return fulfill({ code: "meal_plan_not_found", title: "No plan" }, 404);
      const days = Object.fromEntries([...new Set(entries.map((item) => String(item.localDate)))].map((day) => [day, { caloriesKcal: "502", proteinG: "40.1", carbohydrateG: "60.1", fatG: "11.2", status: "estimated", coverageRatio: "0.950000", targetDifference: { caloriesKcal: "-1698", proteinG: "-139.9", carbohydrateG: "-159.9", fatG: "-53.8" } }]));
      return fulfill({ id: planId, weekStart: "2026-03-09", timezone: preferences.timezone, goal, entries, dayTotals: days, weekTotal: { caloriesKcal: String(entries.length * 502), proteinG: `${(entries.length * 40.1).toFixed(1)}`, carbohydrateG: `${(entries.length * 60.1).toFixed(1)}`, fatG: `${(entries.length * 11.2).toFixed(1)}`, status: "estimated", coverageRatio: "0.950000" }, groceryStatus: "absent", version: planVersion });
    }
    if (path === "/api/v1/owner/preferences" || path === "/api/v1/auth/session") return fulfill(preferences);
    return fulfill({ code: "not_found", title: "Not found" }, 404);
  });
}

test("creates a goal, fills seven days, adjusts, copies, moves, and refreshes snapshots", async ({ page }) => {
  await mockPlanningApi(page);
  await page.goto("/app/goals");
  await page.getByLabel("Maintenance calories").fill("2500.000000");
  await page.getByLabel("Daily calories").fill("2200.000000");
  await page.getByLabel("Daily protein").fill("180.000000");
  await page.getByLabel("Daily carbohydrate").fill("220.000000");
  await page.getByLabel("Daily fat").fill("65.000000");
  await page.getByLabel("Effective from").fill("2026-03-01");
  await page.getByRole("button", { name: "Save targets" }).click();
  await expect(page.getByText("Targets saved")).toBeVisible();

  await page.getByRole("main").getByRole("link", { name: "Weekly plan" }).click();
  await expect(page.getByRole("heading", { name: /week of march 9/i })).toBeVisible();
  const tabs = page.getByRole("tab");
  await expect(tabs).toHaveCount(7);
  for (let index = 0; index < 7; index += 1) {
    await tabs.nth(index).click();
    await page.getByLabel("Breakfast recipe to add").selectOption(recipeId);
    await page.getByRole("button", { name: "Add to breakfast" }).click();
    await expect(page.getByRole("heading", { name: "Protein oats" })).toBeVisible();
  }

  await tabs.first().click();
  await page.getByLabel("Protein oats servings").fill("2.000");
  await page.getByRole("button", { name: "Update Protein oats" }).click();
  await expect(page.getByText("1003 kcal")).toBeVisible();
  await page.getByRole("button", { name: "Copy Protein oats to next day" }).click();
  await page.getByLabel("Protein oats meal slot").selectOption("lunch");
  await page.getByRole("button", { name: "Update Protein oats" }).click();
  await expect(page.getByRole("heading", { name: "Lunch" })).toBeVisible();
  await page.getByRole("button", { name: "Refresh Protein oats nutrition" }).click();
  await expect(page.getByText(/snapshot refreshed/i)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
