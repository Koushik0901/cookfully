import { expect, type Page, test } from "@playwright/test";

async function mockOnboarding(page: Page, { unavailable = false }: { unavailable?: boolean } = {}) {
  let state: "pending" | "completed" | "dismissed" = "pending";
  await page.context().addCookies([{ name: "cookfully_csrf", value: "onboarding-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path === "/api/v1/owner/onboarding" && method === "GET") return unavailable ? route.fulfill({ status: 503, json: { code: "temporarily_unavailable", title: "Unavailable" } }) : route.fulfill({ json: { state, version: 1 } });
    if (path === "/api/v1/owner/onboarding" && method === "PUT") {
      state = route.request().postDataJSON().state;
      return route.fulfill({ json: { state, version: 2 } });
    }
    if (path === "/api/v1/owner/preferences") return route.fulfill({ json: { displayName: "Cook", timezone: "America/Vancouver", weekStartsOn: 1, version: 1 } });
    if (path === "/api/v1/recipes" && method === "GET") return route.fulfill({ json: { items: [], nextCursor: null } });
    if (path === "/api/v1/recipes/collections" && method === "GET") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

test("first-run guidance is direct, dismissible, and never blocks the kitchen", async ({ page }) => {
  await mockOnboarding(page);
  await page.goto("/app/recipes");
  await expect(page.getByRole("heading", { name: "Start with the food you already know." })).toBeVisible();
  await page.getByRole("button", { name: "Skip for now" }).click();
  await expect(page.getByRole("heading", { name: "Start with the food you already know." })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "No matching recipes" })).toBeVisible();
  await page.getByRole("link", { name: "Plan" }).click();
  await expect(page).toHaveURL(/\/app\/plan$/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("an unavailable welcome preference never interrupts an existing kitchen", async ({ page }) => {
  await mockOnboarding(page, { unavailable: true });
  await page.goto("/app/recipes");
  await expect(page.getByRole("heading", { name: "What would you like to cook?" })).toBeVisible();
  await expect(page.getByText("Preparing your kitchen")).toHaveCount(0);
  await expect(page.getByText("Your welcome guide could not be loaded")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
