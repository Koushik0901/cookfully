import { expect, type Page, test } from "@playwright/test";

const recipeId = "00000000-0000-4000-8000-000000000001";
const monday = "2026-03-09";

function nutrition(servings: string) {
  const doubled = servings === "2.000";
  return {
    basisServings: servings,
    caloriesKcal: doubled ? "1003" : "502",
    proteinG: doubled ? "80.1" : "40.1",
    carbohydrateG: doubled ? "120.1" : "60.1",
    fatG: doubled ? "22.3" : "11.2",
    status: "estimated",
    coverageRatio: "0.950000",
  };
}

async function mockFiftyEntryPlan(page: Page) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  const entries = Array.from({ length: 50 }, (_, index) => ({
    id: `00000000-0000-4000-8000-${String(index + 100).padStart(12, "0")}`,
    localDate: monday,
    mealSlot: ["breakfast", "lunch", "dinner", "snack"][index % 4],
    recipeId,
    recipeTitle: `Recipe ${String(index + 1).padStart(2, "0")}`,
    servings: "1.000",
    position: index,
    refreshNutrition: false,
    nutrition: nutrition("1.000"),
    origin: "manual",
    version: 1,
  }));
  const goal = {
    id: "00000000-0000-4000-8000-000000000010",
    mode: "maintain",
    maintenanceKcal: "2200.000000",
    caloriesKcal: "2200.000000",
    proteinG: "180.000000",
    carbohydrateG: "220.000000",
    fatG: "65.000000",
    effectiveFrom: "2026-03-01",
    effectiveTo: null,
    mealTargets: [],
    macroCalorieDifference: "0.000000",
    version: 1,
  };
  await page.context().addCookies([{ name: "vv_csrf", value: "performance-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/owner/preferences") return route.fulfill({ json: { timezone: "America/Vancouver", weekStartsOn: 1, version: 1 } });
    if (path === "/api/v1/goals/current") return route.fulfill({ json: goal });
    if (path === "/api/v1/recipes") return route.fulfill({ json: { items: [{ id: recipeId, title: "Reference recipe", yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 }], nextCursor: null } });
    if (path.startsWith("/api/v1/meal-plan-entries/") && request.method() === "PATCH") {
      const entry = entries.find((item) => path.endsWith(item.id));
      if (!entry) return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
      const value = request.postDataJSON();
      Object.assign(entry, value, { nutrition: nutrition(value.servings), version: entry.version + 1 });
      return route.fulfill({ json: entry });
    }
    if (path.startsWith("/api/v1/meal-plans/") && request.method() === "GET") {
      const calories = entries.reduce((sum, entry) => sum + Number(entry.nutrition.caloriesKcal), 0);
      const total = { caloriesKcal: String(calories), proteinG: "2005.0", carbohydrateG: "3005.0", fatG: "560.0", status: "estimated", coverageRatio: "0.950000", targetDifference: { caloriesKcal: String(calories - 2200), proteinG: "1825.0", carbohydrateG: "2785.0", fatG: "495.0" } };
      return route.fulfill({ json: { id: "00000000-0000-4000-8000-000000000020", weekStart: monday, timezone: "America/Vancouver", goal, entries, dayTotals: { [monday]: total }, weekTotal: total, groceryStatus: "absent", version: 1 } });
    }
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

test("50-entry exact total updates remain visibly under two seconds at p95", async ({ page }, testInfo) => {
  await mockFiftyEntryPlan(page);
  await page.goto("/app/plan");
  await expect(page.getByLabel("March 9 budget").getByText(/^25100 \/ 2200\.000000 kcal$/)).toBeVisible();

  const entry = page.getByRole("article").filter({ has: page.getByRole("heading", { name: "Recipe 01" }) });
  const samples: number[] = [];
  for (let index = 0; index < 20; index += 1) {
    const servings = index % 2 === 0 ? "2.000" : "1.000";
    const expected = servings === "2.000" ? "25601" : "25100";
    await entry.getByLabel("Recipe 01 servings").fill(servings);
    const started = performance.now();
    await entry.getByRole("button", { name: "Update Recipe 01" }).click();
    await expect(page.getByLabel("March 9 budget").getByText(new RegExp(`^${expected} / 2200\\.000000 kcal$`))).toBeVisible();
    samples.push(performance.now() - started);
  }
  const ordered = [...samples].sort((left, right) => left - right);
  const p95 = ordered[Math.ceil(ordered.length * 0.95) - 1];
  const report = { samples: samples.length, p50Ms: ordered[Math.ceil(ordered.length * 0.5) - 1], p95Ms: p95, maxMs: ordered.at(-1) };
  await testInfo.attach("visible-update-latency.json", { body: JSON.stringify(report, null, 2), contentType: "application/json" });
  expect(p95, JSON.stringify(report)).toBeLessThan(2000);
});
