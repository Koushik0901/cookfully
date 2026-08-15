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
    if (path === "/api/v1/auth/session" && request.method() === "DELETE") {
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/v1/access-tokens") return route.fulfill({ json: [] });
    if (path === "/api/v1/reference-data/status") {
      return route.fulfill({
        json: {
          available: false,
          missing: ["foundation", "sr_legacy"],
          releases: [],
          requestedDatasets: null,
          job: null,
        },
      });
    }
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

  await page.getByRole("tab", { name: "Connections" }).click();
  await expect(page.getByRole("heading", { name: "Agent access" })).toBeVisible();
  await captureUi(page, testInfo, "settings-connections");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("the shared shell exposes account settings and a complete sign-out flow", async ({ page }, testInfo) => {
  await mockSettingsApi(page);
  await page.goto("/app/settings");

  if (testInfo.project.name === "narrow-mobile") {
    const more = page.locator(".mobile-nav__more");
    await more.getByText("More", { exact: true }).click();
    await expect(more.getByRole("menuitem", { name: "Settings" })).toBeVisible();
    await expect(more.getByRole("menuitem", { name: "Sign out" })).toBeVisible();
    await captureUi(page, testInfo, "shell-account-controls");

    await more.getByRole("menuitem", { name: "Settings" }).click();
    await expect(more).not.toHaveAttribute("open", "");
    await expect(more).toHaveClass(/mobile-nav__more--active/);
    await more.getByText("More", { exact: true }).click();
    await more.getByRole("menuitem", { name: "Sign out" }).click();
  } else {
    const account = page.getByRole("navigation", { name: "Account" });
    await expect(account.getByRole("link", { name: "Settings" })).toBeVisible();
    await expect(account.getByRole("button", { name: "Sign out" })).toBeVisible();
    await captureUi(page, testInfo, "shell-account-controls");
    await account.getByRole("button", { name: "Sign out" }).click();
  }

  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  if (testInfo.project.name === "desktop-chromium") {
    await expect
      .poll(() => page.locator(".auth-visual img").evaluate((image: HTMLImageElement) => image.complete && image.naturalWidth > 0))
      .toBe(true);
  }
  await captureUi(page, testInfo, "signed-out");
});

test("settings Nutrition data tab shows install controls", async ({ page }) => {
  await mockSettingsApi(page);
  await page.goto("/app/settings");
  await page.getByRole("tab", { name: "Nutrition data" }).click();
  await expect(page.getByRole("button", { name: "Install Foundation + SR Legacy" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Install Branded foods" })).toBeVisible();
});
