import { expect, type Page, test } from "@playwright/test";

const recipeId = "00000000-0000-4000-8000-000000000201";
const collectionId = "00000000-0000-4000-8000-000000000202";
const entryId = "00000000-0000-4000-8000-000000000203";
const weekStart = "2026-03-09";

function recipeDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: recipeId,
    title: "Lemon lentils",
    description: "A weeknight bowl.",
    sourceUrl: null,
    imageUrl: null,
    yieldQuantity: "2.000",
    yieldUnit: "servings",
    status: "ready",
    archivedFromStatus: null,
    nutritionState: "estimated",
    nutrition: {
      status: "estimated",
      basisServings: "2.000",
      coverageRatio: "0.950000",
      caloriesKcal: "540.000000",
      proteinG: "38.500000",
      carbohydrateG: "62.000000",
      fatG: "14.000000",
      provenance: [],
      assumptions: [],
      corrections: [],
      micronutrients: {},
    },
    favorite: false,
    collections: [],
    mealRoles: [],
    version: 1,
    updatedAt: "2026-03-11T18:00:00Z",
    thumbnailCrop: { x: "0", y: "0", width: "1", height: "1" },
    originKind: "manual",
    ingredients: [{
      id: "00000000-0000-4000-8000-000000000204",
      position: 0,
      originalText: "1 cup red lentils",
      quantityMin: "1.000000",
      quantityMax: null,
      unit: "cup",
      food: "red lentils",
      preparation: null,
      optional: false,
      parseStatus: "parsed",
      matchStatus: "matched",
      assumptions: [],
    }],
    instructions: [{ position: 0, text: "Simmer until tender." }],
    sections: [],
    activeJob: null,
    ...overrides,
  };
}

async function mockOrganizationApi(page: Page) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  let recipe = recipeDetail();
  let entries: Array<Record<string, unknown>> = [];
  let planVersion = 1;
  const collection = { id: collectionId, name: "Weeknight favourites", position: 0, version: 1, recipeCount: 0 };
  await page.context().addCookies([{ name: "cookfully_csrf", value: "organization-e2e-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/preferences") return json({ timezone: "America/Vancouver", weekStartsOn: 1, version: 1 });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/goals/current") return json({ code: "goal_not_found", title: "No goal" }, 404);
    if (path === "/api/v1/recipes/collections" && method === "GET") return json([collection]);
    if (path === `/api/v1/recipes/${recipeId}` && method === "GET") return json(recipe);
    if (path === `/api/v1/recipes/${recipeId}/organization` && method === "PUT") {
      const body = request.postDataJSON() as { favorite: boolean; collectionIds: string[]; mealRoles: string[] };
      recipe = recipeDetail({
        ...recipe,
        favorite: body.favorite,
        collections: body.collectionIds.map((id) => ({ id, name: collection.name, position: collection.position })),
        mealRoles: body.mealRoles,
        version: Number(recipe.version) + 1,
      });
      return json(recipe);
    }
    if (path === "/api/v1/recipes" && method === "GET") return json({ items: [recipe], nextCursor: null });
    if (path === `/api/v1/meal-plans/${weekStart}` && method === "GET") {
      return json({
        id: "00000000-0000-4000-8000-000000000205",
        weekStart,
        timezone: "America/Vancouver",
        goal: null,
        entries,
        dayTotals: {},
        weekTotal: { caloriesKcal: "0", proteinG: "0", carbohydrateG: "0", fatG: "0", status: "estimated", coverageRatio: "0.000000" },
        groceryStatus: "absent",
        version: planVersion,
      });
    }
    if (path === `/api/v1/meal-plans/${weekStart}/entries` && method === "POST") {
      const body = request.postDataJSON() as { recipeId: string; localDate: string; mealSlot: string; servings: string; position: number };
      const entry = {
        id: entryId,
        ...body,
        recipeTitle: String(recipe.title),
        nutrition: { basisServings: body.servings, caloriesKcal: "540", proteinG: "38.5", carbohydrateG: "62", fatG: "14", status: "estimated", coverageRatio: "0.950000" },
        origin: "manual",
        version: 1,
      };
      entries = [entry];
      planVersion += 1;
      return json(entry, 201);
    }
    return json({ code: "not_found", title: "Not found" }, 404);
  });
}

test("organizes a recipe and removes focused filters on desktop and mobile", async ({ page }) => {
  await mockOrganizationApi(page);
  await page.goto(`/app/recipes/${recipeId}`);
  await expect(page.getByRole("heading", { name: "Lemon lentils" })).toBeVisible();
  await page.getByText("Keep this easy to find", { exact: true }).click();
  await page.getByLabel("Favorite this recipe").check();
  await page.getByRole("checkbox", { name: "Weeknight favourites", exact: true }).check();
  await page.getByRole("checkbox", { name: "dinner", exact: true }).check();
  await page.getByRole("button", { name: "Save organization" }).click();
  await expect(page.getByText("Weeknight favourites", { exact: true }).first()).toBeVisible();

  await page.goto("/app/recipes");
  await expect(page.getByRole("link", { name: "Lemon lentils" })).toBeVisible();
  await page.getByText("Refine recipes", { exact: true }).click();
  await page.getByLabel("Favorites only").check();
  await page.getByLabel("Collection", { exact: true }).selectOption(collectionId);
  await page.getByLabel("Meal moment", { exact: true }).selectOption("dinner");
  await expect(page.getByRole("button", { name: /Favorites.*remove filter/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Collection: Weeknight favourites.*remove filter/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /Meal: dinner.*remove filter/i })).toBeVisible();
  await page.getByRole("button", { name: /Meal: dinner.*remove filter/i }).click();
  await expect(page.getByRole("button", { name: /Meal: dinner.*remove filter/i })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
test("plans an unorganized recipe without requiring metadata", async ({ page }) => {
  await mockOrganizationApi(page);
  await page.goto("/app/plan");
  await page.getByRole("tab", { name: "Day" }).click();
  await page.getByRole("button", { name: "Add a recipe to Dinner" }).click();
  await page.getByRole("button", { name: "Add Lemon lentils to Dinner" }).click();
  await expect(page.getByRole("heading", { name: "Lemon lentils" })).toBeVisible();
  await expect(page.getByText("Meal added to your plan.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
