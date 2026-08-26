import { expect, type Page, test } from "@playwright/test";

import { captureUi } from "./support/visual-audit";

const recipeId = "00000000-0000-4000-8000-000000000701";

async function mockHome(page: Page) {
  const today = new Date().toISOString().slice(0, 10);
  const dateAfter = (days: number) => new Date(Date.parse(`${today}T00:00:00Z`) + (days * 86_400_000)).toISOString().slice(0, 10);
  await page.context().addCookies([{ name: "cookfully_csrf", value: "home-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/owner/home") {
      const recipe = (id: string, title: string, updatedAt: string, mealRole: string) => ({
        id,
        title,
        sourceUrl: null,
        imageUrl: null,
        yieldQuantity: "4",
        yieldUnit: "servings",
        status: "ready",
        archivedFromStatus: null,
        nutritionState: "estimated",
        favorite: true,
        collections: [],
        mealRoles: [mealRole],
        nutrition: { caloriesKcal: "540", proteinG: "28" },
        version: 1,
        updatedAt,
        thumbnailCrop: { x: "0.5", y: "0.5", zoom: "1" },
      });
      return route.fulfill({ json: {
        preferences: { displayName: "Cook", timezone: "UTC", weekStartsOn: 1, version: 1 },
        recipes: { items: [
          recipe(recipeId, "Lemony lentils", `${today}T08:00:00Z`, "dinner"),
          recipe("00000000-0000-4000-8000-000000000704", "Sesame tofu bowls", `${today}T15:00:00Z`, "dinner"),
          recipe("00000000-0000-4000-8000-000000000705", "Roasted tomato pasta", `${today}T14:00:00Z`, "weeknight"),
          recipe("00000000-0000-4000-8000-000000000706", "Ginger lentil soup", `${today}T13:00:00Z`, "batch cook"),
        ], nextCursor: null },
        pantry: [
          { id: "00000000-0000-4000-8000-000000000711", displayName: "Spinach", normalizedFoodName: "spinach", quantity: "1", unit: "count", expiresOn: dateAfter(1), matchStatus: "matched", matchConfidence: "1", version: 1 },
          { id: "00000000-0000-4000-8000-000000000712", displayName: "Heavy cream", normalizedFoodName: "heavy cream", quantity: "250", unit: "ml", expiresOn: dateAfter(3), matchStatus: "matched", matchConfidence: "1", version: 1 },
        ],
        plan: {
          id: "00000000-0000-4000-8000-000000000702",
          weekStart: today,
          timezone: "UTC",
          entries: [
            { id: "00000000-0000-4000-8000-000000000703", localDate: today, mealSlot: "dinner", recipeId, recipeTitle: "Lemony lentils", servings: "2.000", position: 0, nutrition: { basisServings: "2", caloriesKcal: "620", proteinG: "31", carbohydrateG: "74", fatG: "18", status: "estimated", coverageRatio: "0.9", micronutrients: {} }, version: 1 },
            { id: "00000000-0000-4000-8000-000000000707", localDate: today, mealSlot: "breakfast", recipeId, recipeTitle: "Lemony lentils", servings: "1.000", position: 0, nutrition: { basisServings: "1", caloriesKcal: "310", proteinG: "15.5", carbohydrateG: "37", fatG: "9", status: "estimated", coverageRatio: "0.9", micronutrients: {} }, version: 1 },
          ],
          dayTotals: {}, weekTotal: null, groceryStatus: "dirty", version: 1,
        },
        grocery: {
          id: "00000000-0000-4000-8000-000000000713", weekStart: today, status: "dirty", generatedAt: `${today}T09:00:00Z`, completedAt: null,
          items: [
            { id: "00000000-0000-4000-8000-000000000714", displayName: "Lemon", quantity: "2", unit: "count", origin: "generated", checked: false, needsReview: false, position: 0, shoppingStop: null, sources: [], version: 1 },
            { id: "00000000-0000-4000-8000-000000000715", displayName: "Cilantro", quantity: "1", unit: "count", origin: "generated", checked: false, needsReview: false, position: 1, shoppingStop: null, sources: [], version: 1 },
          ], version: 1,
        },
        pantryMatches: [
          { recipeId, recipeTitle: "Lemony lentils", availability: "partial", coverageRatio: "0.75", missingIngredients: ["lemon"] },
          { recipeId: "00000000-0000-4000-8000-000000000704", recipeTitle: "Sesame tofu bowls", availability: "full", coverageRatio: "1", missingIngredients: [] },
        ],
      } });
    }
    if (path === "/api/v1/owner/preferences") {
      return route.fulfill({ json: { displayName: "Cook", timezone: "UTC", weekStartsOn: 1, version: 1 } });
    }
    if (path === "/api/v1/recipes") {
      const recipe = (id: string, title: string, updatedAt: string, mealRole: string) => ({
        id,
        title,
        imageUrl: null,
        yieldQuantity: "4",
        yieldUnit: "servings",
        status: "ready",
        nutritionState: "estimated",
        favorite: true,
        collections: [],
        mealRoles: [mealRole],
        nutrition: { caloriesKcal: "540", proteinG: "28" },
        version: 1,
        updatedAt,
        thumbnailCrop: { focalX: "0.5", focalY: "0.5", zoom: "1" },
      });
      return route.fulfill({ json: { items: [
        recipe(recipeId, "Lemony lentils", `${today}T08:00:00Z`, "dinner"),
        recipe("00000000-0000-4000-8000-000000000704", "Sesame tofu bowls", `${today}T15:00:00Z`, "dinner"),
        recipe("00000000-0000-4000-8000-000000000705", "Roasted tomato pasta", `${today}T14:00:00Z`, "weeknight"),
        recipe("00000000-0000-4000-8000-000000000706", "Ginger lentil soup", `${today}T13:00:00Z`, "batch cook"),
      ], nextCursor: null } });
    }
    if (path === "/api/v1/pantry-items") {
      return route.fulfill({ json: [
        { id: "00000000-0000-4000-8000-000000000711", displayName: "Spinach", normalizedFoodName: "spinach", quantity: "1", unit: "count", expiresOn: dateAfter(1), matchStatus: "matched", matchConfidence: "1", version: 1 },
        { id: "00000000-0000-4000-8000-000000000712", displayName: "Heavy cream", normalizedFoodName: "heavy cream", quantity: "250", unit: "ml", expiresOn: dateAfter(3), matchStatus: "matched", matchConfidence: "1", version: 1 },
      ] });
    }
    if (path.endsWith("/grocery-list")) {
      return route.fulfill({ json: {
        id: "00000000-0000-4000-8000-000000000713",
        weekStart: path.split("/").at(-2),
        status: "current",
        generatedAt: `${today}T09:00:00Z`,
        completedAt: null,
        items: [
          { id: "00000000-0000-4000-8000-000000000714", displayName: "Lemon", quantity: "2", unit: "count", origin: "generated", checked: false, needsReview: false, position: 0, shoppingStop: null, sources: [], version: 1 },
          { id: "00000000-0000-4000-8000-000000000715", displayName: "Cilantro", quantity: "1", unit: "count", origin: "generated", checked: false, needsReview: false, position: 1, shoppingStop: null, sources: [], version: 1 },
          { id: "00000000-0000-4000-8000-000000000716", displayName: "Greek yogurt", quantity: "500", unit: "g", origin: "manual", checked: true, needsReview: false, position: 2, shoppingStop: null, sources: [], version: 1 },
        ],
        version: 1,
      } });
    }
    if (path.startsWith("/api/v1/meal-plans/")) {
      return route.fulfill({ json: {
        id: "00000000-0000-4000-8000-000000000702",
        weekStart: path.split("/").at(-1),
        timezone: "UTC",
        entries: [
          { id: "00000000-0000-4000-8000-000000000703", localDate: today, mealSlot: "dinner", recipeId, recipeTitle: "Lemony lentils", servings: "2.000", position: 0, nutrition: { basisServings: "2", caloriesKcal: "620", proteinG: "31", carbohydrateG: "74", fatG: "18", status: "estimated", coverageRatio: "0.9", micronutrients: {} }, version: 1 },
          { id: "00000000-0000-4000-8000-000000000707", localDate: today, mealSlot: "breakfast", recipeId, recipeTitle: "Lemony lentils", servings: "1.000", position: 0, nutrition: { basisServings: "1", caloriesKcal: "310", proteinG: "15.5", carbohydrateG: "37", fatG: "9", status: "estimated", coverageRatio: "0.9", micronutrients: {} }, version: 1 },
        ],
        dayTotals: {},
        weekTotal: null,
        groceryStatus: "dirty",
        version: 1,
      } });
    }
    if (path === "/api/v1/pantry/recipe-matches") {
      return route.fulfill({ json: [
        { recipeId, recipeTitle: "Lemony lentils", availability: "partial", coverageRatio: "0.75", missingIngredients: ["lemon"] },
        { recipeId: "00000000-0000-4000-8000-000000000704", recipeTitle: "Sesame tofu bowls", availability: "full", coverageRatio: "1", missingIngredients: [] },
        { recipeId: "00000000-0000-4000-8000-000000000705", recipeTitle: "Roasted tomato pasta", availability: "partial", coverageRatio: "0.8", missingIngredients: ["tomatoes"] },
      ] });
    }
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

test("Home opens on tonight, the week, recent recipes, and focused quick search", async ({ page }, testInfo) => {
  await mockHome(page);
  await page.goto("/app");

  await expect(page.getByRole("heading", { name: /^Good (morning|afternoon|evening)$/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Start cooking" })).toHaveAttribute("href", `/app/recipes/${recipeId}/cook`);
  await expect(page.getByRole("heading", { name: "Two meals planned" })).toBeVisible();
  await expect(page.getByText("620 kcal")).toBeVisible();
  await expect(page.locator(".home-for-you .recipe-meta__item--calories").first()).toBeVisible();
  await expect(page.locator(".home-for-you .recipe-meta__item--protein").first()).toBeVisible();
  await expect(page.locator(".home-week-grid")).toHaveAttribute("aria-label", "1 of 7 days have planned meals");
  await expect(page.locator(".home-week-day")).toHaveCount(7);
  await expect(page.getByRole("heading", { name: "Use soon" })).toBeVisible();
  await expect(page.getByText("Spinach")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Quick actions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Cook next" })).toBeVisible();
  await expect(page.getByText("Everything you need is in your pantry")).toBeVisible();
  await expect(page.getByRole("heading", { name: "2 things to pick up" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recently saved" })).toBeVisible();
  await expect(page.locator(".home-recent-recipe .recipe-fallback-art")).toHaveCount(4);

  const mediaHeights = await page.locator(".home-recent-recipe__media").evaluateAll((items) => items.map((item) => item.getBoundingClientRect().height));
  expect(Math.max(...mediaHeights) - Math.min(...mediaHeights)).toBeLessThanOrEqual(1);
  if (testInfo.project.name === "desktop-chromium") {
    await page.setViewportSize({ width: 1934, height: 1272 });
    const home = await page.locator(".home-page").boundingBox();
    const canvas = await page.locator(".planner-shell__content").boundingBox();
    expect(home).not.toBeNull();
    expect(canvas).not.toBeNull();
    expect(home!.width / canvas!.width).toBeGreaterThan(0.9);
    expect(await page.locator(".home-page").evaluate((element) => element.scrollHeight)).toBeGreaterThan(1100);
    expect(await page.locator(".home-for-you__grid").evaluate((element) => element.getBoundingClientRect().height)).toBeLessThan(500);
    const priorities = await page.locator(".home-priorities").evaluate((element) => {
      const useSoon = element.querySelector<HTMLElement>(".home-use-soon")?.getBoundingClientRect();
      const quickActions = element.querySelector<HTMLElement>(".home-quick-actions")?.getBoundingClientRect();
      return { useSoonHeight: useSoon?.height ?? 0, quickActionsHeight: quickActions?.height ?? 0 };
    });
    expect(Math.abs(priorities.useSoonHeight - priorities.quickActionsHeight)).toBeLessThanOrEqual(24);
  }
  if (testInfo.project.name === "narrow-mobile") {
    const recentShelf = page.locator(".home-recent__grid");
    const shelfGeometry = await recentShelf.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        overflowX: style.overflowX,
        scrollbarWidth: style.scrollbarWidth,
        webkitScrollbarDisplay: getComputedStyle(element, "::-webkit-scrollbar").display,
      };
    });
    expect(shelfGeometry.overflowX).toBe("auto");
    expect(shelfGeometry.scrollWidth).toBeGreaterThan(shelfGeometry.clientWidth);
    expect(shelfGeometry.scrollbarWidth).toBe("none");
    expect(shelfGeometry.webkitScrollbarDisplay).toBe("none");
  }

  await page.keyboard.press("Control+K");
  const palette = page.getByRole("dialog", { name: "Search Cookfully" });
  await expect(palette).toBeVisible();
  await palette.getByLabel("Search Cookfully").fill("Lemony");
  await expect(palette.getByRole("menuitem", { name: /Lemony lentils/i })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(palette).toBeHidden();

  await captureUi(page, testInfo, "home-kitchen");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
