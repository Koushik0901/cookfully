import { expect, test } from "@playwright/test";

const fullId = "00000000-0000-4000-8000-0000000000a1";
const partialId = "00000000-0000-4000-8000-0000000000a2";
const noneId = "00000000-0000-4000-8000-0000000000a3";

function recipe(id: string, title: string) {
  return {
    id,
    title,
    description: null,
    sourceUrl: null,
    imageUrl: null,
    yieldQuantity: "2.000",
    yieldUnit: "servings",
    status: "ready",
    archivedFromStatus: null,
    nutritionState: "estimated",
    nutrition: null,
    version: 1,
    updatedAt: "2026-08-10T10:00:00Z",
    favorite: false,
    collections: [],
    mealRoles: [],
    ingredients: [],
    instructions: [],
    activeJob: null,
  };
}

test("shows pantry availability on cards and filters to what can be cooked now", async ({ page }) => {
  await page.context().addCookies([{ name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA" });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/recipes/collections") return json([]);
    if (path === "/api/v1/pantry/recipe-matches") {
      return json([
        { recipeId: fullId, recipeTitle: "Pantry pasta", availability: "full", coverageRatio: "1.000000", missingIngredients: [] },
        { recipeId: partialId, recipeTitle: "Lemon lentils", availability: "partial", coverageRatio: "0.700000", missingIngredients: ["lemon", "cumin"] },
      ]);
    }
    if (path === "/api/v1/recipes") {
      return json({ items: [recipe(fullId, "Pantry pasta"), recipe(partialId, "Lemon lentils"), recipe(noneId, "Beef wellington")], nextCursor: null });
    }
    return json({});
  });

  await page.goto("/app/recipes");
  const cards = page.locator(".recipe-card");
  await expect(cards).toHaveCount(3);
  await expect(cards.filter({ hasText: "Pantry pasta" }).locator(".recipe-card__pantry")).toHaveText("Can make now");
  await expect(cards.filter({ hasText: "Lemon lentils" }).locator(".recipe-card__pantry")).toHaveText("2 to buy");
  await expect(cards.filter({ hasText: "Beef wellington" }).locator(".recipe-card__pantry")).toHaveCount(0);

  const quick = page.getByRole("button", { name: /Can make now\s*1/ });
  await expect(quick).toHaveAttribute("aria-pressed", "false");
  const box = await quick.boundingBox();
  expect(box!.height).toBeGreaterThanOrEqual(44);

  await quick.click();
  await expect(quick).toHaveAttribute("aria-pressed", "true");
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText("Pantry pasta");
  const filters = page.getByLabel("Active recipe filters");
  await expect(filters.getByRole("button", { name: /Can make now/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await filters.getByRole("button", { name: /Can make now/ }).click();
  await expect(quick).toHaveAttribute("aria-pressed", "false");
  await expect(cards).toHaveCount(3);

  // Pressing the chip again and using Clear filters also restores the shelf.
  await quick.click();
  await expect(cards).toHaveCount(1);
  await filters.getByRole("button", { name: "Clear filters" }).click();
  await expect(cards).toHaveCount(3);
});

test("keeps the library usable when the pantry cannot answer", async ({ page }) => {
  await page.context().addCookies([{ name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/recipes/collections") return json([]);
    if (path === "/api/v1/pantry/recipe-matches") return json({ code: "unavailable" }, 503);
    if (path === "/api/v1/recipes") return json({ items: [recipe(fullId, "Pantry pasta")], nextCursor: null });
    return json({});
  });
  await page.goto("/app/recipes");
  await expect(page.locator(".recipe-card")).toHaveCount(1);
  await expect(page.getByRole("button", { name: /Can make now/ })).toHaveCount(0);
});
