import { expect, test } from "@playwright/test";
import { captureUi } from "./support/visual-audit";

test("loads at desktop and narrow-mobile project sizes", async ({ page }, testInfo) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /Good food\. Clear choices/i })).toBeVisible();
  await expect(page.locator("body")).not.toHaveCSS("overflow-x", "scroll");
  await captureUi(page, testInfo, "landing");
});

test("sign-in is calm and contained", async ({ page }, testInfo) => {
  await page.route("**/api/v1/owner/preferences", (route) => route.fulfill({ status: 401 }));
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await captureUi(page, testInfo, "sign-in");
});

