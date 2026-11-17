import { expect, type Page, test } from "@playwright/test";

const base = {
  normalizedFoodName: "x",
  foodReferenceId: null,
  ownerFoodId: null,
  matchStatus: "unmatched",
  matchConfidence: null,
  quantity: "1",
  unit: "pc",
  version: 1,
};

const items = [
  { ...base, id: "00000000-0000-4000-8000-000000000601", displayName: "Kimchi", expiresOn: "2026-03-18", expirySource: "model" },
  { ...base, id: "00000000-0000-4000-8000-000000000602", displayName: "Yogurt", expiresOn: "2026-03-14", expirySource: "label" },
  { ...base, id: "00000000-0000-4000-8000-000000000603", displayName: "Tortillas", expiresOn: "2026-03-10", expirySource: "model" },
  { ...base, id: "00000000-0000-4000-8000-000000000604", displayName: "Rice", expiresOn: null, expirySource: null },
  { ...base, id: "00000000-0000-4000-8000-000000000605", displayName: "Honey", expiresOn: "2026-09-11", expirySource: "auto" },
];

async function mockApi(page: Page) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  await page.context().addCookies([{ name: "cookfully_csrf", value: "pantry-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/owner/preferences") return route.fulfill({ json: { timezone: "UTC", weekStartsOn: 1, version: 1 } });
    if (path === "/api/v1/pantry-items") return route.fulfill({ json: items });
    if (path === "/api/v1/pantry/recipe-matches") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

const card = (page: Page, name: string) => page.getByRole("article", { name, exact: true });

test("a model-estimated use-by date is marked estimated and explained; label, automatic and missing dates are not", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/pantry");
  const kimchi = card(page, "Kimchi").locator(".pantry-staple__useby");
  await expect(kimchi).toContainText("(estimated)");
  await expect(kimchi).toHaveAttribute("aria-label", /estimated by a decision model/);
  await expect(kimchi).toHaveAttribute("title", /edit it if you know better/);

  await expect(card(page, "Yogurt").locator(".pantry-staple__useby")).not.toContainText("(estimated)");
  await expect(card(page, "Honey").locator(".pantry-staple__useby")).not.toContainText("(estimated)");
  await expect(card(page, "Rice").locator(".pantry-staple__useby")).toContainText("No use-by date");
});

test("an estimated date that has already passed still reads as an estimate and as expired", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/pantry");
  const tortillas = card(page, "Tortillas").locator(".pantry-staple__useby");
  await expect(tortillas).toContainText("(estimated)");
  await expect(tortillas).toHaveClass(/pantry-staple__useby--critical/);
});

test("the estimate chip does not block opening the item to correct it", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/pantry");
  await card(page, "Kimchi").getByRole("button").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("the pantry page has no horizontal overflow with estimated dates", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/pantry");
  await expect(card(page, "Kimchi")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
