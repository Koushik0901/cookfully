import { expect, test } from "@playwright/test";

import {
  accessibleRecipeId,
  mockAccessibleRecipeApi,
} from "./support/mock-accessible-recipe";

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

  await expect(page.getByText("100 g extra firm tofu")).toBeVisible();
  await page.getByText("Ingredient matching and assumptions").click();
  await expect(page.getByText(/deliberately-long-unbroken-preparation-token/)).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
  const controls = page.locator("button, input, select, textarea");
  for (let index = 0; index < await controls.count(); index += 1) {
    const box = await controls.nth(index).boundingBox();
    if (box) expect(box.height).toBeGreaterThanOrEqual(44);
  }
});

test("destructive dialog remains fully contained at every configured viewport", async ({ page }) => {
  await mockAccessibleRecipeApi(page);
  await page.goto(`/app/recipes/${accessibleRecipeId}`);
  await page.getByRole("button", { name: "Permanently delete recipe" }).click();

  const box = await page.getByRole("dialog").boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);
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

  await page.getByRole("checkbox").click();
  await expect(page.getByText("Everything’s ready to cook.")).toBeVisible();
  await page.getByRole("button", { name: "Finish cooking" }).click();
  await expect(page.getByRole("heading", { name: "Time to eat." })).toBeVisible();
  await expect(page.locator(".cook-mode__complete-media img")).toBeVisible();
  await page.getByRole("button", { name: "Cook again" }).click();
  await expect(page.getByText("Cook and portion.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
