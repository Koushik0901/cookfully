import { expect, test, type Page } from "@playwright/test";

import { accessibleRecipe, accessibleRecipeId } from "./support/mock-accessible-recipe";
import { captureUi } from "./support/visual-audit";

const ingredients = ["600 g chicken thighs", "150 g plain yogurt", "2 cloves garlic, grated", "300 g basmati rice", "40 g butter", "400 g crushed tomatoes"];
const steps = [
  "Stir the chicken with yogurt, half the garlic and ginger, and the garam masala. Leave it in the fridge for at least 30 minutes.",
  "Start the rice. Melt the butter in a wide pan and brown the chicken in two batches.",
  "In the same pan, soften the onion with the rest of the garlic and ginger. Add the tomatoes and simmer until thick and glossy.",
  "Return the chicken, pour in the cream, and cook gently until the chicken is done. Scatter with cilantro and serve over the rice.",
];

async function mockCookRecipe(page: Page) {
  const base = accessibleRecipe();
  const recipe = {
    ...base,
    title: "Butter chicken with basmati",
    status: "ready",
    archivedFromStatus: null,
    activeJob: null,
    ingredients: ingredients.map((originalText, position) => ({
      ...base.ingredients[0],
      id: `00000000-0000-4000-8000-0000000009${position}0`,
      position,
      originalText,
    })),
    instructions: steps.map((text, position) => ({ position, text })),
  };
  await page.context().addCookies([{ name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA" });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === `/api/v1/recipes/${accessibleRecipeId}`) return json(recipe);
    return json({ code: "not_found", status: 404, title: "Not found" }, 404);
  });
}

test("cook mode steps with buttons and keyboard and keeps controls in view", async ({ page }, testInfo) => {
  await page.addInitScript(() => window.sessionStorage.clear());
  await mockCookRecipe(page);
  await page.goto(`/app/recipes/${accessibleRecipeId}/cook`);

  const counter = page.locator(".cook-mode__stage-heading .eyebrow");
  await expect(counter).toHaveText("Step 1 of 4");
  await expect(page.getByRole("button", { name: "Previous" })).toBeDisabled();
  await page.waitForTimeout(700);
  await captureUi(page, testInfo, "cook-mode-first");

  await page.getByRole("button", { name: "Next step" }).click();
  await expect(counter).toHaveText("Step 2 of 4");
  await page.getByRole("button", { name: "Next step" }).click();
  await expect(counter).toHaveText("Step 3 of 4");
  await expect(page.getByRole("button", { name: "Next step" })).toBeVisible();
  await page.waitForTimeout(700);
  await captureUi(page, testInfo, "cook-mode-middle");
  await page.getByRole("button", { name: "Start 15 min timer" }).click();
  await expect(page.getByRole("status")).toContainText("Timer set for 15 min");

  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("ArrowLeft");
  await expect(counter).toHaveText("Step 2 of 4");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(counter).toHaveText("Step 4 of 4");
  await expect(page.getByRole("button", { name: "Finish cooking" })).toBeVisible();
  await page.waitForTimeout(700);
  await captureUi(page, testInfo, "cook-mode-last");

  // Controls stay inside the viewport and the step view does not scroll the page.
  const viewport = page.viewportSize()!;
  const box = await page.getByRole("button", { name: "Finish cooking" }).boundingBox();
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
  expect(box!.height).toBeGreaterThanOrEqual(56);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("cook mode ingredients are one tap away", async ({ page }, testInfo) => {
  await page.addInitScript(() => window.sessionStorage.clear());
  await mockCookRecipe(page);
  await page.goto(`/app/recipes/${accessibleRecipeId}/cook`);
  await expect(page.locator(".cook-mode__stage-heading .eyebrow")).toHaveText("Step 1 of 4");
  const summary = page.locator(".cook-mode__ingredients summary");
  const open = await page.locator(".cook-mode__ingredients details").evaluate((el) => (el as HTMLDetailsElement).open);
  if (!open) await summary.click();
  await expect(page.getByText("600 g chicken thighs")).toBeVisible();
  await expect(page.getByText("400 g crushed tomatoes")).toBeVisible();
  await captureUi(page, testInfo, "cook-mode-ingredients");
});
