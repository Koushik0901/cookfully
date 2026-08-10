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

  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);

  await expect(page.getByText(/deliberately-long-unbroken-preparation-token/)).toBeVisible();
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
