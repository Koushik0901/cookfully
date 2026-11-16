import { expect, type Page, type TestInfo } from "@playwright/test";

/**
 * The control that opens the recipe editor from a recipe's detail page.
 *
 * Desktop shows an "Edit recipe" button in the hero; phones show a compact bottom-bar action whose
 * visible text is "Edit" but whose accessible name is also "Edit recipe", so one locator serves both.
 */
export function editRecipeLink(page: Page) {
  return page.getByRole("link", { name: "Edit recipe" });
}

/**
 * Assert that a recipe's background processing is announced.
 *
 * Desktop spells out the nutrition work. Phones show a concise "Updating your recipe" banner
 * and keep the detailed wording in the Nutrition tab, so check what each layout shows up front.
 */
export async function expectProcessingNotice(page: Page, testInfo: TestInfo, desktopText: RegExp) {
  if (testInfo.project.name === "narrow-mobile") {
    await expect(page.getByRole("status").getByText("Updating your recipe")).toBeVisible();
  } else {
    await expect(page.getByText(desktopText)).toBeVisible();
  }
}
