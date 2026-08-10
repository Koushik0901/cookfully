import { expect, type Page, test } from "@playwright/test";

const recipeId = "00000000-0000-4000-8000-000000000001";
const jobId = "00000000-0000-4000-8000-000000000002";

function detail(overrides: Record<string, unknown> = {}) {
  return {
    id: recipeId,
    title: "Protein oats",
    description: "Reliable breakfast",
    sourceUrl: "https://example.com/protein-oats",
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
      assumptions: ["One household measure used a reviewed density conversion."],
      corrections: [],
    },
    version: 1,
    updatedAt: "2026-08-10T10:00:00Z",
    ingredients: [
      {
        id: "00000000-0000-4000-8000-000000000003",
        position: 0,
        originalText: "1 cup rolled oats",
        quantityMin: "1.000000",
        quantityMax: null,
        unit: "cup",
        food: "rolled oats",
        preparation: null,
        optional: false,
        parseStatus: "parsed",
        matchStatus: "matched",
        assumptions: [],
      },
    ],
    instructions: ["Mix and chill."],
    activeJob: null,
    ...overrides,
  };
}

async function mockApi(page: Page) {
  let recipe = detail();
  let pollCount = 0;
  let releaseImport = false;
  let deleted = false;
  await page.context().addCookies([
    { name: "vv_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" },
  ]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA" });
    if (path === "/api/v1/recipes" && method === "GET") {
      return json({ items: deleted ? [] : [recipe], nextCursor: null });
    }
    if (path === "/api/v1/recipes" && method === "POST") {
      const body = request.postDataJSON();
      recipe = detail({
        ...body,
        id: recipeId,
        version: 1,
        ingredients: body.ingredients.map((item: { originalText: string }, index: number) => ({
          ...detail().ingredients[0],
          id: `00000000-0000-4000-8000-${String(index + 3).padStart(12, "0")}`,
          position: index,
          originalText: item.originalText,
        })),
      });
      return json(recipe, 201);
    }
    if (path === "/api/v1/recipes/import" && method === "POST") {
      recipe = detail({
        title: "Imported recipe",
        status: "processing",
        nutritionState: "pending",
        activeJob: {
          id: jobId,
          kind: "recipe.import",
          aggregateId: recipeId,
          status: "running",
          attempt: 1,
          maxAttempts: 3,
          inputHash: "input-one",
          progressCurrent: 1,
          progressTotal: 2,
          nextRetryAt: null,
          terminalDeadlineAt: "2026-08-10T10:05:00Z",
          failureCode: null,
          failureMessage: null,
          createdAt: "2026-08-10T10:00:00Z",
          finishedAt: null,
          pollAfterSeconds: 2,
          recoveryActions: [],
        },
      });
      return json({ jobId, resourceId: recipeId, status: "queued" }, 202);
    }
    if (path === `/api/v1/jobs/${jobId}`) {
      if (!releaseImport) return json(recipe.activeJob);
      pollCount += 1;
      const stale = pollCount === 1;
      if (!stale) recipe = detail({ nutritionState: "stale", activeJob: null, version: 2 });
      return json({
        id: jobId,
        kind: "recipe.import",
        aggregateId: recipeId,
        status: stale ? "retry_wait" : "succeeded",
        attempt: stale ? 2 : 3,
        maxAttempts: 3,
        inputHash: "input-one",
        progressCurrent: stale ? 1 : 2,
        progressTotal: 2,
        nextRetryAt: stale ? new Date(Date.now() + 1_000).toISOString() : null,
        terminalDeadlineAt: new Date(Date.now() + 60_000).toISOString(),
        failureCode: stale ? "provider_timeout" : null,
        failureMessage: stale ? "Reference provider timed out." : null,
        createdAt: new Date().toISOString(),
        finishedAt: stale ? null : new Date().toISOString(),
        pollAfterSeconds: stale ? 2 : null,
        recoveryActions: stale ? ["wait", "edit_recipe"] : [],
      });
    }
    if (path === `/api/v1/recipes/${recipeId}` && method === "GET") return json(recipe);
    if (path === `/api/v1/recipes/${recipeId}` && method === "PATCH") {
      const body = request.postDataJSON();
      recipe = detail({
        ...recipe,
        ...body,
        ingredients: body.ingredients.map((item: { originalText: string }, index: number) => ({
          ...detail().ingredients[0],
          id: `00000000-0000-4000-8000-${String(index + 3).padStart(12, "0")}`,
          position: index,
          originalText: item.originalText,
        })),
        nutritionState: "stale",
        version: Number(recipe.version) + 1,
      });
      return json(recipe);
    }
    if (path === `/api/v1/recipes/${recipeId}` && method === "DELETE") {
      recipe = detail({ ...recipe, status: "archived", archivedFromStatus: "ready", version: Number(recipe.version) + 1 });
      return route.fulfill({ status: 204 });
    }
    if (path === `/api/v1/recipes/${recipeId}/restore` && method === "POST") {
      recipe = detail({ ...recipe, status: "ready", archivedFromStatus: null, version: Number(recipe.version) + 1 });
      return json(recipe);
    }
    if (path === `/api/v1/recipes/${recipeId}/nutrition/corrections` && method === "POST") {
      const correction = { id: "00000000-0000-4000-8000-000000000004", ...request.postDataJSON(), active: true, createdAt: new Date().toISOString() };
      recipe = detail({ ...recipe, nutrition: { ...recipe.nutrition, corrections: [correction] } });
      return json(recipe.nutrition, 201);
    }
    if (path === `/api/v1/recipes/${recipeId}/nutrition/recalculate` && method === "POST") {
      recipe = detail({ ...recipe, nutritionState: "pending" });
      return json({ jobId, resourceId: recipeId, status: "queued" }, 202);
    }
    if (path === `/api/v1/recipes/${recipeId}/permanent` && method === "DELETE") {
      deleted = true;
      return route.fulfill({ status: 204 });
    }
    return json({ code: "not_found", title: "Not found", status: 404 }, 404);
  });
  return { releaseImport: () => { releaseImport = true; pollCount = 0; } };
}

