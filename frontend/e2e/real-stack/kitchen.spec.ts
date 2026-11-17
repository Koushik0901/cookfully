import { expect, test, type Page } from "@playwright/test";

const ownerEmail = process.env.E2E_OWNER_EMAIL ?? "owner@example.com";
const ownerPassword = process.env.E2E_OWNER_PASSWORD;

test.beforeAll(() => {
  if (!ownerPassword) throw new Error("Set E2E_OWNER_PASSWORD to the stack's owner bootstrap password.");
});

async function signIn(page: Page) {
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await page.getByLabel("Email").fill(ownerEmail);
  await page.getByLabel("Password", { exact: true }).fill(ownerPassword ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeHidden();
}

test("the edge, API, database and broker report healthy", async ({ request }) => {
  const response = await request.get("/api/v1/health");
  expect(response.ok()).toBe(true);
  expect(await response.json()).toMatchObject({ status: "ok", database: "ok", broker: "ok" });
});

test("the owner signs in, writes a recipe, finds it, edits it, and deletes it", async ({ page }) => {
  const title = `Smoke test lentils ${Date.now()}`;

  await test.step("sign in through the real session API", async () => {
    await signIn(page);
  });

  await test.step("write a recipe", async () => {
    await page.goto("/app/recipes/new");
    await page.getByLabel("Recipe title").fill(title);
    await page.getByLabel("Yield quantity").fill("2.000");
    await page.getByRole("textbox", { name: "ingredient 1 for main recipe", exact: true }).fill("1 cup red lentils");
    await page.getByRole("button", { name: "Save recipe" }).click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  });

  await test.step("a worker picks up its background job", async () => {
    // Saving queues a job through the outbox to a Celery worker. This is the only check that those
    // pieces are wired together, because the mocked suite never starts them. A fresh stack has no
    // nutrition reference data installed, so the job may legitimately wait to retry; what must not
    // happen is the job sitting untouched in the queue.
    const recipeId = /\/app\/recipes\/([0-9a-f-]{36})/.exec(page.url())?.[1];
    expect(recipeId, "the saved recipe's id is in the URL").toBeTruthy();
    await expect
      .poll(
        async () => {
          const response = await page.request.get(`/api/v1/recipes/${recipeId}`);
          if (!response.ok()) return `request failed (${response.status()})`;
          const { activeJob } = (await response.json()) as { activeJob: { attempt: number } | null };
          return activeJob === null || activeJob.attempt >= 1 ? "picked up" : "still queued";
        },
        { timeout: 60_000, message: "a worker should start the recipe's background job" },
      )
      .toBe("picked up");
  });

  await test.step("find it in the library", async () => {
    await page.goto("/app/recipes");
    await expect(page.getByText(title).first()).toBeVisible();
    await page.getByText(title).first().click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  });

  await test.step("edit it and see the change persisted by the API", async () => {
    await page.getByRole("link", { name: "Edit recipe" }).click();
    await page.getByLabel("Yield quantity").fill("3.000");
    await page.getByRole("button", { name: "Save recipe" }).click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await page.reload();
    // The servings appear in several places (some only on other layouts); one visible match is enough.
    await expect(page.getByText("3 servings").locator("visible=true").first()).toBeVisible();
  });

  await test.step("archive and permanently delete it", async () => {
    await openRecipeOptions(page);
    await page.getByRole("button", { name: "Archive recipe" }).click();
    await page.getByRole("button", { name: "Archive", exact: true }).click();
    await openRecipeOptions(page);
    await page.getByRole("button", { name: "Permanently delete recipe" }).click();
    await page.getByRole("button", { name: "Delete permanently" }).click();
    await page.goto("/app/recipes");
    await expect(page.getByText(title)).toHaveCount(0);
  });
});

async function openRecipeOptions(page: Page) {
  const details = page.locator("details.danger-zone");
  if (!(await details.evaluate((element: HTMLDetailsElement) => element.open))) {
    await details.locator("summary").click();
  }
}
