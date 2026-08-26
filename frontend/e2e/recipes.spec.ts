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
    if (path === "/api/v1/recipes/bulk/archive" && method === "POST") {
      deleted = true;
      return json({ results: (request.postDataJSON().recipes as Array<{ id: string; version: number }>).map((item) => ({ id: item.id, status: "archived", version: item.version + 1, code: null, message: null })) });
    }
    if (path === "/api/v1/recipes" && method === "GET") {
      return json({ items: deleted ? [] : [recipe], nextCursor: null });
    }
    if (path === "/api/v1/recipes" && method === "POST") {
      const body = request.postDataJSON();
      recipe = detail({
        ...body,
        id: recipeId,
        imageUrl: body.stagedPhotoId ? "/api/v1/media/00000000-0000-4000-8000-000000000011" : null,
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
    if (path === "/api/v1/recipes/photo-stages" && method === "POST") {
      return json({ id: "00000000-0000-4000-8000-000000000012", expiresAt: "2026-08-10T10:10:00Z" }, 201);
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

async function mockPreviewApi(page: Page, options: { pdfThumbnail?: boolean } = {}) {
  const parseId = "preview-parse-0001";
  let confirmPosted: Record<string, unknown> | null = null;
  let mergePosted: Record<string, unknown> | null = null;
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
        imageSources: options.pdfThumbnail ? [`data:image/jpeg;base64,${Buffer.from("pdf-cover").toString("base64")}`] : [],
        duplicates: [{ id: recipeId, title: "Shawarma bowl", version: 1 }],
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
      return json({ jobId, resourceId: recipeId, status: "queued" }, 202);
    }
    if (path === "/api/v1/recipes/import/merge" && method === "POST") {
      mergePosted = request.postDataJSON() as Record<string, unknown>;
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
  return { parseId, posted: () => confirmPosted, mergePosted: () => mergePosted };
}

async function openRecipeOptions(page: Page) {
  const details = page.locator("details.danger-zone");
  if (!(await details.evaluate((element: HTMLDetailsElement) => element.open))) {
    await details.locator("summary").click();
  }
}

async function openRecipeImport(page: Page) {
  await expect(page.locator(".recipe-grid, .empty-state").first()).toBeVisible();
  const directImport = page.getByRole("button", { name: "Import recipe", exact: true });
  if (await directImport.isVisible()) {
    await directImport.click();
    return;
  }
  await page.locator("summary").filter({ hasText: "Add recipe" }).click();
  await page.getByRole("button", { name: /Import a recipe/i }).click();
}

async function pasteRows(page: Page, label: string, value: string) {
  await page.getByRole("textbox", { name: label, exact: true }).evaluate((element, text) => {
    const clipboard = new DataTransfer();
    clipboard.setData("text/plain", text);
    element.dispatchEvent(new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: clipboard }));
  }, value);
}

test("manual create, edit, correction, archive, restore, and history-safe permanent delete", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto("/app/recipes/new");
  if (testInfo.project.name === "narrow-mobile") {
    await expect(page.getByRole("textbox", { name: "ingredient 1 for main recipe", exact: true })).toBeHidden();
    await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Ingredients", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "ingredient 1 for main recipe", exact: true })).toBeVisible();
    await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Recipe", exact: true }).click();
  }
  await page.getByLabel("Recipe title").fill("Protein oats");
  await page.getByLabel("Yield quantity").fill("2.000");
  if (testInfo.project.name === "narrow-mobile") await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Ingredients", exact: true }).click();
  await page.getByRole("textbox", { name: "ingredient 1 for main recipe", exact: true }).fill("1 cup rolled oats");
  if (testInfo.project.name === "narrow-mobile") await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Method", exact: true }).click();
  await captureUi(page, testInfo, "recipe-editor");
  if (testInfo.project.name !== "narrow-mobile") await captureUi(page, testInfo, "recipe-editor-ingredients", { focus: page.getByRole("textbox", { name: "ingredient 1 for main recipe", exact: true }) });
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByRole("heading", { name: "Protein oats" })).toBeVisible();
  await expect(page.locator('.recipe-saved-moment [data-companion-moment="success"]')).toBeVisible();
  await captureUi(page, testInfo, "recipe-detail");

  await page.getByRole("link", { name: "Edit recipe" }).click();
  await captureUi(page, testInfo, "recipe-editor-edit");
  await page.getByLabel("Yield quantity").fill("3.000");
  if (testInfo.project.name === "narrow-mobile") await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Method", exact: true }).click();
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.locator(".nutrition-state").filter({ hasText: "Needs review" }).first()).toBeVisible();
  await expect(page.locator('.recipe-saved-moment [data-companion-moment="success"]')).toBeVisible();

  await page.getByRole("link", { name: "Edit recipe" }).click();
  if (testInfo.project.name === "narrow-mobile") await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Finish", exact: true }).click();
  else await page.getByText("Nutrition values").click();
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
  await openRecipeImport(page);
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
  await expect(page.locator(".nutrition-state").filter({ hasText: "Needs review" }).first()).toBeVisible({ timeout: 7_000 });
  await captureUi(page, testInfo, "recipe-import-stale");
  await page.getByRole("button", { name: "Recalculate nutrition" }).click();
  await expect(page.locator(".nutrition-state").filter({ hasText: "Updating" }).first()).toBeVisible();
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

test("uses more of the wide desktop canvas for the recipe library", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await mockApi(page);
  await page.goto("/app/recipes");

  const shell = page.locator(".page-shell.recipe-library-page");
  await expect(shell).toBeVisible();

  const shellBox = await shell.boundingBox();
  expect(shellBox).not.toBeNull();
  expect(shellBox!.width).toBeGreaterThanOrEqual(1580);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("turns the mobile recipe library into a compact visual shelf", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "narrow-mobile", "The compact two-column shelf is mobile-only.");
  await mockApi(page);
  await page.goto("/app/recipes");

  await expect(page.getByRole("heading", { name: "Saved recipes" })).toBeVisible();
  const layout = await page.evaluate(() => {
    const grid = document.querySelector<HTMLElement>(".recipe-grid");
    const card = document.querySelector<HTMLElement>(".recipe-card");
    const media = document.querySelector<HTMLElement>(".recipe-card__media");
    if (!grid || !card || !media) return null;
    const gridStyle = getComputedStyle(grid);
    const cardBox = card.getBoundingClientRect();
    const mediaBox = media.getBoundingClientRect();
    return {
      columns: gridStyle.gridTemplateColumns.split(" ").length,
      cardWidth: cardBox.width,
      mediaRatio: mediaBox.width / mediaBox.height,
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      metadataDisplay: card.querySelector<HTMLElement>(".recipe-meta") ? getComputedStyle(card.querySelector<HTMLElement>(".recipe-meta")!).display : "missing",
    };
  });
  expect(layout).not.toBeNull();
  expect(layout!.columns).toBe(2);
  expect(layout!.cardWidth).toBeGreaterThan(layout!.viewportWidth * 0.4);
  expect(layout!.cardWidth).toBeLessThan(layout!.viewportWidth * 0.6);
  expect(layout!.mediaRatio).toBeGreaterThan(1.15);
  expect(layout!.metadataDisplay).toBe("none");
  expect(layout!.documentWidth).toBeLessThanOrEqual(layout!.viewportWidth);
  const textFit = await page.locator(".recipe-card").evaluateAll((cards) => cards.map((card) => {
    const metadata = card.querySelector<HTMLElement>(".recipe-meta");
    const yieldText = card.querySelector<HTMLElement>(".recipe-card__yield");
    return {
      metadataFont: metadata ? Number.parseFloat(getComputedStyle(metadata).fontSize) : 0,
      yieldFont: yieldText ? Number.parseFloat(getComputedStyle(yieldText).fontSize) : 0,
      overflows: card.scrollWidth > card.clientWidth + 1,
    };
  }));
  expect(textFit.every((item) => item.metadataFont >= 14 && item.yieldFont >= 14 && !item.overflows)).toBe(true);
});

