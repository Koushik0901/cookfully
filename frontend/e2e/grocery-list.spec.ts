import { expect, type Page, test } from "@playwright/test";
import { captureUi } from "./support/visual-audit";

const weekStart = "2026-03-09";
const listId = "00000000-0000-4000-8000-000000000070";
type TestStop = { id: string; name: string; position: number; version: number };
type TestItem = {
  id: string; displayName: string; quantity: string | null; unit: string | null;
  origin: string; checked: boolean; needsReview: boolean; position: number;
  sources: Array<{ mealPlanEntryId: string; originalText: string; quantityContribution: string | null }>;
  version: number; shoppingStop?: TestStop | null; shoppingStopId?: string | null;
};

async function mockGroceryApi(page: Page, { empty = false, missing = false }: { empty?: boolean; missing?: boolean } = {}) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  let listVersion = 2;
  let status = empty ? "current" : "dirty";
  let stops: TestStop[] = [];
  const plannedEntries = [
    { id: "00000000-0000-4000-8000-000000000020", localDate: "2026-03-11", mealSlot: "dinner", recipeId: "00000000-0000-4000-8000-000000000120", recipeTitle: "Sheet-pan tofu bowls" },
    { id: "00000000-0000-4000-8000-000000000021", localDate: "2026-03-12", mealSlot: "dinner", recipeId: "00000000-0000-4000-8000-000000000121", recipeTitle: "Garlicky tomato pasta" },
  ];
  let items: TestItem[] = empty ? [] : [
    {
      id: "00000000-0000-4000-8000-000000000071",
      displayName: "Red onion",
      quantity: "750",
      unit: "g",
      origin: "generated",
      checked: false,
      needsReview: false,
      position: 0,
      sources: [
        {
          mealPlanEntryId: "00000000-0000-4000-8000-000000000020",
          originalText: "500 g red onion",
          quantityContribution: "750",
        },
      ],
      version: 1,
    },
    {
      id: "00000000-0000-4000-8000-000000000072",
      displayName: "Salt to taste",
      quantity: null,
      unit: null,
      origin: "generated",
      checked: false,
      needsReview: true,
      position: 1,
      sources: [
        {
          mealPlanEntryId: "00000000-0000-4000-8000-000000000021",
          originalText: "salt to taste",
          quantityContribution: null,
        },
      ],
      version: 1,
    },
  ];
  await page.context().addCookies([{ name: "cookfully_csrf", value: "grocery-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const grocery = () => ({ id: listId, weekStart, status, generatedAt: "2026-03-10T12:00:00Z", items, version: listVersion });
    if (path === "/api/v1/owner/preferences") return route.fulfill({ json: { timezone: "America/Vancouver", weekStartsOn: 1, version: 1 } });
    if (path === "/api/v1/owner/onboarding") return route.fulfill({ json: { state: "completed", version: 1 } });
    if (path === `/api/v1/meal-plans/${weekStart}` && method === "GET") return route.fulfill({ json: { entries: plannedEntries } });
    if (path === "/api/v1/grocery-shopping-stops" && method === "GET") return route.fulfill({ json: stops });
    if (path === "/api/v1/grocery-shopping-stops" && method === "POST") {
      const value = request.postDataJSON();
      const stop = { id: `00000000-0000-4000-8000-${String(80 + stops.length).padStart(12, "0")}`, name: value.name, position: stops.length, version: 1 };
      stops = [...stops, stop];
      return route.fulfill({ status: 201, json: stop });
    }
    if (path.startsWith("/api/v1/grocery-shopping-stops/") && method === "PATCH") {
      const id = path.split("/").at(-1);
      const value = request.postDataJSON();
      const index = stops.findIndex((stop) => stop.id === id);
      stops[index] = { ...stops[index], ...value, version: stops[index].version + 1 };
      if (typeof value.position === "number") stops = stops.map((stop, current) => ({ ...stop, position: current }));
      return route.fulfill({ json: stops.find((stop) => stop.id === id) });
    }
    if (path.startsWith("/api/v1/grocery-shopping-stops/") && method === "DELETE") {
      const id = path.split("/").at(-1);
      stops = stops.filter((stop) => stop.id !== id);
      items = items.map((item) => item.shoppingStop?.id === id ? { ...item, shoppingStop: null } : item);
      return route.fulfill({ status: 204 });
    }
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list` && method === "GET") return missing ? route.fulfill({ status: 404, json: { code: "grocery_list_not_found", title: "Not found" } }) : route.fulfill({ json: grocery() });
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list` && method === "POST") {
      status = "current";
      listVersion += 1;
      return route.fulfill({ json: grocery() });
    }
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list/complete` && method === "POST") {
      status = "completed";
      listVersion += 1;
      return route.fulfill({ json: grocery() });
    }
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list/reopen` && method === "POST") {
      status = "current";
      listVersion += 1;
      return route.fulfill({ json: grocery() });
    }
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list/items` && method === "POST") {
      const value = request.postDataJSON();
      const item = { id: "00000000-0000-4000-8000-000000000073", ...value, origin: "manual", checked: false, needsReview: false, position: items.length, sources: [], version: 1 };
      items = [...items, item];
      return route.fulfill({ status: 201, json: item });
    }
    if (path.startsWith("/api/v1/grocery-items/") && method === "PATCH") {
      const id = path.split("/").at(-1);
      const index = items.findIndex((item) => item.id === id);
      const value = request.postDataJSON();
      const shoppingStop = "shoppingStopId" in value ? stops.find((stop) => stop.id === value.shoppingStopId) ?? null : items[index].shoppingStop;
      items[index] = { ...items[index], ...value, shoppingStop, version: items[index].version + 1 };
      delete items[index].shoppingStopId;
      return route.fulfill({ json: items[index] });
    }
    if (path.startsWith("/api/v1/grocery-items/") && method === "DELETE") {
      const id = path.split("/").at(-1);
      items = items.filter((item) => item.id !== id);
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

test("keeps a missing grocery list focused on one useful choice", async ({ page }, testInfo) => {
  await mockGroceryApi(page, { missing: true });
  await page.goto("/app/grocery");
  await expect(page.getByRole("heading", { level: 1, name: "Your grocery list starts with your plan" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open meal plan" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Start an empty list" })).toHaveCount(1);
  await expect(page.getByText("Plan the meals that matter")).toBeVisible();
  await expect(page.getByText("Use what is already home")).toBeVisible();
  await expect(page.getByText("Shop and check off")).toBeVisible();
  await expect(page.getByText("Build the list from your plan")).toHaveCount(0);
  await captureUi(page, testInfo, "grocery-missing");
});

test("does not call an empty grocery list ready to shop", async ({ page }, testInfo) => {
  await mockGroceryApi(page, { empty: true });
  await page.goto("/app/grocery");
  await expect(page.getByRole("heading", { name: "Nothing to pick up yet" })).toBeVisible();
  await expect(page.getByText("Ready to shop")).toHaveCount(0);
  await expect(page.getByText("Shop by stop", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Back to meal plan" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Use pantry stock" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Refresh from plan" })).toHaveCount(1);
  await expect(page.getByRole("link", { name: "Open meal plan" })).toHaveCount(1);
  await expect(page.getByText("Add something else", { exact: true })).toBeVisible();
  await captureUi(page, testInfo, "grocery-empty");
});

test("regenerates, traces, edits, checks, adds, and removes grocery items", async ({ page }, testInfo) => {
  await mockGroceryApi(page);
  await page.goto("/app/grocery");
  await expect(page.getByRole("heading", { name: "Everything you need this week" })).toBeVisible();
  await captureUi(page, testInfo, "grocery-active");
  await expect(page.getByText(/meal plan changed.*refresh/i)).toBeVisible();
  await page.getByRole("button", { name: "Refresh from plan" }).click();
  await expect(page.getByText("Ready to shop")).toBeVisible();

  await expect(page.getByText("Sheet-pan tofu bowls")).toBeVisible();
  await page.getByRole("checkbox", { name: "Red onion purchased" }).check();
  await expect(page.getByRole("checkbox", { name: "Red onion purchased" })).toBeChecked();

  await page.getByLabel("Edit Red onion").click();
  await page.getByLabel("Red onion name").fill("My red onions");
  await page.getByLabel("Red onion quantity").fill("800.000000");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("heading", { name: "My red onions" })).toBeVisible();

  await page.getByText("Add something else", { exact: true }).click();
  await page.getByLabel("Item", { exact: true }).fill("Reusable bags");
  await page.getByLabel("Quantity", { exact: true }).fill("2.000000");
  await page.getByLabel("Unit", { exact: true }).fill("bags");
  await page.getByRole("button", { name: "Add to list" }).click();
  await expect(page.getByRole("heading", { name: "Reusable bags" })).toBeVisible();
  await page.getByRole("button", { name: "Remove Reusable bags" }).click();
  await expect(page.getByRole("heading", { name: "Reusable bags" })).toHaveCount(0);
  await expect(page.getByText("Needs review")).toBeVisible();
  await captureUi(page, testInfo, "grocery-edited", { focus: page.getByText("Needs review") });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("groups a shopping pass by personal stops, then finishes and reopens it", async ({ page }, testInfo) => {
  await mockGroceryApi(page);
  await page.goto("/app/grocery");
  await page.getByText("Shop by stop", { exact: true }).click();
  await page.getByLabel("New stop").fill("Market");
  await page.getByRole("button", { name: "Add stop" }).click();
  await page.getByLabel("New stop").fill("Corner shop");
  await page.getByRole("button", { name: "Add stop" }).click();
  await expect(page.getByLabel("Market stop name")).toBeVisible();
  await captureUi(page, testInfo, "grocery-stops", { focus: page.getByLabel("Market stop name") });
  await page.getByLabel("Edit Red onion").click();
  await page.getByLabel("Shopping stop for Red onion").selectOption({ label: "Market" });
  await expect(page.getByRole("heading", { name: "Market" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Red onion purchased" }).check();
  await page.getByRole("checkbox", { name: "Salt to taste purchased" }).check();
  await page.getByRole("button", { name: "Finish this shopping pass" }).click();
  await expect(page.getByText("This shopping pass is complete")).toBeVisible();
  await expect(page.locator('.grocery-complete [data-companion-moment="milestone"]')).toBeVisible();
  await captureUi(page, testInfo, "grocery-complete");
  await expect(page.getByLabel("Edit Red onion")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Red onion" })).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: "Red onion purchased" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Refresh from plan" })).toHaveCount(0);
  await page.getByRole("button", { name: "Reopen list" }).click();
  await expect(page.getByText("Ready to shop")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
