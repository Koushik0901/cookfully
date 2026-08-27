import { expect, type Page, test } from "@playwright/test";
import { Buffer } from "node:buffer";

const recipeId = "00000000-0000-4000-8000-000000000101";
const collectionId = "00000000-0000-4000-8000-000000000102";
const entryId = "00000000-0000-4000-8000-000000000103";
const groceryItemId = "00000000-0000-4000-8000-000000000104";
const groceryListId = "00000000-0000-4000-8000-000000000105";
const groceryStopId = "00000000-0000-4000-8000-000000000106";
const weekStart = "2026-03-09";

function recipeDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: recipeId,
    title: "Lemon lentils",
    description: "A first recipe worth making again.",
    sourceUrl: null,
    imageUrl: "/api/v1/media/00000000-0000-4000-8000-000000000107",
    yieldQuantity: "2.000",
    yieldUnit: "servings",
    prepMinutes: null,
    cookMinutes: null,
    status: "ready",
    archivedFromStatus: null,
    favorite: false,
    collections: [],
    mealRoles: [],
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
    },
    version: 1,
    updatedAt: "2026-03-11T18:00:00Z",
    ingredients: [{
      id: "00000000-0000-4000-8000-000000000108",
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
      section: null,
    }],
    instructions: [{ position: 0, text: "Simmer until tender.", section: null }],
    activeJob: null,
    ...overrides,
  };
}

