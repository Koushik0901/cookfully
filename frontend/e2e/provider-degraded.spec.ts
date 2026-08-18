import { expect, type Page, test } from "@playwright/test";

const recipeId = "00000000-0000-4000-8000-000000000091";
const jobId = "00000000-0000-4000-8000-000000000092";

function failedRecipe() {
  return {
    id: recipeId,
    title: "Provider-degraded bowl",
    description: "The stored recipe remains editable.",
    sourceUrl: "https://example.com/provider-degraded",
    imageUrl: null,
    yieldQuantity: "2.000",
    yieldUnit: "servings",
    status: "failed",
    archivedFromStatus: null,
    nutritionState: "failed",
    nutrition: null,
    version: 2,
    updatedAt: "2026-08-10T10:00:00Z",
    ingredients: [{
      id: "00000000-0000-4000-8000-000000000093",
      position: 0,
      originalText: "200 g tofu",
      quantityMin: "200.000000",
      quantityMax: null,
      unit: "g",
      food: "tofu",
      preparation: null,
      optional: false,
      parseStatus: "parsed",
      matchStatus: "ambiguous",
      assumptions: [],
    }],
    instructions: ["Cook and portion."],
    activeJob: {
      id: jobId,
      kind: "nutrition_match",
      aggregateId: recipeId,
      status: "failed",
      attempt: 1,
      maxAttempts: 5,
      inputHash: "provider-degraded-input",
      progressCurrent: null,
      progressTotal: null,
      nextRetryAt: null,
      terminalDeadlineAt: "2026-08-10T10:15:00Z",
      failureCode: "ai_provider_timeout",
      failureMessage: "Optional provider timed out; deterministic work was kept.",
      createdAt: "2026-08-10T10:00:00Z",
      finishedAt: "2026-08-10T10:00:05Z",
      pollAfterSeconds: null,
      recoveryActions: ["edit_recipe", "enter_manual_nutrition"],
    },
  };
}

async function mockDegradedApi(page: Page) {
  type RecipeFixture = Omit<ReturnType<typeof failedRecipe>, "nutrition" | "activeJob"> & {
    nutrition: unknown;
    activeJob: unknown;
  };
  let recipe: RecipeFixture = failedRecipe();
  await page.context().addCookies([
    { name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" },
  ]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA" });
    if (path === `/api/v1/recipes/${recipeId}` && request.method() === "GET") return json(recipe);
    if (path === `/api/v1/jobs/${jobId}`) return json(recipe.activeJob);
    if (path === `/api/v1/recipes/${recipeId}/nutrition/corrections`) {
      const correction = {
        id: "00000000-0000-4000-8000-000000000094",
        ...request.postDataJSON(),
        active: true,
        createdAt: "2026-08-10T10:01:00Z",
      };
      const nutrition = {
        status: "manual",
        basisServings: "2.000",
        coverageRatio: "0.250000",
        caloriesKcal: null,
        proteinG: "40.000000",
        carbohydrateG: null,
        fatG: null,
        micronutrients: {},
        provenance: [{ kind: "manual", label: "Owner correction", version: null }],
        assumptions: ["Provider output was not used."],
        corrections: [correction],
      };
      recipe = { ...recipe, nutritionState: "estimated", nutrition, activeJob: null };
      return json(nutrition, 201);
    }
    if (path === `/api/v1/recipes/${recipeId}` && request.method() === "PATCH") {
      const body = request.postDataJSON();
      recipe = {
        ...recipe,
        ...body,
        status: "processing",
        nutritionState: "stale",
        version: 3,
        ingredients: recipe.ingredients.map((ingredient) => ({
          ...ingredient,
          originalText: body.ingredients[0].originalText,
        })),
        activeJob: null,
      };
      return json(recipe);
    }
    return json({ code: "not_found", status: 404, title: "Not found" }, 404);
  });
}

test("provider failure stays explicit while edit and manual nutrition recovery remain usable", async ({ page }, testInfo) => {
  await mockDegradedApi(page);
  await page.goto(`/app/recipes/${recipeId}`);

  await expect(page.getByText(/deterministic work was kept/i).first()).toBeVisible();
  await page.getByText("Nutrition details and evidence").click();
  await expect(page.getByLabel("Nutrition processing status").getByText("failed")).toBeVisible();
  await expect(page.getByText(/planning aid, not medical advice/i)).toBeVisible();
  await expect(page.getByRole("link", { name: "Edit recipe" })).toBeVisible();

  await page.getByRole("link", { name: "Edit nutrition" }).click();
  if (testInfo.project.name === "narrow-mobile") await expect(page.getByRole("button", { name: "Nutrition" })).toHaveAttribute("aria-current", "step");
  await page.getByLabel("Protein (g)").fill("40.000000");
  await page.getByLabel("Source or reason").fill("Package label after provider failure");
  await page.getByRole("button", { name: "Save recipe" }).click();
  await page.getByText("Nutrition details and evidence").click();
  await expect(page.getByText("Package label after provider failure")).toBeVisible();

  await page.getByRole("link", { name: "Edit recipe" }).click();
  if (testInfo.project.name === "narrow-mobile") await page.getByRole("button", { name: "Ingredients" }).click();
  await page.getByLabel("Ingredients, one per line").fill("250 g tofu");
  if (testInfo.project.name === "narrow-mobile") await page.getByRole("button", { name: "Method" }).click();
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByRole("heading", { name: "Provider-degraded bowl" })).toBeVisible();
  await expect(page.locator(".nutrition-state").filter({ hasText: "Needs review" }).first()).toBeVisible();

  await expect(page.getByRole("link", { name: "Plan" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Grocery" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
