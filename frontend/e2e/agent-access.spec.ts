import { expect, type Page, test } from "@playwright/test";

const existingId = "00000000-0000-4000-8000-000000000101";

type TokenFixture = {
  id: string;
  name: string;
  scopes: string[];
  createdAt: string;
  expiresAt: string | null;
  lastUsedAt: string | null;
  revokedAt: string | null;
};

async function mockAgentAccessApi(page: Page) {
  let tokens: TokenFixture[] = [
    {
      id: existingId,
      name: "Read-only coach",
      scopes: ["goals:read", "plans:read"],
      createdAt: "2026-03-01T12:00:00Z",
      expiresAt: null,
      lastUsedAt: null,
      revokedAt: null,
    },
  ];
  await page.context().addCookies([
    { name: "cookfully_csrf", value: "agent-access-csrf", domain: "127.0.0.1", path: "/" },
  ]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (path === "/api/v1/owner/preferences") {
      return route.fulfill({
        json: { timezone: "America/Vancouver", weekStartsOn: 1, version: 1 },
      });
    }
    if (path === "/api/v1/access-tokens" && method === "GET") {
      return route.fulfill({ json: tokens });
    }
    if (path === "/api/v1/access-tokens" && method === "POST") {
      const value = request.postDataJSON();
      const created = {
        id: "00000000-0000-4000-8000-000000000202",
        ...value,
        createdAt: "2026-03-11T19:00:00Z",
        lastUsedAt: null,
        revokedAt: null,
      };
      tokens = [...tokens, created];
      return route.fulfill({
        status: 201,
        json: { ...created, secret: "cookfully_once_only_e2e_secret_12345678901234567890" },
      });
    }
    if (path.startsWith("/api/v1/access-tokens/") && method === "DELETE") {
      const id = path.split("/").at(-1);
      tokens = tokens.map((token) =>
        token.id === id ? { ...token, revokedAt: "2026-03-11T19:05:00Z" } : token,
      );
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

test("creates, stores once, and revokes scoped agent tokens without overflow", async ({ page }) => {
  await mockAgentAccessApi(page);
  await page.goto("/app/agent-access");
  await expect(page.getByRole("heading", { name: "Agent access" })).toBeVisible();
  await expect(page.getByRole("article", { name: "Read-only coach" })).toBeVisible();
  await expect(page.getByLabel("Read meal plans")).toBeChecked();
  await expect(page.getByLabel("Write meal plans")).not.toBeChecked();

  await page.getByLabel("Token name").fill("Workout assistant");
  await page.getByLabel("Write meal plans").check();
  await page.getByRole("button", { name: "Create access token" }).click();
  const oneTime = page.getByRole("region", { name: "One-time token secret" });
  await expect(oneTime).toContainText("cookfully_once_only_e2e_secret_12345678901234567890");
  await expect(oneTime).toContainText(/shown only once/i);
  await oneTime.getByRole("button", { name: "I have stored it" }).click();
  await expect(page.getByText("cookfully_once_only_e2e_secret_12345678901234567890")).toHaveCount(0);

  const existing = page.getByRole("article", { name: "Read-only coach" });
  await existing.getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("button", { name: "Revoke token" }).click();
  await expect(page.getByText("Token revoked. Existing connections can no longer use it.")).toBeVisible();
  await expect(page.getByRole("article", { name: "Read-only coach" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});
