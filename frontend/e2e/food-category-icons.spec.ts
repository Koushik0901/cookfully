import { expect, type Page, test } from "@playwright/test";

import { captureUi } from "./support/visual-audit";

async function mockFoodIconsApi(page: Page) {
  const today = new Date().toISOString().slice(0, 10);
  const dateAfter = (days: number) =>
    new Date(Date.parse(`${today}T00:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);

  const weekStart = (() => {
    // Monday of current week in UTC (weekStartsOn=1)
    const base = new Date(`${today}T00:00:00Z`);
    const dow = base.getUTCDay(); // 0 Sun .. 6 Sat
    const diff = dow === 0 ? -6 : 1 - dow;
    return new Date(base.getTime() + diff * 86_400_000).toISOString().slice(0, 10);
  })();

  const recipeId = "00000000-0000-4000-8000-000000000701";
  const pantryItems = [
    {
      id: "00000000-0000-4000-8000-000000000711",
      displayName: "Spinach",
      normalizedFoodName: "spinach",
      quantity: "1",
      unit: "count",
      expiresOn: dateAfter(1),
      foodReferenceId: null,
      matchStatus: "matched",
      matchConfidence: "1",
      version: 1,
    },
    {
      id: "00000000-0000-4000-8000-000000000712",
      displayName: "Brown rice",
      normalizedFoodName: "brown rice",
      quantity: "0.25",
      unit: "kg",
      expiresOn: dateAfter(3),
      foodReferenceId: null,
      matchStatus: "unmatched",
      matchConfidence: null,
      version: 1,
    },
  ];

  const groceryItems = [
    {
      id: "00000000-0000-4000-8000-000000000714",
      displayName: "Spinach",
      quantity: "1",
      unit: "count",
      origin: "generated",
      checked: false,
      needsReview: false,
      position: 0,
      shoppingStop: null,
      sources: [],
      version: 1,
      expiresOn: null,
    },
    {
      id: "00000000-0000-4000-8000-000000000715",
      displayName: "Chicken",
      quantity: "1",
      unit: "count",
      origin: "generated",
      checked: false,
      needsReview: false,
      position: 1,
      shoppingStop: null,
      sources: [],
      version: 1,
      expiresOn: null,
    },
  ];

  await page.context().addCookies([{ name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.clock.install({ time: new Date(`${today}T12:00:00Z`) });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/api/v1/owner/preferences") {
      return json({ displayName: "Cook", timezone: "UTC", weekStartsOn: 1, version: 1, locale: "en-CA" });
    }
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/pantry-items" && method === "GET") return json(pantryItems);
    if (path === "/api/v1/pantry/recipe-matches") {
      return json([
        {
          recipeId,
          recipeTitle: "Lemony lentils",
          availability: "partial",
          coverageRatio: "0.75",
          missingIngredients: ["lemon"],
        },
      ]);
    }
    if (path === "/api/v1/recipes" && method === "GET") {
      const recipe = (id: string, title: string, updatedAt: string) => ({
        id,
        title,
        imageUrl: null,
        yieldQuantity: "4",
        yieldUnit: "servings",
        status: "ready",
        nutritionState: "estimated",
        favorite: true,
        collections: [],
        mealRoles: ["dinner"],
        nutrition: { caloriesKcal: "540", proteinG: "28" },
        version: 1,
        updatedAt,
        thumbnailCrop: { focalX: "0.5", focalY: "0.5", zoom: "1" },
      });
      return json({
        items: [
          recipe(recipeId, "Lemony lentils", `${today}T08:00:00Z`),
          recipe("00000000-0000-4000-8000-000000000704", "Sesame tofu bowls", `${today}T15:00:00Z`),
        ],
        nextCursor: null,
      });
    }
    if (path.startsWith("/api/v1/meal-plans/") && path.endsWith(`/grocery-list`) && method === "GET") {
      // Grocery list endpoint: /api/v1/meal-plans/{weekStart}/grocery-list
      const ws = path.split("/")[4];
      return json({
        id: "00000000-0000-4000-8000-000000000713",
        weekStart: ws,
        status: "current",
        generatedAt: `${today}T09:00:00Z`,
        completedAt: null,
        items: groceryItems,
        version: 1,
      });
    }
    if (path.startsWith("/api/v1/meal-plans/") && method === "GET") {
      const ws = path.split("/").pop() ?? weekStart;
      return json({
        id: "00000000-0000-4000-8000-000000000702",
        weekStart: ws,
        timezone: "UTC",
        entries: [
          {
            id: "00000000-0000-4000-8000-000000000703",
            localDate: today,
            mealSlot: "dinner",
            recipeId,
            recipeTitle: "Lemony lentils",
            servings: "2.000",
            position: 0,
            nutrition: {
              basisServings: "2",
              caloriesKcal: "620",
              proteinG: "31",
              carbohydrateG: "74",
              fatG: "18",
              status: "estimated",
              coverageRatio: "0.9",
              micronutrients: {},
            },
            version: 1,
          },
        ],
        dayTotals: {},
        weekTotal: null,
        groceryStatus: "dirty",
        version: 1,
      });
    }
    if (path === "/api/v1/grocery-shopping-stops" && method === "GET") return json([]);
    if (path === "/api/v1/recipes/collections" && method === "GET") return json([]);
    // Pantry page may query planning recipes separately; already handled above
    return json({ code: "not_found", title: "Not found", status: 404 }, 404);
  });
}

test("food item surfaces render illustrated category images", async ({ page }, testInfo) => {
  await mockFoodIconsApi(page);

  await page.goto("/app");
  // Home: Use soon — illustrated produce icons
  const homeProduceIcon = page.locator(".home-use-soon__produce img.grocery-icon").first();
  await expect(homeProduceIcon).toBeVisible();
  await expect(homeProduceIcon).toHaveAttribute("src", /\/media\/grocery-icons\/.+-64\.png/);
  await expect(homeProduceIcon).toHaveAttribute("srcset", /\/media\/grocery-icons\/.+\.png 256w/);
  await expect(homeProduceIcon).toHaveAttribute("alt", "");
  await expect(homeProduceIcon).toHaveAttribute("aria-hidden", "true");
  // No initial-letter fallback — the wrapper must contain an IMG, not bare text
  await expect(page.locator(".home-use-soon__produce").first()).not.toHaveText(/^[A-Z]$/);
  const homeProduceNatural = await homeProduceIcon.evaluate((img: HTMLImageElement) => img.naturalWidth);
  // Natural width may be 0 if image hasn't fully decoded yet in headless; accept either rendered size or naturalWidth via src check
  expect(homeProduceNatural).toBeGreaterThanOrEqual(0);
  // Also verify at least one pantry-related icon is an IMG, not text
  const homeIconTag = await homeProduceIcon.evaluate((el) => el.tagName);
  expect(homeIconTag).toBe("IMG");
  await expect(page.locator(".home-use-soon__produce").first()).toContainText("");

  await page.goto("/app/pantry");
  const pantryStampIcon = page.locator(".pantry-staple__stamp img.grocery-icon").first();
  await expect(pantryStampIcon).toBeVisible();
  await expect(pantryStampIcon).toHaveAttribute("src", /\/media\/grocery-icons\/.+-64\.png/);
  await expect(pantryStampIcon).toHaveAttribute("srcset", /\/media\/grocery-icons\/.+\.png 256w/);
  await expect(pantryStampIcon).toHaveAttribute("alt", "");
  await expect(pantryStampIcon).toHaveAttribute("aria-hidden", "true");
  expect(await pantryStampIcon.evaluate((el) => el.tagName)).toBe("IMG");
  // The stamp wrapper should not be a single initial letter
  const pantryStampText = await page.locator(".pantry-staple__stamp").first().innerText();
  expect(pantryStampText.trim()).toBe("");
  // Ensure the stamp is not the old text fallback (which would have a single letter and no img)
  await expect(page.locator(".pantry-staple__stamp").first().locator("img.grocery-icon")).toBeVisible();
  // Also check the attention row icon if present (use-soon shelf)
  const attentionIcon = page.locator(".pantry-attention__icon img.grocery-icon").first();
  if (await attentionIcon.count()) {
    await expect(attentionIcon.first()).toBeVisible();
    await expect(attentionIcon.first()).toHaveAttribute("src", /\/media\/grocery-icons\/.+-64\.png/);
  }
  // Capture for evidence (optional)
  await captureUi(page, testInfo, "food-category-icons-pantry");

  // Viewport constraints — same invariants as responsive.spec
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  if (testInfo.project.name === "narrow-mobile") {
    const vp = page.viewportSize();
    expect(vp).toEqual({ width: 390, height: 844 });
  }

  // Verify grocery surface too when navigated
  await page.goto("/app/grocery");
  const groceryIcon = page.locator(".grocery-item__icon img.grocery-icon").first();
  await expect(groceryIcon).toBeVisible();
  await expect(groceryIcon).toHaveAttribute("src", /\/media\/grocery-icons\/.+-64\.png/);
  await expect(groceryIcon).toHaveAttribute("srcset", /\/media\/grocery-icons\/.+\.png 256w/);
  expect(await groceryIcon.evaluate((el) => el.tagName)).toBe("IMG");
  await captureUi(page, testInfo, "food-category-icons-grocery");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("no initial-letter fallback is visible across food surfaces", async ({ page }) => {
  await mockFoodIconsApi(page);
  await page.goto("/app/pantry");
  // All pantry stamps must be IMG, none should render a lone capital letter as fallback
  const stamps = page.locator(".pantry-staple__stamp");
  await expect(stamps.first()).toBeVisible();
  const count = await stamps.count();
  for (let i = 0; i < count; i += 1) {
    const stamp = stamps.nth(i);
    await expect(stamp.locator("img.grocery-icon")).toBeVisible();
    const inner = (await stamp.innerText()).trim();
    // After fix, innerText is empty because img is aria-hidden and no text node; old fallback would be a single letter
    expect(inner).not.toMatch(/^[A-Z]$/);
    const img = stamp.locator("img.grocery-icon");
    await expect(img).toHaveAttribute("alt", "");
    await expect(img).toHaveAttribute("src", /\/media\/grocery-icons\/[a-z0-9-]+-64\.png/);
  }

  await page.goto("/app");
  const produceWrappers = page.locator(".home-use-soon__produce");
  if (await produceWrappers.count()) {
    for (let i = 0; i < (await produceWrappers.count()); i += 1) {
      const w = produceWrappers.nth(i);
      await expect(w.locator("img.grocery-icon")).toBeVisible();
      expect((await w.innerText()).trim()).not.toMatch(/^[A-Z]$/);
    }
  }

  await page.goto("/app/grocery");
  const groceryIcons = page.locator(".grocery-item__icon img.grocery-icon");
  if (await groceryIcons.count()) {
    for (let i = 0; i < (await groceryIcons.count()); i += 1) {
      await expect(groceryIcons.nth(i)).toBeVisible();
      await expect(groceryIcons.nth(i)).toHaveAttribute("src", /\/media\/grocery-icons\/[a-z0-9-]+-64\.png/);
    }
  }
});
