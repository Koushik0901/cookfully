import { expect, type Page, test } from "@playwright/test";

import { captureUi } from "./support/visual-audit";

async function mockSettingsApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/owner/preferences") {
      return route.fulfill({
        json: {
          displayName: "Koush",
          timezone: "America/Vancouver",
          weekStartsOn: 1,
          version: 1,
        },
      });
    }
    if (path === "/api/v1/auth/sessions") {
      return route.fulfill({
        json: {
          sessions: [
            {
              id: "00000000-0000-4000-8000-000000000901",
              clientLabel: "Chrome on Windows",
              createdAt: "2026-08-01T18:00:00Z",
              lastSeenAt: "2026-08-13T18:00:00Z",
              isCurrent: true,
            },
            {
              id: "00000000-0000-4000-8000-000000000902",
              clientLabel: "Safari on iPhone",
              createdAt: "2026-08-08T18:00:00Z",
              lastSeenAt: "2026-08-12T18:00:00Z",
              isCurrent: false,
            },
          ],
        },
      });
    }
    if (path === "/api/v1/access-tokens") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

test("settings sections keep distinct, contained workspaces", async ({ page }, testInfo) => {
  await mockSettingsApi(page);
  await page.goto("/app/settings");

  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Account" })).toBeVisible();
  await captureUi(page, testInfo, "settings-account");

  await page.getByRole("tab", { name: "Security" }).click();
  await expect(page.getByRole("heading", { name: "Change password" })).toBeVisible();
  await captureUi(page, testInfo, "settings-security");

  await page.getByRole("tab", { name: "System access" }).click();
  await expect(page.getByRole("heading", { name: "Agent access" })).toBeVisible();
  await captureUi(page, testInfo, "settings-system");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
