import { expect, type Page, test } from "@playwright/test";
import axe from "axe-core";

const recipeId = "00000000-0000-4000-8000-000000000001";
const ingredientIds = ["00000000-0000-4000-8000-000000000003", "00000000-0000-4000-8000-000000000004", "00000000-0000-4000-8000-000000000005"];

function ingredient(index: number, text: string, extra: Record<string, unknown> = {}) {
  return {
    id: ingredientIds[index],
    position: index,
    originalText: text,
    quantityMin: "1.000000",
    quantityMax: null,
    unit: "cup",
    food: text,
    preparation: null,
    optional: false,
    parseStatus: "parsed",
    matchStatus: "matched",
    assumptions: [],
    substitutable: true,
    ...extra,
  };
}

function detail(overrides: Record<string, unknown> = {}) {
  return {
    id: recipeId,
    title: "Caesar salad",
    description: "Crisp and salty",
    sourceUrl: null,
    imageUrl: null,
    yieldQuantity: "2.000",
    yieldUnit: "servings",
    status: "ready",
    archivedFromStatus: null,
    nutritionState: "estimated",
    nutrition: {
      status: "estimated",
      basisServings: "2.000",
      coverageRatio: "0.950000",
      caloriesKcal: "540.000000",
      proteinG: "38.500000",
      carbohydrateG: "62.000000",
      fatG: "14.000000",
      provenance: [{ kind: "reference", label: "USDA Foundation Foods", version: "2026-04-30" }],
      assumptions: [],
      corrections: [],
    },
    version: 1,
    updatedAt: "2026-08-10T10:00:00Z",
    ingredients: [ingredient(0, "1 head romaine"), ingredient(1, "1 tbsp Worcestershire sauce"), ingredient(2, "2 anchovy fillets")],
    instructions: [{ position: 0, text: "Toss." }],
    activeJob: null,
    avoidWarnings: [],
    hiddenIngredientCheck: "no_avoid_list",
    facets: [],
    ...overrides,
  };
}

type Mock = {
  recipe: Record<string, unknown>;
  libraryRequests: string[];
  substitutes: (ingredientId: string) => { status: number; body: unknown };
  substituteCalls: string[];
};

async function mockApi(page: Page, overrides: Partial<Mock> = {}): Promise<Mock> {
  const state: Mock = {
    recipe: detail(),
    libraryRequests: [],
    substitutes: () => ({ status: 200, body: { ingredientId: ingredientIds[1], key: null, substitutes: [], ranked: true } }),
    substituteCalls: [],
    ...overrides,
  };
  await page.context().addCookies([{ name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA", timezone: "UTC", weekStartsOn: 1, version: 1 });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/recipes/collections") return json([]);
    if (path === "/api/v1/recipes" && request.method() === "GET") {
      state.libraryRequests.push(url.search);
      const wanted = url.searchParams.getAll("facet");
      const facets = (state.recipe.facets ?? []) as { key: string }[];
      const matches = wanted.every((key) => facets.some((facet) => facet.key === key));
      return json({ items: matches ? [state.recipe] : [], nextCursor: null });
    }
    if (path === `/api/v1/recipes/${recipeId}`) return json(state.recipe);
    const swap = path.match(new RegExp(`^/api/v1/recipes/${recipeId}/ingredients/([^/]+)/substitutes$`));
    if (swap) {
      state.substituteCalls.push(swap[1] ?? "");
      const result = state.substitutes(swap[1] ?? "");
      return json(result.body, result.status);
    }
    return json({ code: "not_found", title: "Not found" }, 404);
  });
  return state;
}

const openRefine = async (page: Page) => {
  await page.getByText("Refine recipes").click();
};

