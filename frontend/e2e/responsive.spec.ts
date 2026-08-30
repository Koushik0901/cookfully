import { expect, test } from "@playwright/test";

import {
  accessibleRecipeId,
  mockAccessibleRecipeApi,
} from "./support/mock-accessible-recipe";
import { captureUi } from "./support/visual-audit";

test("desktop and 390x844 layouts contain long content without document overflow", async ({
  page,
}, testInfo) => {
  await mockAccessibleRecipeApi(page);
  await page.goto(`/app/recipes/${accessibleRecipeId}`);

  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();
  if (testInfo.project.name === "narrow-mobile") {
    expect(viewport).toEqual({ width: 390, height: 844 });
  } else {
    expect(viewport!.width).toBeGreaterThanOrEqual(1000);
  }

  await expect(page.getByText(/200 g extra-firm tofu/)).toBeVisible();
  await expect(page.getByText(/deliberately-long-unbroken-preparation-token/)).toBeVisible();
  await captureUi(page, testInfo, "recipe-evidence", { focus: page.getByText(/deliberately-long-unbroken-preparation-token/) });

  if (testInfo.project.name === "narrow-mobile") {
    await page.getByRole("button", { name: "Nutrition" }).click();
    await expect(page.locator(".recipe-nutrition-drawer")).toHaveAttribute("open", "");
    await expect(page.getByRole("link", { name: "Start cooking" })).toHaveCount(1);
  }

  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
  if (testInfo.project.name === "narrow-mobile") {
    const navItems = page.locator(
      ".mobile-nav > .mobile-nav__link, .mobile-nav > .mobile-nav__more > .mobile-nav__more-trigger",
    );
    await expect(navItems).toHaveCount(5);
    for (let index = 0; index < await navItems.count(); index += 1) {
      for (const element of [navItems.nth(index), navItems.nth(index).locator("svg"), navItems.nth(index).locator("span")]) {
        const box = await element.boundingBox();
        expect(box).not.toBeNull();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
      }
    }
    const navGeometry = await navItems.evaluateAll((items) => items.map((item) => {
      const box = item.getBoundingClientRect();
      return { x: box.x, width: box.width, height: box.height, center: box.x + (box.width / 2) };
    }));
    expect(new Set(navGeometry.map((item) => Math.round(item.width))).size).toBe(1);
    expect(new Set(navGeometry.map((item) => Math.round(item.height))).size).toBe(1);
    expect(navGeometry.map((item) => Math.round(item.center))).toEqual([...navGeometry].sort((a, b) => a.center - b.center).map((item) => Math.round(item.center)));
    const shellGeometry = await page.evaluate(() => {
      const brand = document.querySelector<HTMLElement>(".planner-shell__mobile-brand");
      const nav = document.querySelector<HTMLElement>(".mobile-nav");
      return {
        brandBorder: brand ? getComputedStyle(brand).borderBottomWidth : null,
        navBorder: nav ? getComputedStyle(nav).borderTopWidth : null,
      };
    });
    expect(shellGeometry).toEqual({ brandBorder: "0px", navBorder: "0px" });
  }
  const controls = page.locator("button, input, select, textarea");
  for (let index = 0; index < await controls.count(); index += 1) {
    const control = controls.nth(index);
    if (!(await control.isVisible())) continue;
    const box = await control.boundingBox();
    if (box) expect(box.height).toBeGreaterThanOrEqual(44);
  }
});

test("destructive dialog remains fully contained at every configured viewport", async ({ page }, testInfo) => {
  await mockAccessibleRecipeApi(page);
  await page.goto(`/app/recipes/${accessibleRecipeId}`);
  await page.getByText("More recipe options").click();
  await page.getByRole("button", { name: "Permanently delete recipe" }).click();
  await captureUi(page, testInfo, "recipe-delete-dialog");

  const box = await page.getByRole("dialog").boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);
});

