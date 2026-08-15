import { expect, type Page, test } from "@playwright/test";
import { captureUi } from "./support/visual-audit";

async function mockOnboarding(page: Page, { unavailable = false, hasRecipe = false, hasArchivedRecipe = false }: { unavailable?: boolean; hasRecipe?: boolean; hasArchivedRecipe?: boolean } = {}) {
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
    if (path === "/api/v1/recipes" && method === "GET") return route.fulfill({ json: { items: hasRecipe || hasArchivedRecipe ? [{ id: "00000000-0000-4000-8000-000000000001", title: "Tomato soup", imageUrl: null, yieldQuantity: "2", yieldUnit: "servings", status: hasArchivedRecipe ? "archived" : "ready", nutritionState: "estimated", favorite: false, collections: [], mealRoles: [], nutrition: null, version: 1, updatedAt: "2026-08-13T00:00:00Z" }] : [], nextCursor: null } });
    if (path === "/api/v1/recipes/collections" && method === "GET") return route.fulfill({ json: [] });
    if (path === "/api/v1/reference-data/status") return route.fulfill({ json: { available: false, missing: ["foundation", "sr_legacy"], releases: [], requestedDatasets: null, job: null } });
    if (path === "/api/v1/reference-data/install" && method === "POST") return route.fulfill({ status: 202, json: { jobId: "00000000-0000-4000-8000-000000000009", status: "queued" } });
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

test("first-run guidance is direct, dismissible, and never blocks the kitchen", async ({ page }, testInfo) => {
  await mockOnboarding(page);
  await page.goto("/app/plan");
  await expect(page.getByRole("heading", { name: "Start with a recipe you already love." })).toHaveCount(0);
  await page.goto("/app/recipes");
  await expect(page.getByRole("heading", { name: "Start with a recipe you already love." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What would you like to cook?" })).toHaveCount(0);
  await captureUi(page, testInfo, "onboarding-first-run");
  await page.getByRole("button", { name: "Skip welcome" }).click();
  await expect(page.getByRole("heading", { name: "Start with a recipe you already love." })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "No recipes yet" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Create recipe" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Import recipe" })).toHaveCount(1);
  await captureUi(page, testInfo, "recipes-empty");
  await page.getByRole("link", { name: "Plan" }).click();
  await expect(page).toHaveURL(/\/app\/plan$/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("pending onboarding never replaces an established recipe library", async ({ page }) => {
  await mockOnboarding(page, { hasRecipe: true });
  await page.goto("/app/recipes");

  await expect(page.getByRole("heading", { name: "Tomato soup" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Start with a recipe you already love." })).toHaveCount(0);
});

test("archived recipes keep a pending welcome from treating the kitchen as new", async ({ page }) => {
  await mockOnboarding(page, { hasArchivedRecipe: true });
  await page.goto("/app/recipes");

  await expect(page.getByRole("heading", { name: "Start with a recipe you already love." })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "No active recipes" })).toBeVisible();
  await page.getByRole("button", { name: "View archived recipes" }).click();
  await expect(page.getByRole("heading", { name: "Tomato soup" })).toBeVisible();
});

test("an unavailable welcome preference never interrupts an existing kitchen", async ({ page }) => {
  await mockOnboarding(page, { unavailable: true });
  await page.goto("/app/recipes");
  await expect(page.getByRole("heading", { level: 1, name: "No recipes yet" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Create recipe" })).toBeVisible();
  await expect(page.getByText("Preparing your kitchen")).toHaveCount(0);
  await expect(page.getByText("Your welcome guide could not be loaded")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("onboarding offers the nutrition data choice and continues after install", async ({ page }, testInfo) => {
  await mockOnboarding(page);
  await page.goto("/app/recipes");
  await page.getByRole("button", { name: "Set up nutrition data" }).click();
  await expect(page.getByRole("heading", { name: "Real nutrition numbers?" })).toBeVisible();
  await captureUi(page, testInfo, "onboarding-nutrition-step");
  await page.getByRole("button", { name: "Foundation + SR Legacy only" }).click();
  await expect(page).toHaveURL(/\/app\/recipes$/);
  await expect(page.getByRole("heading", { name: "No recipes yet" })).toBeVisible();
});
