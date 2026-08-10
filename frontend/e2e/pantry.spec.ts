import { expect, type Page, test } from "@playwright/test";

async function mockPantryApi(page: Page) {
  let pantry = [
    {
      id: "00000000-0000-4000-8000-000000000601",
      displayName: "Brown rice",
      normalizedFoodName: "brown rice",
      quantity: "0.25",
      unit: "kg",
      foodReferenceId: null,
      matchStatus: "unmatched",
      matchConfidence: null,
      version: 1,
    },
  ];
  await page.context().addCookies([
    { name: "vv_csrf", value: "pantry-csrf", domain: "127.0.0.1", path: "/" },
  ]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/owner/preferences") {
      return route.fulfill({ json: { timezone: "America/Vancouver", weekStartsOn: 1, version: 1 } });
    }
    if (path === "/api/v1/pantry-items" && request.method() === "GET") {
      return route.fulfill({ json: pantry });
    }
    if (path === "/api/v1/pantry-items" && request.method() === "POST") {
      const value = request.postDataJSON();
      pantry = [...pantry, { id: "00000000-0000-4000-8000-000000000602", normalizedFoodName: "black beans", foodReferenceId: null, matchStatus: "unmatched", matchConfidence: null, version: 1, ...value }];
      return route.fulfill({ status: 201, json: pantry.at(-1) });
    }
    if (path === "/api/v1/pantry/recipe-matches") {
      return route.fulfill({ json: [{ recipeId: "00000000-0000-4000-8000-000000000603", recipeTitle: "Chicken rice", availability: "partial", coverageRatio: "0.5", missingIngredients: ["400 g chicken breast"] }] });
    }
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

test("manages pantry quantities and shows explicit recipe gaps without mobile overflow", async ({ page }) => {
  await mockPantryApi(page);
  await page.goto("/app/pantry");
  await expect(page.getByRole("heading", { name: "Pantry" })).toBeVisible();
  await expect(page.getByRole("article", { name: "Brown rice" })).toContainText("0.25 kg");

  await page.getByLabel("Food name").fill("Black beans");
  await page.getByLabel("Quantity").fill("2.000000");
  await page.getByLabel("Unit").selectOption("count");
  await page.getByRole("button", { name: "Add pantry item" }).click();
  await expect(page.getByRole("article", { name: "Black beans" })).toContainText("2 count");

  await page.getByRole("button", { name: "Find makeable recipes" }).click();
  await expect(page.getByRole("article", { name: "Chicken rice" })).toContainText("Partially makeable");
  await expect(page.getByRole("article", { name: "Chicken rice" })).toContainText("400 g chicken breast");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