test("the library filters by tag, sends exactly the chosen tags, and says so when nothing matches", async ({ page }) => {
  const state = await mockApi(page, { recipe: detail({ facets: [{ key: "vegetarian", probability: "0.95" }, { key: "freezes_well", probability: "0.9" }] }) });
  await page.goto("/app/recipes");
  await expect(page.getByRole("link", { name: /Caesar salad/ }).first()).toBeVisible();
  await openRefine(page);
  const vegetarian = page.getByRole("button", { name: "Vegetarian", exact: true });
  await vegetarian.click();
  await expect(vegetarian).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => state.libraryRequests.some((q) => q.includes("facet=vegetarian"))).toBe(true);
  await expect(page.getByRole("link", { name: /Caesar salad/ }).first()).toBeVisible();

  await page.getByRole("button", { name: "Vegan", exact: true }).click();
  await expect.poll(() => state.libraryRequests.some((q) => q.includes("facet=vegetarian") && q.includes("facet=vegan"))).toBe(true);
  await expect(page.getByRole("link", { name: /Caesar salad/ })).toHaveCount(0);

  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByRole("link", { name: /Caesar salad/ }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Vegan", exact: true })).toHaveAttribute("aria-pressed", "false");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("an avoid-list recipe lists named ingredients, labels model suspicions, and quotes their probability", async ({ page }) => {
  await mockApi(page, {
    recipe: detail({
      hiddenIngredientCheck: "checked",
      avoidWarnings: [
        { ingredientId: ingredientIds[2], item: "fish", source: "ingredient", probability: null },
        { ingredientId: ingredientIds[1], item: "fish", source: "model", probability: "0.92" },
      ],
    }),
  });
  await page.goto(`/app/recipes/${recipeId}`);
  const notice = page.locator(".avoid-notice");
  await expect(notice).toContainText("On your avoid list");
  await expect(notice).toContainText("fish: 2 anchovy fillets");
  await expect(notice).toContainText("May contain fish: 1 tbsp Worcestershire sauce (92%), suggested by a decision model");
  await expect(notice).not.toContainText("have not been checked");
});

test("a recipe whose hidden-ingredient check has not run says so instead of implying it is safe", async ({ page }) => {
  await mockApi(page, { recipe: detail({ hiddenIngredientCheck: "not_checked", avoidWarnings: [] }) });
  await page.goto(`/app/recipes/${recipeId}`);
  const note = page.getByRole("note");
  await expect(note).toContainText("Nothing on your avoid list is named");
  await expect(note).toContainText("have not been checked yet");
  await expect(page.locator(".avoid-notice")).toHaveCount(0);
});

test("a stale check still shows earlier warnings and also says the check is pending", async ({ page }) => {
  await mockApi(page, {
    recipe: detail({
      hiddenIngredientCheck: "not_checked",
      avoidWarnings: [{ ingredientId: ingredientIds[1], item: "fish", source: "model", probability: "0.9" }],
    }),
  });
  await page.goto(`/app/recipes/${recipeId}`);
  await expect(page.locator(".avoid-notice")).toContainText("May contain fish");
  await expect(page.locator(".avoid-notice")).toContainText("Hidden ingredients have not been checked yet");
});

