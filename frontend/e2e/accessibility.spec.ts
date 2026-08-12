import { expect, test } from "@playwright/test";
import axe from "axe-core";

import {
  accessibleRecipeId,
  mockAccessibleRecipeApi,
} from "./support/mock-accessible-recipe";

async function seriousAxeViolations(page: import("@playwright/test").Page) {
  await page.addScriptTag({ content: axe.source });
  return page.evaluate(async () => {
    const result = await window.axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
    });
    return result.violations.filter((violation) =>
      ["serious", "critical"].includes(violation.impact ?? ""),
    );
  });
}

declare global {
  interface Window {
    axe: typeof axe;
  }
}

test("keyboard focus, contrast, landmarks, and reduced motion meet the release baseline", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");

  await page.keyboard.press("Tab");
  const openPlanner = page.getByRole("link", { name: "Open Cookfully" });
  await expect(openPlanner).toBeFocused();
  const focusStyle = await openPlanner.evaluate((element) => {
    const style = getComputedStyle(element);
    return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth };
  });
  expect(focusStyle.outlineStyle).not.toBe("none");
  expect(Number.parseFloat(focusStyle.outlineWidth)).toBeGreaterThanOrEqual(2);

  await expect(page.getByRole("main").first()).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: /Good food\. Clear choices/i })).toBeVisible();
  expect(await seriousAxeViolations(page)).toEqual([]);

  const reducedMotion = await page.locator("body").evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      animationDuration: style.animationDuration,
      transitionDuration: style.transitionDuration,
    };
  });
  expect(["0s", "0.00001s", "1e-05s"]).toContain(reducedMotion.animationDuration);
  expect(["0s", "0.00001s", "1e-05s"]).toContain(reducedMotion.transitionDuration);
});

test("polling announcements and destructive confirmation preserve screen-reader and focus behavior", async ({
  page,
}) => {
  await mockAccessibleRecipeApi(page);
  await page.goto(`/app/recipes/${accessibleRecipeId}`);

  const status = page.getByLabel("Nutrition processing status").getByRole("status");
  await expect(status).toHaveAttribute("aria-live", "polite");
  await expect(status).toHaveText("running");
  await expect(page.locator("nav:visible").first()).toBeVisible();
  await expect(page.getByRole("main").first()).toBeVisible();
  await expect(page.getByLabel("Nutrition field")).toBeVisible();

  const trigger = page.getByRole("button", { name: "Permanently delete recipe" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Permanently delete this recipe?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/historical plan and grocery records remain detached/i)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();

  expect(await seriousAxeViolations(page)).toEqual([]);
});
