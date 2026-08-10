import { expect, test } from "@playwright/test";

test("loads at desktop and narrow-mobile project sizes", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Vigor & Vine" })).toBeVisible();
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");
});