test("no avoid list means no avoid notice at all", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/app/recipes/${recipeId}`);
  await expect(page.getByRole("heading", { name: "Caesar salad" })).toBeVisible();
  await expect(page.locator(".avoid-notice, .avoid-unchecked")).toHaveCount(0);
});

test("tag chips word unsure tags as probable, hide unknown tags, and carry their probability", async ({ page }) => {
  await mockApi(page, {
    recipe: detail({
      facets: [
        { key: "vegetarian", probability: "0.72" },
        { key: "gluten_free", probability: "0.65" },
        { key: "reheats_well", probability: "0.75" },
        { key: "freezes_well", probability: "0.95" },
        { key: "made_up:tag", probability: "0.99" },
      ],
    }),
  });
  await page.goto(`/app/recipes/${recipeId}`);
  const chips = page.getByRole("list", { name: "Recipe tags" });
  await expect(chips).toContainText("Vegetarian");
  await expect(chips).not.toContainText("Probably vegetarian");
  await expect(chips).toContainText("Probably gluten-free");
  await expect(chips).toContainText("Probably reheats well");
  await expect(chips).toContainText("Freezes well");
  await expect(chips).not.toContainText("made_up");
  await expect(chips.getByText("Probably gluten-free")).toHaveAttribute("title", /65%/);
});

test("swaps load only when opened, show fit, and explain unranked and empty results", async ({ page }) => {
  const state = await mockApi(page, {
    substitutes: (id) =>
      id === ingredientIds[1]
        ? { status: 200, body: { ingredientId: id, key: "x", ranked: true, substitutes: [{ name: "Tamari", amount: "Same amount", note: null, probability: "0.91" }] } }
        : id === ingredientIds[0]
          ? { status: 200, body: { ingredientId: id, key: "y", ranked: false, substitutes: [{ name: "Quinoa", amount: "Same amount", note: null, probability: null }] } }
          : { status: 200, body: { ingredientId: id, key: null, ranked: true, substitutes: [] } },
  });
  await page.goto(`/app/recipes/${recipeId}`);
  await expect(page.getByRole("heading", { name: "Caesar salad" })).toBeVisible();
  expect(state.substituteCalls).toEqual([]);

  const swaps = page.locator("details.substitutes");
  await swaps.nth(1).locator("summary").click();
  await expect(swaps.nth(1)).toContainText("Tamari");
  await expect(swaps.nth(1)).toContainText("91% fit for this recipe");
  expect(state.substituteCalls).toEqual([ingredientIds[1]]);

  await swaps.nth(0).locator("summary").click();
  await expect(swaps.nth(0)).toContainText("Not ranked for this recipe; common swaps shown.");

  await swaps.nth(2).locator("summary").click();
  await expect(swaps.nth(2)).toContainText("No good swaps for this recipe.");

  await swaps.nth(1).locator("summary").click();
  await swaps.nth(1).locator("summary").click();
  expect(state.substituteCalls.filter((id) => id === ingredientIds[1])).toHaveLength(1);
});

test("a failed swap request offers a retry that works", async ({ page }) => {
  let fail = true;
  await mockApi(page, {
    substitutes: (id) =>
      fail
        ? { status: 500, body: { code: "boom", title: "Boom" } }
        : { status: 200, body: { ingredientId: id, key: "x", ranked: true, substitutes: [{ name: "Tamari", amount: "Same amount", note: null, probability: "0.9" }] } },
  });
  await page.goto(`/app/recipes/${recipeId}`);
  const swap = page.locator("details.substitutes").nth(1);
  await swap.locator("summary").click();
  await expect(swap.getByText("Swaps could not be loaded.")).toBeVisible();
  fail = false;
  await swap.getByRole("button", { name: "Try again" }).click();
  await expect(swap).toContainText("Tamari");
});

test("the recipe page with every decision-model element has no accessibility violations and no overflow", async ({ page }) => {
  await mockApi(page, {
    recipe: detail({
      hiddenIngredientCheck: "checked",
      avoidWarnings: [{ ingredientId: ingredientIds[1], item: "fish", source: "model", probability: "0.92" }],
      facets: [{ key: "vegetarian", probability: "0.72" }, { key: "weeknight", probability: "1" }, { key: "cuisine:italian", probability: "0.9" }],
    }),
  });
  await page.goto(`/app/recipes/${recipeId}`);
  await expect(page.locator(".avoid-notice")).toBeVisible();
  await page.waitForTimeout(1000);
  await page.addScriptTag({ content: axe.source });
  const violations = await page.evaluate(async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const out = await (window as any).axe.run(document.querySelector("main") ?? document.body, { runOnly: ["wcag2a", "wcag2aa"] });
    return out.violations.map((v: { id: string; nodes: { target: string[] }[] }) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
  });
  expect(violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("only ingredients the server marks swappable get a Swap control", async ({ page }) => {
  await mockApi(page, {
    recipe: detail({ ingredients: [ingredient(0, "1 head romaine", { substitutable: false }), ingredient(1, "1 tbsp Worcestershire sauce"), ingredient(2, "2 anchovy fillets", { substitutable: false })] }),
  });
  await page.goto(`/app/recipes/${recipeId}`);
  await expect(page.getByRole("heading", { name: "Caesar salad" })).toBeVisible();
  await expect(page.locator("details.substitutes")).toHaveCount(1);
});