test("manual create, edit, correction, archive, restore, and history-safe permanent delete", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/recipes/new");
  await page.getByLabel("Recipe title").fill("Protein oats");
  await page.getByLabel("Yield quantity").fill("2.000");
  await page.getByLabel("Ingredients, one per line").fill("1 cup rolled oats");
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByRole("heading", { name: "Protein oats" })).toBeVisible();

  await page.getByRole("link", { name: "Edit recipe" }).click();
  await page.getByLabel("Yield quantity").fill("3.000");
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByText(/nutrition is stale/i)).toBeVisible();

  await page.getByLabel("Nutrition field").selectOption("protein_g");
  await page.getByLabel("Corrected decimal value").fill("40.000000");
  await page.getByLabel("Correction reason").fill("Package label");
  await page.getByRole("button", { name: "Apply correction" }).click();
  await expect(page.getByText("Package label")).toBeVisible();

  await page.getByRole("button", { name: "Archive recipe" }).click();
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(page.getByRole("button", { name: "Restore recipe" })).toBeVisible();
  await page.getByRole("button", { name: "Restore recipe" }).click();
  await expect(page.getByRole("button", { name: "Archive recipe" })).toBeVisible();

  await page.getByRole("button", { name: "Archive recipe" }).click();
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await page.getByRole("button", { name: "Permanently delete recipe" }).click();
  await expect(page.getByText(/historical plan and grocery records remain detached/i)).toBeVisible();
  await page.getByRole("button", { name: "Delete permanently" }).click();
  await expect(page.getByText("No recipes yet")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("URL import survives reload, exposes bounded retry, and offers stale-yield recovery", async ({ page }) => {
  const api = await mockApi(page);
  await page.goto("/app/recipes");
  await page.getByRole("button", { name: "Import from URL" }).click();
  await page.getByLabel("Recipe URL").fill("https://example.com/protein-oats");
  await page.getByRole("button", { name: "Start import" }).click();
  await expect(page.getByText("running")).toBeVisible();

  api.releaseImport();
  await page.reload();
  await expect(page.getByText(/attempt 2 of 3/i)).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText(/next retry/i)).toBeVisible();
  await expect(page.getByText(/deadline/i)).toBeVisible();
  await expect(page.getByText(/nutrition is stale/i)).toBeVisible({ timeout: 7_000 });
  await page.getByRole("button", { name: "Recalculate nutrition" }).click();
  await expect(page.getByText(/nutrition is pending/i)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
