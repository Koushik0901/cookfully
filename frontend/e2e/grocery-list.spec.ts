import { expect, type Page, test } from "@playwright/test";

const weekStart = "2026-03-09";
const listId = "00000000-0000-4000-8000-000000000070";
type TestStop = { id: string; name: string; position: number; version: number };
type TestItem = {
  id: string; displayName: string; quantity: string | null; unit: string | null;
  origin: string; checked: boolean; needsReview: boolean; position: number;
  sources: Array<{ mealPlanEntryId: string; originalText: string; quantityContribution: string | null }>;
  version: number; shoppingStop?: TestStop | null; shoppingStopId?: string | null;
};

async function mockGroceryApi(page: Page) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  let listVersion = 2;
  let status = "dirty";
  let stops: TestStop[] = [];
  let items: TestItem[] = [
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
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list` && method === "GET") return route.fulfill({ json: grocery() });
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

test("regenerates, traces, edits, checks, adds, and removes grocery items", async ({ page }) => {
  await mockGroceryApi(page);
  await page.goto("/app/grocery");
  await expect(page.getByRole("heading", { name: "Everything you need this week" })).toBeVisible();
  await expect(page.getByText(/meal plan changed.*refresh/i)).toBeVisible();
  await page.getByRole("button", { name: "Refresh from plan" }).click();
  await expect(page.getByText("Ready to shop")).toBeVisible();

  await page.getByRole("button", { name: "Show Red onion sources" }).click();
  await expect(page.getByText("500 g red onion")).toBeVisible();
  await page.getByRole("checkbox", { name: "Red onion purchased" }).check();
  await expect(page.getByRole("checkbox", { name: "Red onion purchased" })).toBeChecked();

  await page.getByText("Edit Red onion", { exact: true }).click();
  await page.getByLabel("Red onion name").fill("My red onions");
  await page.getByLabel("Red onion quantity").fill("800.000000");
  await page.getByRole("button", { name: "Save Red onion" }).click();
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
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("groups a shopping pass by personal stops, then finishes and reopens it", async ({ page }) => {
  await mockGroceryApi(page);
  await page.goto("/app/grocery");
  await page.getByText("Shop by stop", { exact: true }).click();
  await page.getByLabel("New stop").fill("Market");
  await page.getByRole("button", { name: "Add stop" }).click();
  await page.getByLabel("New stop").fill("Corner shop");
  await page.getByRole("button", { name: "Add stop" }).click();
  await expect(page.getByLabel("Market stop name")).toBeVisible();
  await page.getByText("Edit Red onion", { exact: true }).click();
  await page.getByLabel("Shopping stop for Red onion").selectOption({ label: "Market" });
  await expect(page.getByRole("heading", { name: "Market" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Red onion purchased" }).check();
  await page.getByRole("checkbox", { name: "Salt to taste purchased" }).check();
  await page.getByRole("button", { name: "Finish this shopping pass" }).click();
  await expect(page.getByText("This shopping pass is complete")).toBeVisible();
  await expect(page.getByText("Edit Red onion", { exact: true })).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Remove Red onion" })).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: "Red onion purchased" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Refresh from plan" })).toHaveCount(0);
  await page.getByRole("button", { name: "Reopen list" }).click();
  await expect(page.getByText("Ready to shop")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