test("320px layouts have no width floor or masked horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  await mockAccessibleRecipeApi(page);
  await page.goto(`/app/recipes/${accessibleRecipeId}`);

  await expect(page.getByText(/deliberately-long-unbroken-preparation-token/)).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    htmlMinWidth: getComputedStyle(document.documentElement).minWidth,
    bodyMinWidth: getComputedStyle(document.body).minWidth,
    bodyOverflowX: getComputedStyle(document.body).overflowX,
  }));

  expect(dimensions).toMatchObject({
    viewportWidth: 320,
    htmlMinWidth: "0px",
    bodyMinWidth: "0px",
    bodyOverflowX: "visible",
  });
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
});

test("tablet keeps a compact kitchen rail instead of inheriting phone navigation", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 900 });
  await mockAccessibleRecipeApi(page);
  await page.goto(`/app/recipes/${accessibleRecipeId}`);

  await expect(page.locator(".planner-nav")).toBeVisible();
  await expect(page.locator(".mobile-nav")).toBeHidden();
  await expect(page.getByRole("link", { name: "Recipes" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Goals" })).toBeHidden();

  const content = await page.locator(".planner-shell__content").boundingBox();
  expect(content).not.toBeNull();
  expect(content!.x).toBe(112);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("mobile keeps secondary places in a deliberate More menu", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "narrow-mobile", "This navigation pattern is mobile-only.");
  await mockAccessibleRecipeApi(page);
  await page.goto(`/app/recipes/${accessibleRecipeId}`);

  const more = page.locator(".mobile-nav__more");
  await more.getByText("More", { exact: true }).click();
  await expect(more.getByRole("button", { name: "More" })).toHaveAttribute("aria-expanded", "true");
  await expect(more.getByRole("menuitem", { name: "Pantry" })).toBeVisible();
  await expect(more.getByRole("menuitem", { name: "Foods" })).toBeVisible();
  await expect(more.getByRole("menuitem", { name: "Goals" })).toBeVisible();
  await expect(more.getByRole("menuitem", { name: "Settings" })).toBeVisible();
  await expect(more.getByRole("menuitem", { name: "Sign out" })).toBeVisible();
  await captureUi(page, testInfo, "mobile-more-menu");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("recipes grid scales from one to four columns without oversized cards", async ({ page }) => {
  // Keep phone layouts compact at two columns, use two columns at compact desktop widths,
  // and add columns as the recipe surface has room to breathe.
  // Mock minimal recipes API so .recipe-grid is rendered in both viewports.
  const recipeId = "00000000-0000-4000-8000-000000000001";
  const collection = { id: "00000000-0000-4000-8000-000000000010", name: "Weeknight favourites", position: 0, version: 1, recipeCount: 0 };
  const recipe = {
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
      assumptions: [],
      corrections: [],
    },
    version: 1,
    updatedAt: "2026-08-10T10:00:00Z",
    ingredients: [],
    instructions: [],
    activeJob: null,
  };
  await page.context().addCookies([{ name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA" });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/recipes/collections" && method === "GET") return json([collection]);
    if (path === "/api/v1/recipes" && method === "GET") return json({ items: [recipe], nextCursor: null });
    if (path.startsWith("/api/v1/recipes/") && method === "GET") return json(recipe);
    return json({ code: "not_found", title: "Not found", status: 404 }, 404);
  });

  // Mobile: 390×844 → two compact columns
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/recipes");
  await expect(page.locator(".recipe-grid").first()).toBeVisible();
  const mobileColumns = await page.locator(".recipe-grid").first().evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length);
  expect(mobileColumns).toBe(2);
  const mobileGrid = await page.locator(".recipe-grid").first().evaluate((element) => getComputedStyle(element).gridTemplateColumns);
  expect(mobileGrid.trim().split(" ").length).toBe(2);

  // Desktop: 1024×900 → two columns repeat(2, ...)
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.waitForFunction(() => {
    const grid = document.querySelector<HTMLElement>(".recipe-grid");
    return grid ? getComputedStyle(grid).gridTemplateColumns.split(" ").length === 2 : false;
  });
  const desktopColumns = await page.locator(".recipe-grid").first().evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length);
  expect(desktopColumns).toBe(2);
  const desktopGrid = await page.locator(".recipe-grid").first().evaluate((element) => getComputedStyle(element).gridTemplateColumns);
  expect(desktopGrid.trim().split(" ").length).toBe(2);

  // Standard desktop: 1280×900 → three columns
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.waitForFunction(() => {
    const grid = document.querySelector<HTMLElement>(".recipe-grid");
    return grid ? getComputedStyle(grid).gridTemplateColumns.split(" ").length === 3 : false;
  });
  expect(await page.locator(".recipe-grid").first().evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length)).toBe(3);

  // Wide desktop: 2209×1272 → four columns
  await page.setViewportSize({ width: 2209, height: 1272 });
  await page.waitForFunction(() => {
    const grid = document.querySelector<HTMLElement>(".recipe-grid");
    return grid ? getComputedStyle(grid).gridTemplateColumns.split(" ").length === 4 : false;
  });
  expect(await page.locator(".recipe-grid").first().evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length)).toBe(4);
});