test("makes a focused recipe-library view easy to understand and clear", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto("/app/recipes");
  await expect(page.getByRole("heading", { name: "What would you like to cook?" })).toBeVisible();
  await expect(page.locator(".recipe-card--featured")).toHaveCount(0);
  await expect(page.locator(".recipe-card__media .recipe-card__state")).toHaveCount(0);
  await expect(page.locator(".recipe-card__body .recipe-card__state")).toBeVisible();
  if (testInfo.project.name === "desktop-chromium") {
    await expect(page.locator(".recipe-card .recipe-meta__item--time svg").first()).toBeVisible();
  }
  await expect(page.getByText("Time not set")).toHaveCount(0);
  const libraryStyling = await page.evaluate(() => {
    const favorite = document.querySelector<HTMLElement>(".recipe-card__favorite-toggle");
    const discovery = document.querySelector<HTMLElement>(".recipe-discovery");
    const results = document.querySelector<HTMLElement>(".recipe-results-heading");
    const root = getComputedStyle(document.documentElement);
    return {
      favoriteColor: favorite ? getComputedStyle(favorite).color : "",
      primaryColor: root.getPropertyValue("--color-primary").trim(),
      discoveryBorders: discovery ? [getComputedStyle(discovery).borderTopWidth, getComputedStyle(discovery).borderBottomWidth] : [],
      resultsBorder: results ? getComputedStyle(results).borderBottomWidth : "",
    };
  });
  expect(libraryStyling.favoriteColor).toBe(libraryStyling.primaryColor);
  expect(libraryStyling.discoveryBorders).toEqual(["0px", "0px"]);
  expect(libraryStyling.resultsBorder).toBe("0px");
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

test("keeps recipe nutrition metrics in one evidence layer", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/app/recipes/${recipeId}`);
  await expect(page.getByRole("heading", { name: "Protein oats" })).toBeVisible();
  await expect(page.locator(".recipe-nutrition-summary__metrics")).toHaveCount(1);
  await expect(page.locator(".recipe-nutrition-overview")).toHaveCount(0);
  await page.getByText("Nutrition details and evidence").click();
  await expect(page.getByText("Ingredient coverage", { exact: true })).toBeVisible();
});

test("archives selected recipes from the library with one reversible action", async ({ page }) => {
  await mockApi(page);
  await page.goto("/app/recipes");
  await expect(page.locator(".recipe-grid")).toBeVisible();
  await page.locator("summary").filter({ hasText: "Refine recipes" }).click();
  await page.getByRole("button", { name: "Select recipes" }).click();
  await page.getByRole("checkbox", { name: "Select Protein oats" }).click();
  await page.getByRole("button", { name: "Archive 1 selected recipe" }).click();
  const [request] = await Promise.all([
    page.waitForRequest((value) => value.url().includes("/recipes/bulk/archive") && value.method() === "POST"),
    page.getByRole("button", { name: "Archive 1 recipe" }).click(),
  ]);
  expect(request.postDataJSON()).toEqual({ recipes: [{ id: recipeId, version: 1 }] });
  await expect(page.getByText("1 recipe archived.")).toBeVisible();
});

test("a handwritten recipe can gain and remove a representative photo", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto("/app/recipes/new");
  await page.getByLabel("Recipe title").fill("Lemon lentils");
  await page.getByLabel("Yield quantity").fill("2.000");
  if (testInfo.project.name === "narrow-mobile") await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Ingredients", exact: true }).click();
  await page.getByRole("textbox", { name: "ingredient 1 for main recipe", exact: true }).fill("1 cup lentils");
  if (testInfo.project.name === "narrow-mobile") await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Finish", exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: "lentils.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9JbM8AAAAASUVORK5CYII=", "base64") });
  await expect(page.locator(".thumbnail-crop-editor__preview img")).toBeVisible();
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByRole("heading", { name: "Lemon lentils" })).toBeVisible();
  await page.getByRole("link", { name: "Edit recipe" }).click();
  if (testInfo.project.name === "narrow-mobile") await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Finish", exact: true }).click();
  await expect(page.locator(".thumbnail-crop-editor__preview img")).toBeVisible();
  await page.getByRole("button", { name: "Remove photo" }).click();
  await page.getByRole("button", { name: "Remove photo" }).click();
  await page.getByRole("button", { name: "Save recipe" }).click();
  await expect(page.getByRole("heading", { name: "Lemon lentils" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("import preview shows components, prompts for missing quantities, warns on duplicates, and confirms edits", async ({ page }) => {
  const preview = await mockPreviewApi(page);
  await page.goto("/app/recipes");
  await openRecipeImport(page);

  await page.getByLabel("Recipe or cookbook URL").fill("https://example.com/shawarma");
  await page.getByRole("button", { name: "Start import" }).click();

  await expect(page.getByRole("heading", { name: "Review the recipe" })).toBeVisible();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("Shawarma bowl");
  await expect(page.getByRole("alert")).toContainText("already have “Shawarma bowl”");
  await expect(page.getByLabel("Component 1 title")).toHaveValue("The chicken");
  await expect(page.getByLabel("Component 2 title")).toHaveValue("The sauce");
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

test("merge replaces duplicate content while preserving the existing recipe identity", async ({ page }) => {
  const preview = await mockPreviewApi(page);
  await page.goto("/app/recipes");
  await openRecipeImport(page);

  await page.getByLabel("Recipe or cookbook URL").fill("https://example.com/shawarma");
  await page.getByRole("button", { name: "Start import" }).click();

  await expect(page.getByRole("heading", { name: "Review the recipe" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("already have “Shawarma bowl”");
  await expect(page.getByRole("button", { name: "Merge into existing" })).toBeVisible();

  await page.getByRole("button", { name: "Merge into existing" }).click();

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Shawarma bowl");
  const mergePosted = preview.mergePosted();
  expect(mergePosted).not.toBeNull();
  expect(mergePosted?.recipeId).toBe(recipeId);
  expect(mergePosted?.parseId).toBe(preview.parseId);
  expect(mergePosted?.expectedVersion).toBe(1);
  expect(mergePosted?.title).toBe("Shawarma bowl");
  expect(JSON.stringify(mergePosted?.components ?? [])).toContain("1 lb chicken breast");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("editor preview toggle mirrors the live draft", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto("/app/recipes/new");
  await page.getByLabel("Recipe title").fill("Sheet pan chicken");
  await page.getByLabel("Yield quantity").fill("4.000");
  if (testInfo.project.name === "narrow-mobile") await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Ingredients", exact: true }).click();
  await pasteRows(page, "ingredient 1 for main recipe", "1 chicken breast\n2 cups rice");
  if (testInfo.project.name === "narrow-mobile") await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Method", exact: true }).click();
  await pasteRows(page, "step 1 for main recipe", "Roast the chicken.\nRest before serving.");

  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("heading", { name: "Sheet pan chicken" })).toBeVisible();
  await expect(page.getByText("1 chicken breast")).toBeVisible();
  await expect(page.getByText("2 cups rice")).toBeVisible();
  await expect(page.getByLabel("Recipe preview").getByText("Roast the chicken.")).toBeVisible();
  await expect(page.getByText("4 servings")).toBeVisible();
  await captureUi(page, testInfo, "recipe-editor-preview");

  await page.getByRole("button", { name: "Edit" }).click();
  await expect(page.getByLabel("Recipe title")).toHaveValue("Sheet pan chicken");
  if (testInfo.project.name === "narrow-mobile") await page.getByLabel("Recipe editor progress").getByRole("button", { name: "Ingredients", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "ingredient 1 for main recipe", exact: true })).toHaveValue("1 chicken breast");
  await expect(page.getByRole("textbox", { name: "ingredient 2 for main recipe", exact: true })).toHaveValue("2 cups rice");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("a PDF thumbnail selected at import is confirmed with pdf_thumbnail kind and attach feedback", async ({ page }) => {
  const preview = await mockPreviewApi(page, { pdfThumbnail: true });
  await page.goto("/app/recipes");
  await openRecipeImport(page);

  await page.getByLabel("Recipe or cookbook URL").fill("https://example.com/cookbook.pdf");
  await page.getByRole("button", { name: "Start import" }).click();

  await expect(page.getByRole("heading", { name: "Review the recipe" })).toBeVisible();
  await expect(page.getByLabel("Thumbnail 1")).toBeChecked();
  await page.getByRole("button", { name: "Keep this import" }).click();
  await expect(page.getByText(/cover photo will be attached/i)).toBeVisible();

  await page.getByRole("button", { name: "Add to collection" }).click();

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Shawarma bowl");
  const posted = preview.posted();
  expect(posted).not.toBeNull();
  expect(posted?.imageSourceKind).toBe("pdf_thumbnail");
  expect(typeof posted?.imageSource).toBe("string");
  expect(String(posted?.imageSource ?? "")).toMatch(/^data:image\/jpeg;base64,/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
