import { expect, type Page, test } from "@playwright/test";

const weekStart = "2026-03-09";
const listId = "00000000-0000-4000-8000-000000000070";
const ids = ["00000000-0000-4000-8000-000000000071", "00000000-0000-4000-8000-000000000072", "00000000-0000-4000-8000-000000000073"];

type Item = Record<string, unknown>;

function item(index: number, displayName: string, extra: Item = {}): Item {
  return {
    id: ids[index],
    displayName,
    quantity: "2",
    unit: null,
    origin: "generated",
    checked: false,
    needsReview: false,
    position: index,
    sources: [],
    version: 1,
    aisle: null,
    likelyStaple: false,
    mergedFrom: [],
    ...extra,
  };
}

async function mockApi(page: Page, options: { failKeepSeparate?: boolean; keepSeparateDelayMs?: number } = {}) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  let items: Item[] = [
    item(0, "Green onion", { aisle: "produce", mergedFrom: ["Scallion"] }),
    item(1, "Salt", { aisle: "spices", likelyStaple: true, quantity: null }),
    item(2, "Mystery item", { aisle: null }),
  ];
  const calls = { patches: [] as Item[], keepSeparate: 0 };
  await page.context().addCookies([{ name: "cookfully_csrf", value: "grocery-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const list = () => ({ id: listId, weekStart, status: "current", generatedAt: "2026-03-10T12:00:00Z", items, version: 2 });
    if (path === "/api/v1/owner/preferences") return route.fulfill({ json: { timezone: "UTC", weekStartsOn: 1, version: 1 } });
    if (path === "/api/v1/owner/onboarding") return route.fulfill({ json: { state: "completed", version: 1 } });
    if (path === `/api/v1/meal-plans/${weekStart}`) {
      return route.fulfill({ json: { entries: [{ id: "00000000-0000-4000-8000-000000000020", localDate: "2026-03-11", mealSlot: "dinner", recipeId: "00000000-0000-4000-8000-000000000120", recipeTitle: "Sheet-pan tofu bowls" }] } });
    }
    if (path === "/api/v1/grocery-shopping-stops") return route.fulfill({ json: [] });
    if (path === `/api/v1/meal-plans/${weekStart}/grocery-list`) return route.fulfill({ json: list() });
    if (path.startsWith("/api/v1/grocery-items/") && path.endsWith("/keep-separate") && method === "POST") {
      calls.keepSeparate += 1;
      if (options.keepSeparateDelayMs) await new Promise((resolve) => setTimeout(resolve, options.keepSeparateDelayMs));
      if (options.failKeepSeparate) return route.fulfill({ status: 500, json: { code: "boom", title: "Keeping these separate failed." } });
      items = [item(0, "Green onion", { aisle: "produce" }), item(1, "Salt", { aisle: "spices", likelyStaple: true, quantity: null }), item(2, "Mystery item"), item(3 - 1, "Scallion", { id: "00000000-0000-4000-8000-000000000099", aisle: "produce" })];
      return route.fulfill({ json: list() });
    }
    if (path.startsWith("/api/v1/grocery-items/") && method === "PATCH") {
      const id = path.split("/").at(-1);
      const value = request.postDataJSON() as Item;
      calls.patches.push(value);
      const index = items.findIndex((candidate) => candidate.id === id);
      items[index] = { ...items[index], ...value, version: Number(items[index].version) + 1 };
      return route.fulfill({ json: items[index] });
    }
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
  return calls;
}

const row = (page: Page, name: string) => page.locator("article.grocery-item").filter({ has: page.getByRole("heading", { name, exact: true }) });

test("each line shows its aisle, merged names and staple mark, and a line without an aisle shows none", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/grocery");
  await expect(row(page, "Green onion").locator(".grocery-tidy__aisle")).toHaveText("Produce");
  await expect(row(page, "Green onion").locator(".grocery-tidy__merged")).toContainText("Includes Scallion");
  await expect(row(page, "Salt").locator(".grocery-tidy__aisle")).toHaveText("Spices");
  await expect(row(page, "Salt").getByRole("button", { name: "Probably have" })).toHaveAttribute("aria-pressed", "true");
  await expect(row(page, "Mystery item").locator(".grocery-tidy")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("tapping 'Probably have' tells the server the owner needs to buy it, and the mark goes", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/app/grocery");
  await row(page, "Salt").getByRole("button", { name: "Probably have" }).click();
  await expect.poll(() => calls.patches.length).toBe(1);
  expect(calls.patches[0]).toMatchObject({ likelyStaple: false });
  await expect(row(page, "Salt").getByRole("button", { name: "Probably have" })).toHaveCount(0);
});

test("keeping merged names separate asks once, even on a double click, and splits the line", async ({ page }) => {
  const calls = await mockApi(page, { keepSeparateDelayMs: 400 });
  await page.goto("/app/grocery");
  const button = row(page, "Green onion").getByRole("button", { name: "Keep Scallion separate from Green onion" });
  await button.dblclick();
  await expect(row(page, "Scallion")).toBeVisible();
  expect(calls.keepSeparate).toBe(1);
  await expect(row(page, "Green onion").locator(".grocery-tidy__merged")).toHaveCount(0);
});

test("a failed keep-separate is shown to the owner and leaves the list as it was", async ({ page }) => {
  await mockApi(page, { failKeepSeparate: true });
  await page.goto("/app/grocery");
  await row(page, "Green onion").getByRole("button", { name: /Keep Scallion separate/ }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Keeping these separate failed." })).toBeVisible();
  await expect(row(page, "Green onion").locator(".grocery-tidy__merged")).toContainText("Includes Scallion");
});