async function mockFirstKitchenApi(page: Page) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  const collection = { id: collectionId, name: "Weeknight favourites", position: 0, version: 1, recipeCount: 0 };
  let recipe: Record<string, unknown> | null = null;
  let entry: Record<string, unknown> | null = null;
  let groceryStatus = "dirty";
  let groceryVersion = 1;
  let stop: Record<string, unknown> | null = null;
  let groceryItem: Record<string, unknown> | null = null;

  await page.context().addCookies([{ name: "cookfully_csrf", value: "first-kitchen-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/api/v1/owner/preferences") return json({ timezone: "America/Vancouver", weekStartsOn: 1, version: 1 });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/goals/current") return json({ code: "goal_not_found", title: "No goal" }, 404);
    if (path.startsWith("/api/v1/media/")) return route.fulfill({ status: 204 });

    if (path === "/api/v1/recipes/collections" && method === "GET") return json([collection]);
    if (path === "/api/v1/recipes/photo-stages" && method === "POST") {
      return json({ id: "00000000-0000-4000-8000-000000000109", expiresAt: "2026-03-11T18:10:00Z" }, 201);
    }
    if (path === "/api/v1/recipes" && method === "GET") return json({ items: recipe ? [recipe] : [], nextCursor: null });
    if (path === "/api/v1/recipes" && method === "POST") {
      const body = request.postDataJSON() as { title: string; description?: string | null; sourceUrl?: string | null; yieldQuantity: string; yieldUnit: string; ingredients: Array<{ originalText: string }>; instructions: Array<{ text: string }> };
      recipe = recipeDetail({
        title: body.title,
        description: body.description ?? null,
        sourceUrl: body.sourceUrl ?? null,
        yieldQuantity: body.yieldQuantity,
        yieldUnit: body.yieldUnit,
        ingredients: body.ingredients.map((ingredient, index) => ({
          ...recipeDetail().ingredients[0],
          id: `00000000-0000-4000-8000-${String(110 + index).padStart(12, "0")}`,
          position: index,
          originalText: ingredient.originalText,
        })),
        instructions: body.instructions.map((instruction, index) => ({ position: index, text: instruction.text, section: null })),
      });
      return json(recipe, 201);
    }
    if (path === `/api/v1/recipes/${recipeId}` && method === "GET") return json(recipe ?? recipeDetail());
    if (path === `/api/v1/recipes/${recipeId}/organization` && method === "PUT") {
      const body = request.postDataJSON() as { favorite: boolean; collectionIds: string[]; mealRoles: string[] };
      recipe = recipeDetail({
        ...recipe,
        favorite: body.favorite,
        collections: body.collectionIds.map((id) => ({ id, name: collection.name, position: collection.position })),
        mealRoles: body.mealRoles,
        version: Number(recipe?.version ?? 1) + 1,
      });
      return json(recipe);
    }

    if (path === "/api/v1/recipes" && method === "GET") return json({ items: recipe ? [recipe] : [], nextCursor: null });
    if (path === `/api/v1/meal-plans/${weekStart}/entries` && method === "POST") {
      const body = request.postDataJSON() as { recipeId: string; localDate: string; mealSlot: string; servings: string; position: number };
      entry = {
        id: entryId,
        ...body,
        recipeTitle: String(recipe?.title ?? "Lemon lentils"),
        nutrition: { basisServings: body.servings, caloriesKcal: "540", proteinG: "38.5", carbohydrateG: "62", fatG: "14", status: "estimated", coverageRatio: "0.950000" },
        origin: "manual",
        version: 1,
      };
      return json(entry, 201);
    }
    if (path === `/api/v1/meal-plans/${weekStart}` && method === "GET") {
      const entries = entry ? [entry] : [];
      return json({
        id: "00000000-0000-4000-8000-000000000110",
        weekStart,
        timezone: "America/Vancouver",
        goal: null,
        entries,
        dayTotals: entry ? { "2026-03-11": { caloriesKcal: "540", proteinG: "38.5", carbohydrateG: "62", fatG: "14", status: "estimated", coverageRatio: "0.950000", targetDifference: null } } : {},
        weekTotal: { caloriesKcal: entry ? "540" : "0", proteinG: entry ? "38.5" : "0", carbohydrateG: entry ? "62" : "0", fatG: entry ? "14" : "0", status: "estimated", coverageRatio: "0.950000" },
        groceryStatus: entry ? groceryStatus : "absent",
        version: entry ? 2 : 1,
      });
    }

    if (path === "/api/v1/grocery-shopping-stops" && method === "GET") return json(stop ? [stop] : []);
    if (path === "/api/v1/grocery-shopping-stops" && method === "POST") {
      const body = request.postDataJSON() as { name: string };
      stop = { id: groceryStopId, name: body.name, position: 0, version: 1 };
      return json(stop, 201);
    }
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list` && method === "GET") {
      groceryItem ??= {
        id: groceryItemId,
        displayName: "Red lentils",
        quantity: "1",
        unit: "cup",
        origin: "generated",
        checked: false,
        needsReview: false,
        position: 0,
        sources: [{ mealPlanEntryId: entryId, originalText: "1 cup red lentils", quantityContribution: "1" }],
        version: 1,
        shoppingStop: null,
      };
      return json({ id: groceryListId, weekStart, status: groceryStatus, generatedAt: "2026-03-11T18:00:00Z", items: [groceryItem], version: groceryVersion });
    }
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list` && method === "POST") {
      groceryStatus = "current";
      groceryVersion += 1;
      return json({ id: groceryListId, weekStart, status: groceryStatus, generatedAt: "2026-03-11T18:00:00Z", items: groceryItem ? [groceryItem] : [], version: groceryVersion });
    }
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list/complete` && method === "POST") {
      groceryStatus = "completed";
      groceryVersion += 1;
      return json({ id: groceryListId, weekStart, status: groceryStatus, generatedAt: "2026-03-11T18:00:00Z", items: groceryItem ? [groceryItem] : [], version: groceryVersion });
    }
    if (path === `/api/v1/grocery-items/${groceryItemId}` && method === "PATCH") {
      const body = request.postDataJSON() as { checked?: boolean; shoppingStopId?: string | null };
      groceryItem = {
        ...groceryItem,
        ...body,
        shoppingStop: body.shoppingStopId ? stop : groceryItem?.shoppingStop ?? null,
        version: Number(groceryItem?.version ?? 0) + 1,
      };
      delete groceryItem.shoppingStopId;
      return json(groceryItem);
    }
    return json({ code: "not_found", title: "Not found" }, 404);
  });

  return {
    snapshot: () => ({ recipe, entry, groceryStatus, stop, groceryItem }),
  };
}

test("takes a first kitchen from recipe and cover through a finished shopping pass", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Individual recipe, planner, and grocery specs cover narrow layouts.");
  const api = await mockFirstKitchenApi(page);

  await page.goto("/app/recipes/new");
  await page.getByLabel("Recipe title").fill("Lemon lentils");
  await page.getByLabel("Yield quantity").fill("2.000");
  await page.getByRole("textbox", { name: "ingredient 1 for main recipe", exact: true }).fill("1 cup red lentils");
  await page.locator('input[type="file"]').setInputFiles({
    name: "lentils.png",
    mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9JbM8AAAAASUVORK5CYII=", "base64"),
  });
  await expect(page.getByText("Photo ready to save")).toBeVisible();
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByRole("heading", { name: "Lemon lentils" })).toBeVisible();

  await page.getByText("Keep this easy to find").click();
  await page.getByLabel("Favorite this recipe").check();
  await page.getByRole("checkbox", { name: "Weeknight favourites", exact: true }).check();
  await page.getByRole("checkbox", { name: "dinner", exact: true }).check();
  await page.getByRole("button", { name: "Save organization" }).click();
  await expect(page.getByText("Weeknight favourites", { exact: true }).first()).toBeVisible();

  await page.goto("/app/plan");
  await page.getByRole("tab", { name: "Day" }).click();
  await page.getByRole("button", { name: "Add a recipe to Dinner" }).click();
  await page.getByRole("button", { name: "Add Lemon lentils to Dinner" }).click();
  await expect(page.getByText("Meal added to your plan.")).toBeVisible();

  await page.goto("/app/grocery");
  await expect(page.getByRole("heading", { name: "Everything you need this week" })).toBeVisible();
  await page.getByRole("button", { name: "Refresh from plan" }).click();
  await expect(page.getByText("Ready to shop")).toBeVisible();
  await page.getByText("Shop by stop", { exact: true }).click();
  await page.getByLabel("New stop").fill("Market");
  await page.getByRole("button", { name: "Add stop" }).click();
  await page.getByLabel("Edit Red lentils").click();
  await page.getByLabel("Shopping stop for Red lentils").selectOption({ label: "Market" });
  await page.getByRole("checkbox", { name: "Red lentils purchased" }).check();
  await page.getByRole("button", { name: "Finish this shopping pass" }).click();
  await page.getByRole("button", { name: "Finish shopping pass" }).click();
  await expect(page.getByText("This shopping pass is complete")).toBeVisible();

  expect(api.snapshot()).toMatchObject({
    recipe: { imageUrl: expect.any(String), favorite: true, mealRoles: ["dinner"] },
    entry: { recipeId, recipeTitle: "Lemon lentils", mealSlot: "dinner" },
    groceryStatus: "completed",
    stop: { name: "Market" },
    groceryItem: { checked: true, shoppingStop: { id: groceryStopId } },
  });
});