test("cook mode takes over the viewport and adapts its ingredient checklist", async ({ page }, testInfo) => {
  await mockAccessibleRecipeApi(page);
  await page.goto(`/app/recipes/${accessibleRecipeId}/cook`);

  const cookMode = page.locator(".cook-mode");
  await expect(cookMode).toBeVisible();
  await expect(page.getByText("Cook and portion.")).toBeVisible();
  const viewport = page.viewportSize();
  const box = await cookMode.boundingBox();
  expect(viewport).not.toBeNull();
  expect(box).not.toBeNull();
  expect(box!.x).toBe(0);
  expect(box!.y).toBe(0);
  expect(Math.abs(box!.width - viewport!.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(box!.height - viewport!.height)).toBeLessThanOrEqual(1);
  expect(await page.evaluate(() => document.elementFromPoint(4, 4)?.closest(".cook-mode") !== null)).toBe(true);

  const ingredients = page.locator(".cook-mode__ingredients details");
  const shouldStartOpen = testInfo.project.name !== "narrow-mobile";
  expect(await ingredients.evaluate((element) => (element as HTMLDetailsElement).open)).toBe(shouldStartOpen);
  if (!shouldStartOpen) await page.locator(".cook-mode__ingredients summary").click();

  await captureUi(page, testInfo, "cook-mode");

  await page.getByRole("checkbox").click();
  await expect(page.getByText("Everything’s ready to cook.")).toBeVisible();
  await page.getByRole("button", { name: "Finish cooking" }).click();
  await expect(page.getByRole("heading", { name: "Time to eat." })).toBeVisible();
  await expect(page.locator('.cook-mode__complete [data-companion-moment="milestone"]')).toBeVisible();
  await expect(page.locator(".cook-mode__complete-media img")).toBeVisible();
  await captureUi(page, testInfo, "cook-mode-complete");
  await page.getByRole("button", { name: "Cook again" }).click();
  await expect(page.getByText("Cook and portion.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("cook mode keeps its compact layout and ingredient disclosure on one breakpoint contract", async ({ page }) => {
  await mockAccessibleRecipeApi(page);

  for (const [width, compact] of [[960, true], [980, true], [1023, true], [1024, false]] as const) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/app/recipes/${accessibleRecipeId}/cook`);

    const state = await page.locator(".cook-mode__ingredients details").evaluate((ingredients) => {
      const body = document.querySelector<HTMLElement>(".cook-mode__body");
      return {
        ingredientsOpen: (ingredients as HTMLDetailsElement).open,
        columnCount: body ? getComputedStyle(body).gridTemplateColumns.split(" ").length : 0,
      };
    });

    expect(state.columnCount).toBe(compact ? 1 : 2);
    expect(state.ingredientsOpen).toBe(!compact);
  }
});
