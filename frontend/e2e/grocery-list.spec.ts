import { expect, type Page, test } from "@playwright/test";

const weekStart = "2026-03-09";
const listId = "00000000-0000-4000-8000-000000000070";

async function mockGroceryApi(page: Page) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  let listVersion = 2;
  let status = "dirty";
  let items = [
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
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list` && method === "GET") return route.fulfill({ json: grocery() });
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list` && method === "POST") {
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
      items[index] = { ...items[index], ...request.postDataJSON(), version: items[index].version + 1 };
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
