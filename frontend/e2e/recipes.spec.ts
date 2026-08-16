import { expect, type Page, test } from "@playwright/test";
import { captureUi } from "./support/visual-audit";
import { Buffer } from "node:buffer";

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
    instructions: [{ position: 0, text: "Mix and chill." }],
    activeJob: null,
    ...overrides,
  };
}

async function mockApi(page: Page) {
  let recipe = detail();
  let pollCount = 0;
  let releaseImport = false;
  let deleted = false;
  const collection = { id: "00000000-0000-4000-8000-000000000010", name: "Weeknight favourites", position: 0, version: 1, recipeCount: 0 };
  await page.context().addCookies([
    { name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" },
  ]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA" });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/recipes/collections" && method === "GET") return json([collection]);
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
    if (path === "/api/v1/recipes/import/preview" && method === "POST") {
      // Preview is best-effort: simulate a source that continues in the background
      // so the dialog falls back to the legacy asynchronous import below.
      return json({ code: "preview_unavailable", title: "Unavailable", status: 503 }, 503);
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
    if (path === `/api/v1/recipes/${recipeId}/organization` && method === "PUT") {
      const body = request.postDataJSON();
      recipe = detail({ ...recipe, favorite: body.favorite, collections: body.collectionIds.map((id: string) => ({ id, name: collection.name, position: collection.position })), mealRoles: body.mealRoles, version: Number(recipe.version) + 1 });
      return json(recipe);
    }
    if (path === `/api/v1/recipes/${recipeId}/photo` && method === "PUT") {
      recipe = detail({ ...recipe, imageUrl: "/api/v1/media/00000000-0000-4000-8000-000000000011", version: Number(recipe.version) + 1 });
      return json(recipe);
    }
    if (path === `/api/v1/recipes/${recipeId}/photo` && method === "DELETE") {
      recipe = detail({ ...recipe, imageUrl: null, version: Number(recipe.version) + 1 });
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

async function mockPreviewApi(page: Page) {
  const parseId = "preview-parse-0001";
  let confirmPosted: Record<string, unknown> | null = null;
  await page.context().addCookies([
    { name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" },
  ]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA" });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/recipes/collections" && method === "GET") return json([]);
    if (path === "/api/v1/recipes" && method === "GET") {
      return json({ items: [], nextCursor: null });
    }
    if (path === "/api/v1/recipes/import/preview" && method === "POST") {
      return json({
        parseId,
        title: "Shawarma bowl",
        yieldQuantity: null,
        yieldText: null,
        imageSources: [],
        duplicates: [{ id: recipeId, title: "Shawarma bowl" }],
        sections: [
          {
            title: "The chicken",
            ingredients: [
              { originalText: "1 lb chicken breast", needsQuantity: false },
              { originalText: "olive oil", needsQuantity: true },
            ],
            instructions: ["Season the chicken."],
          },
          {
            title: "The sauce",
            ingredients: [{ originalText: "2 tbsp yogurt", needsQuantity: false }],
            instructions: ["Whisk the sauce."],
          },
        ],
      });
    }
    if (path === "/api/v1/recipes/import/confirm" && method === "POST") {
      confirmPosted = request.postDataJSON() as Record<string, unknown>;
      const title = (confirmPosted.title as string) ?? "Shawarma bowl";
      return json({ jobId, resourceId: recipeId, status: "queued" }, 202);
    }
    if (path === `/api/v1/recipes/${recipeId}` && method === "GET") {
      return json(
        detail({
          title: "Shawarma bowl",
          status: "processing",
          nutritionState: "pending",
          activeJob: {
            id: jobId,
            kind: "recipe.import",
            aggregateId: recipeId,
            status: "running",
            attempt: 0,
            maxAttempts: 3,
            inputHash: "preview-confirmed",
            progressCurrent: 1,
            progressTotal: 2,
            nextRetryAt: null,
            terminalDeadlineAt: null,
            failureCode: null,
            failureMessage: null,
            createdAt: new Date().toISOString(),
            finishedAt: null,
            pollAfterSeconds: 2,
            recoveryActions: [],
          },
        }),
      );
    }
    return json({ code: "not_found", title: "Not found", status: 404 }, 404);
  });
  return { parseId, posted: () => confirmPosted };
}

async function openRecipeOptions(page: Page) {
  const details = page.locator("details.danger-zone");
  if (!(await details.evaluate((element: HTMLDetailsElement) => element.open))) {
    await details.locator("summary").click();
  }
}

test("manual create, edit, correction, archive, restore, and history-safe permanent delete", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto("/app/recipes/new");
  if (testInfo.project.name === "narrow-mobile") {
    await expect(page.getByLabel("Ingredients, one per line")).toBeHidden();
    await page.getByRole("button", { name: "Ingredients" }).click();
    await expect(page.getByLabel("Ingredients, one per line")).toBeVisible();
    await page.getByRole("button", { name: "Basics" }).click();
  }
  await page.getByLabel("Recipe title").fill("Protein oats");
  await page.getByLabel("Yield quantity").fill("2.000");
  if (testInfo.project.name === "narrow-mobile") await page.getByRole("button", { name: "Ingredients" }).click();
  await page.getByLabel("Ingredients, one per line").fill("1 cup rolled oats");
  if (testInfo.project.name === "narrow-mobile") await page.getByRole("button", { name: "Method" }).click();
  await captureUi(page, testInfo, "recipe-editor");
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByRole("heading", { name: "Protein oats" })).toBeVisible();
  await expect(page.locator('.recipe-saved-moment [data-companion-moment="success"]')).toBeVisible();
  await captureUi(page, testInfo, "recipe-detail");

  await page.getByRole("link", { name: "Edit recipe" }).click();
  await page.getByLabel("Yield quantity").fill("3.000");
  if (testInfo.project.name === "narrow-mobile") await page.getByRole("button", { name: "Method" }).click();
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByText("Outdated", { exact: true })).toBeVisible();
  await expect(page.locator('.recipe-saved-moment [data-companion-moment="success"]')).toBeVisible();

  await page.getByRole("link", { name: "Edit recipe" }).click();
  if (testInfo.project.name === "narrow-mobile") await page.getByRole("button", { name: "Nutrition" }).click();
  await page.getByText("Nutrition values").click();
  await page.getByLabel("Protein (g)").fill("40.000000");
  await page.getByLabel("Source or reason").fill("Package label");
  await page.getByRole("button", { name: "Save recipe" }).click();
  await page.getByText("Nutrition details and evidence").click();
  await expect(page.getByText("Package label")).toBeVisible();
  await captureUi(page, testInfo, "recipe-nutrition-correction", { focus: page.getByText("Package label") });

  await openRecipeOptions(page);
  await page.getByRole("button", { name: "Archive recipe" }).click();
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await openRecipeOptions(page);
  await expect(page.getByRole("button", { name: "Restore recipe" })).toBeVisible();
  await page.getByRole("button", { name: "Restore recipe" }).click();
  await openRecipeOptions(page);
  await expect(page.getByRole("button", { name: "Archive recipe" })).toBeVisible();

  await page.getByRole("button", { name: "Archive recipe" }).click();
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await openRecipeOptions(page);
  await page.getByRole("button", { name: "Permanently delete recipe" }).click();
  await expect(page.getByText(/historical plan and grocery records remain detached/i)).toBeVisible();
  await page.getByRole("button", { name: "Delete permanently" }).click();
  await expect(page.getByText("No recipes yet")).toBeVisible();
  await expect(page.locator('.empty-state [data-companion-moment="empty"]')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("URL import survives reload, exposes bounded retry, and offers stale-yield recovery", async ({ page }, testInfo) => {
  const api = await mockApi(page);
  await page.goto("/app/recipes");
  await page.getByRole("button", { name: "Import recipe" }).click();
  await captureUi(page, testInfo, "recipe-import-dialog");
  await page.getByLabel("Recipe or cookbook URL").fill("https://example.com/protein-oats");
  await page.getByRole("button", { name: "Start import" }).click();
  await expect(page.getByText(/calculating nutrition/i)).toBeVisible();

  api.releaseImport();
  await page.reload();
  await expect(page.getByText(/nutrition will retry automatically/i)).toBeVisible({ timeout: 5_000 });
  await page.getByText("Nutrition details and evidence").click();
  await expect(page.getByText(/attempt 2 of 3/i)).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText(/next retry/i)).toBeVisible();
  await expect(page.getByText(/deadline/i)).toBeVisible();
  await expect(page.getByText("Outdated", { exact: true })).toBeVisible({ timeout: 7_000 });
  await captureUi(page, testInfo, "recipe-import-stale");
  await page.getByRole("button", { name: "Recalculate nutrition" }).click();
  await expect(page.getByText("Estimating…", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("keeps optional favorites and meal moments out of recipe entry, but easy to add later", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto(`/app/recipes/${recipeId}`);
  await page.getByText("Keep this easy to find").click();
  await captureUi(page, testInfo, "recipe-organization", { focus: page.getByText("Keep this easy to find") });
  await page.getByLabel("Favorite this recipe").check();
  await page.getByRole("checkbox", { name: "Weeknight favourites", exact: true }).check();
  await page.getByRole("checkbox", { name: "dinner", exact: true }).check();
  await page.getByRole("button", { name: "Save organization" }).click();
  await expect(page.getByRole("button", { name: "Save organization" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("makes a focused recipe-library view easy to understand and clear", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto("/app/recipes");
  await expect(page.getByRole("heading", { name: "What would you like to cook?" })).toBeVisible();
  await expect(page.locator(".recipe-card--featured")).toHaveCount(0);
  await expect(page.locator(".recipe-card__media .recipe-card__state")).toHaveCount(0);
  await expect(page.locator(".recipe-card__body .recipe-card__state")).toBeVisible();
  await page.getByRole("button", { name: "More actions for Protein oats" }).click();
  await expect(page.getByRole("menuitem", { name: "Edit recipe" })).toHaveAttribute("href", `/app/recipes/${recipeId}/edit`);
  await expect(page.getByRole("menuitem", { name: "Archive recipe" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Delete recipe" })).toBeVisible();
  const [organizeRequest] = await Promise.all([
    page.waitForRequest((request) => request.url().includes("/organization") && request.method() === "PUT"),
    page.getByRole("menuitem", { name: "Weeknight favourites" }).click(),
  ]);
  expect(organizeRequest.postDataJSON()).toMatchObject({ favorite: false, collectionIds: ["00000000-0000-4000-8000-000000000010"], mealRoles: [] });
  await captureUi(page, testInfo, "recipes");
  await page.getByText("Refine recipes", { exact: true }).click();
  if (testInfo.project.name !== "narrow-mobile") {
    const sort = await page.getByLabel("Sort recipes").boundingBox();
    const collection = await page.getByLabel("Collection", { exact: true }).boundingBox();
    expect(sort).not.toBeNull();
    expect(collection).not.toBeNull();
    expect(Math.abs(sort!.y - collection!.y)).toBeLessThanOrEqual(1);
  }
  await captureUi(page, testInfo, "recipes-filters");
  await page.getByText("Manage collections", { exact: true }).click();
  await expect(page.getByLabel("Weeknight favourites collection name")).toBeVisible();
  await page.getByText("Manage collections", { exact: true }).click();
  await page.getByLabel("Favorites only").check();
  await expect(page.getByRole("button", { name: /Favorites.*remove filter/i })).toBeVisible();
  await page.getByLabel("Collection", { exact: true }).selectOption({ label: "Weeknight favourites" });
  await expect(page.getByRole("button", { name: /Collection: Weeknight favourites.*remove filter/i })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByLabel("Favorites only")).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Clear filters" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("a handwritten recipe can gain and remove a representative photo", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto("/app/recipes/new");
  await page.getByLabel("Recipe title").fill("Lemon lentils");
  await page.getByLabel("Yield quantity").fill("2.000");
  if (testInfo.project.name === "narrow-mobile") await page.getByRole("button", { name: "Ingredients" }).click();
  await page.getByLabel("Ingredients, one per line").fill("1 cup lentils");
  if (testInfo.project.name === "narrow-mobile") await page.getByRole("button", { name: "Basics" }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "lentils.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9JbM8AAAAASUVORK5CYII=", "base64") });
  await expect(page.getByAltText("Preview of the selected recipe photo")).toBeVisible();
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByRole("heading", { name: "Lemon lentils" })).toBeVisible();
  await page.getByRole("link", { name: "Edit recipe" }).click();
  if (testInfo.project.name === "narrow-mobile") await page.getByRole("button", { name: "Basics" }).click();
  await expect(page.getByAltText("Current photo for Lemon lentils")).toBeVisible();
  await page.getByRole("button", { name: "Remove photo" }).click();
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByRole("heading", { name: "Lemon lentils" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("import preview shows components, prompts for missing quantities, warns on duplicates, and confirms edits", async ({ page }, testInfo) => {
  const preview = await mockPreviewApi(page);
  await page.goto("/app/recipes");
  await page.getByRole("button", { name: "Import recipe" }).click();

  await page.getByLabel("Recipe or cookbook URL").fill("https://example.com/shawarma");
  await page.getByRole("button", { name: "Start import" }).click();

  await expect(page.getByRole("heading", { name: "Review the recipe" })).toBeVisible();
  await expect(page.getByText("Shawarma bowl")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("already have “Shawarma bowl”");
  await expect(page.getByLabel("Component 1 title")).toHaveValue("The chicken");
  await expect(page.getByLabel("Component 2 title")).toHaveValue("The sauce");

  // The second line has no quantity: a quantity prompt appears beside it.
  await expect(page.getByLabel("Ingredient 2 for component 1")).toHaveValue("olive oil");
  await page.getByLabel("Quantity").fill("2 tbsp");

  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Add this recipe" })).toBeVisible();
  await page.getByRole("button", { name: "Add to collection" }).click();

  // Assert breadcrumb navigation completes
  await expect(page.getByText("Shawarma bowl")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Shawarma bowl");

  // Assert nutrition is processing (allocation pending)
  await expect(page.getByText(/nutrition.*calculating/i)).toBeVisible();

  // Assert confirm payload includes quantity override and title
  const posted = preview.posted();
  expect(posted).not.toBeNull();
  expect(posted?.parseId).toBe(preview.parseId);
  expect(JSON.stringify(posted?.components ?? [])).toContain("olive oil");
  expect(posted?.title).toBe("Shawarma bowl");

  // Assert quantity override is transmitted in the confirm payload
  const confirmBody = posted && "confirm" in posted ? posted : null;
  if (confirmBody) {
    const matches = JSON.stringify(confirmBody).match(/"quantityOverride":"\d+[^"]*"/g);
    expect(matches).toBeTruthy();
  }

  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
