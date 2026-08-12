import { expect, type Page, test } from "@playwright/test";

const suggestionId = "00000000-0000-4000-8000-000000000201";
const recipeId = "00000000-0000-4000-8000-000000000101";
const itemId = "00000000-0000-4000-8000-000000000301";

async function mockSuggestionApi(page: Page) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  let scope = "day";
  await page.context().addCookies([{ name: "cookfully_csrf", value: "suggestion-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/owner/preferences") return route.fulfill({ json: { timezone: "America/Vancouver", weekStartsOn: 1, version: 1 } });
    if (path === "/api/v1/recipes") return route.fulfill({ json: { items: [{ id: recipeId, title: "Protein oats", yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 }], nextCursor: null } });
    if (path === "/api/v1/suggestions" && request.method() === "POST") {
      scope = request.postDataJSON().scope;
      return route.fulfill({ status: 202, json: { jobId: "00000000-0000-4000-8000-000000000401", resourceId: suggestionId, status: "queued" } });
    }
    const projected = scope === "week"
      ? { caloriesKcal: "8400", proteinG: "700.0", carbohydrateG: "840.0", fatG: "245.0", status: "estimated", coverageRatio: "0.95" }
      : { caloriesKcal: "1200", proteinG: "100.0", carbohydrateG: "120.0", fatG: "35.0", status: "estimated", coverageRatio: "0.95" };
    if (path === `/api/v1/suggestions/${suggestionId}`) return route.fulfill({ json: {
      id: suggestionId,
      status: "feasible",
      request: { scope, weekStart: "2026-03-09", localDate: scope === "week" ? null : "2026-03-11", mealSlot: null, tolerances: { caloriesKcal: "100", proteinG: "10", carbohydrateG: "15", fatG: "5" }, excludedRecipeIds: [], requiredRecipeIds: [], maxRecipeRepetitions: 3 },
      target: projected,
      items: [{ id: itemId, recipeId, recipeTitle: "Protein oats", localDate: "2026-03-11", mealSlot: "breakfast", servings: "1.000", projectedNutrition: { basisServings: "1.000", caloriesKcal: projected.caloriesKcal, proteinG: projected.proteinG, carbohydrateG: projected.carbohydrateG, fatG: projected.fatG, status: "estimated", coverageRatio: "0.95" }, accepted: false }],
      projectedDayTotals: { "2026-03-11": scope === "week" ? { ...projected, caloriesKcal: "1200", proteinG: "100.0", carbohydrateG: "120.0", fatG: "35.0" } : projected },
      projectedWeekTotal: projected,
      missedConstraints: [], unmetConstraintCount: 0, objectiveScore: "0", distanceComponents: { calories: "0", protein: "0", carbohydrates: "0", fat: "0", repetitionOverage: 0, missingRequiredRecipes: 0 }, planVersion: 4, failureCode: null,
      ranking: "fewest-unmet,weighted-4-3-1-1-2-5,fewer-entries,ordered-recipe-ids", planningNotice: "Planning aid only—not medical advice.", createdAt: "2026-03-11T18:00:00Z", expiresAt: "2026-03-11T19:00:00Z",
    } });
    if (path === `/api/v1/suggestions/${suggestionId}/accept`) return route.fulfill({ json: { id: "00000000-0000-4000-8000-000000000501", weekStart: "2026-03-09", timezone: "America/Vancouver", entries: [], dayTotals: { "2026-03-11": scope === "week" ? { ...projected, caloriesKcal: "1200", proteinG: "100.0", carbohydrateG: "120.0", fatG: "35.0" } : projected }, weekTotal: projected, groceryStatus: "dirty", version: 5 } });
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

for (const scope of ["day", "week"] as const) {
  test(`${scope} suggestion preserves exact preview and accepted-total parity`, async ({ page }) => {
    await mockSuggestionApi(page);
    await page.goto("/app/suggestions");
    await expect(page.getByRole("heading", { name: "Meal suggestions" })).toBeVisible();
    await page.getByLabel("Suggestion scope").selectOption(scope);
    await page.getByRole("button", { name: "Generate suggestions" }).click();
    await expect(page.getByText("Feasible within your tolerances")).toBeVisible();
    const expected = scope === "week" ? "8400 kcal" : "1200 kcal";
    await expect(page.getByTestId("preview-primary-total")).toContainText(expected);
    await page.getByRole("button", { name: "Accept 1 selected item" }).click();
    await expect(page.getByTestId("accepted-primary-total")).toContainText(expected);
    await expect(page.getByText(/matches the preview/i)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}
