import { expect, type Page, test } from "@playwright/test";
import { captureUi } from "./support/visual-audit";
import axe from "axe-core";

const food = {
  id: "00000000-0000-4000-8000-000000000001",
  displayName: "Whey Protein Powder",
  normalizedName: "whey protein powder",
  brand: "Optimum Nutrition",
  caloriesKcal: "120",
  proteinG: "24",
  carbohydrateG: "3",
  fatG: "1.5",
  basisGrams: "31",
  typicalServingG: "31",
  typicalServingUnit: "scoop",
  version: 1,
};

async function mockFoodsApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const fulfill = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/preferences") return fulfill({ timezone: "America/Vancouver", weekStartsOn: 1, version: 1 });
    if (path === "/api/v1/foods/user" && request.method() === "GET") return fulfill([food]);
    if (path === "/api/v1/foods/user" && request.method() === "POST") return fulfill({ ...food, ...request.postDataJSON(), id: "00000000-0000-4000-8000-000000000002" }, 201);
    return fulfill({ code: "not_found", title: "Not found" }, 404);
  });
}

test("food labels remain purposeful, accessible, and contained", async ({ page }, testInfo) => {
  await mockFoodsApi(page);
  await page.goto("/app/foods");

  await expect(page.getByRole("heading", { name: "Foods you know best" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Whey Protein Powder" })).toBeVisible();
  await expect(page.getByLabel("Nutrition for Whey Protein Powder")).toContainText("24 g");
  await captureUi(page, testInfo, "foods");
  const help = page.locator("details.owner-foods-help");
  await expect(help.getByText("When to save a food", { exact: true })).toBeVisible();
  await expect(help.getByText("Copy the label once", { exact: true })).not.toBeVisible();
  await help.getByText("When to save a food", { exact: true }).click();
  await expect(help.getByText("Copy the label once", { exact: true })).toBeVisible();
  await captureUi(page, testInfo, "foods-help", { focus: help });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.getByRole("button", { name: "New food" }).click();
  await captureUi(page, testInfo, "foods-create-dialog");
  const dialog = page.getByRole("dialog", { name: "Add a food you know" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Identify the food")).toBeVisible();
  await expect(dialog.getByText("Copy one label serving")).toBeVisible();

  const dialogBox = await dialog.boundingBox();
  const viewport = page.viewportSize();
  expect(dialogBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(dialogBox!.x).toBeGreaterThanOrEqual(0);
  expect(dialogBox!.y).toBeGreaterThanOrEqual(0);
  expect(dialogBox!.x + dialogBox!.width).toBeLessThanOrEqual(viewport!.width);
  expect(dialogBox!.y + dialogBox!.height).toBeLessThanOrEqual(viewport!.height);
  expect(await page.evaluate(() => document.elementFromPoint(4, 4)?.classList.contains("dialog-overlay"))).toBe(true);

  await page.addScriptTag({ content: axe.source });
  const serious = await page.evaluate(async () => {
    const result = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } });
    return result.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""));
  });
  expect(serious).toEqual([]);
});

declare global {
  interface Window {
    axe: typeof axe;
  }
}
