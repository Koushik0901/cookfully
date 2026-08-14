import type { Page } from "@playwright/test";

export const accessibleRecipeId = "00000000-0000-4000-8000-000000000081";

export function accessibleRecipe() {
  return {
    id: accessibleRecipeId,
    title: "A very long provider-independent training recipe title that must wrap safely",
    description: "Keyboard-accessible recipe evidence with an intentionally long description that must not create document overflow.",
    sourceUrl: null,
    imageUrl: null,
    yieldQuantity: "2.000",
    yieldUnit: "servings",
    status: "archived",
    archivedFromStatus: "ready",
    nutritionState: "estimated",
    nutrition: {
      status: "estimated",
      basisServings: "2.000",
      coverageRatio: "0.950000",
      caloriesKcal: "500.000000",
      proteinG: "40.000000",
      carbohydrateG: "60.000000",
      fatG: "12.000000",
      micronutrients: {},
      provenance: [{ kind: "reference", label: "USDA Foundation Foods", version: "2026-04" }],
      assumptions: [],
      corrections: [],
    },
    version: 4,
    updatedAt: "2026-08-10T10:00:00Z",
    ingredients: [{
      id: "00000000-0000-4000-8000-000000000082",
      position: 0,
      originalText: "200 g extra-firm tofu with a deliberately-long-unbroken-preparation-token-for-overflow-validation",
      quantityMin: "200.000000",
      quantityMax: null,
      unit: "g",
      food: "extra firm tofu",
      preparation: null,
      optional: false,
      parseStatus: "parsed",
      matchStatus: "matched",
      assumptions: [],
    }],
    instructions: ["Cook and portion."],
    activeJob: {
      id: "00000000-0000-4000-8000-000000000083",
      kind: "nutrition_match",
      aggregateId: accessibleRecipeId,
      status: "running",
      attempt: 1,
      maxAttempts: 5,
      inputHash: "accessible-input",
      progressCurrent: 1,
      progressTotal: 2,
      nextRetryAt: null,
      terminalDeadlineAt: "2026-08-10T10:15:00Z",
      failureCode: null,
      failureMessage: null,
      createdAt: "2026-08-10T10:00:00Z",
      finishedAt: null,
      pollAfterSeconds: 2,
      recoveryActions: ["wait"],
    },
  };
}

export async function mockAccessibleRecipeApi(page: Page) {
  const recipe = accessibleRecipe();
  await page.context().addCookies([
    { name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" },
  ]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA" });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/auth/session" && route.request().method() === "DELETE") {
      return route.fulfill({ status: 204 });
    }
    if (path === `/api/v1/recipes/${accessibleRecipeId}`) return json(recipe);
    if (path === `/api/v1/jobs/${recipe.activeJob.id}`) return json(recipe.activeJob);
    if (path === `/api/v1/recipes/${accessibleRecipeId}/permanent`) {
      return route.fulfill({ status: 204 });
    }
    return json({ code: "not_found", status: 404, title: "Not found" }, 404);
  });
}
