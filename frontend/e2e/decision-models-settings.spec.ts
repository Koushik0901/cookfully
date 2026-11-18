import { expect, type Page, test } from "@playwright/test";
import axe from "axe-core";

const PURPOSES = [
  "match_referee",
  "food_labels",
  "import_line_gate",
  "import_screen",
  "cleanup_verifier",
  "hidden_ingredients",
  "recipe_facets",
  "substitutions",
  "grocery_tidy",
  "shelf_life",
  "step_timers",
  "cook_command",
  "gram_estimate",
] as const;
const PANEL = ["typesafe/jev-1.14", "cloudflare/clef"];

type Settings = {
  keyConfigured: boolean;
  keyHint: string | null;
  cleanupModel: string;
  decisionAssistToleranceDv: string;
  decisionFeatures: { purpose: string; enabled: boolean; models: string[] }[];
  monthlyCapUsd: string;
  spentThisMonthUsd: string;
  version: number;
};

type Backend = {
  settings: Settings;
  puts: Record<string, unknown>[];
  labelRuns: number;
  labelSummary: Record<string, unknown>;
  failNextPutWith: number | null;
};

function freshBackend(overrides: Partial<Settings> = {}): Backend {
  return {
    settings: {
      keyConfigured: true,
      keyHint: "1234",
      cleanupModel: "",
      decisionAssistToleranceDv: "0.08",
      decisionFeatures: PURPOSES.map((purpose) => ({ purpose, enabled: true, models: PANEL })),
      monthlyCapUsd: "2",
      spentThisMonthUsd: "0.00042",
      version: 1,
      ...overrides,
    },
    puts: [],
    labelRuns: 0,
    labelSummary: { labelled: 120, total: 8000, active: 0, waiting: 0, pollAfterSeconds: null },
    failNextPutWith: null,
  };
}

async function mockApi(page: Page, backend: Backend) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (path === "/api/v1/owner/preferences") {
      return route.fulfill({ json: { displayName: "Koush", timezone: "UTC", weekStartsOn: 1, version: 1 } });
    }
    if (path === "/api/v1/nutrition-intelligence/settings") {
      return route.fulfill({
        json: {
          backend: "hashing",
          intelligenceEnabled: true,
          inlineEnabled: true,
          modelName: "BAAI/bge-small-en-v1.5",
          modelRevision: null,
          concurrency: 1,
          version: 1,
          runtimeStatus: "ready",
        },
      });
    }
    if (path === "/api/v1/recipe-import/settings") {
      return route.fulfill({
        json: { cleanupEnabled: true, openrouterFallbackEnabled: false, version: 1, openrouterConfigured: backend.settings.keyConfigured },
      });
    }
    if (path === "/api/v1/openrouter/settings" && method === "GET") return route.fulfill({ json: backend.settings });
    if (path === "/api/v1/openrouter/settings" && method === "PUT") {
      const body = request.postDataJSON() as Record<string, unknown>;
      backend.puts.push(body);
      if (backend.failNextPutWith) {
        const status = backend.failNextPutWith;
        backend.failNextPutWith = null;
        return route.fulfill({ status, json: { code: status === 409 ? "stale_version" : "invalid_value", title: status === 409 ? "This was changed elsewhere. Reload and try again." : "Invalid value" } });
      }
      const features = body.decisionFeatures as Settings["decisionFeatures"];
      backend.settings = {
        ...backend.settings,
        keyConfigured: body.clearApiKey ? false : Boolean(body.apiKey) || backend.settings.keyConfigured,
        keyHint: body.clearApiKey ? null : body.apiKey ? String(body.apiKey).slice(-4) : backend.settings.keyHint,
        monthlyCapUsd: String(body.monthlyCapUsd),
        decisionAssistToleranceDv: String(body.decisionAssistToleranceDv),
        decisionFeatures: features,
        version: backend.settings.version + 1,
      };
      return route.fulfill({ json: backend.settings });
    }
    if (path === "/api/v1/jobs/food-labels" && method === "GET") return route.fulfill({ json: backend.labelSummary });
    if (path === "/api/v1/jobs/food-labels" && method === "POST") {
      backend.labelRuns += 1;
      backend.labelSummary = { ...backend.labelSummary, active: 1, pollAfterSeconds: null };
      return route.fulfill({ status: 202, json: { jobId: "00000000-0000-4000-8000-000000000042", status: "queued" } });
    }
    return route.fulfill({ status: 404, json: { code: "not_found", title: "Not found" } });
  });
}

async function open(page: Page, backend: Backend) {
  await mockApi(page, backend);
  await page.goto("/app/settings?tab=intelligence");
  await expect(page.locator("legend", { hasText: "Decision features" })).toBeVisible();
}

const modelsBox = (page: Page, label: string) => page.getByLabel(`${label} models`);
const card = (page: Page) => page.getByRole("region", { name: "OpenRouter", exact: true });
const saveButton = (page: Page) => card(page).getByRole("button", { name: /^Save (key and )?settings$/ });
const status = (page: Page) => card(page).getByRole("status");

test("every decision feature is listed, on by default, with the default panel", async ({ page }) => {
  await open(page, freshBackend());
  const checkboxes = page.locator(".decision-feature input[type=checkbox]");
  await expect(checkboxes).toHaveCount(PURPOSES.length);
  for (let index = 0; index < PURPOSES.length; index += 1) await expect(checkboxes.nth(index)).toBeChecked();
  await expect(modelsBox(page, "Ingredient matching")).toHaveValue("typesafe/jev-1.14, cloudflare/clef");
  await expect(page.getByText(/\$0\.0004 spent this month/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("the Intelligence tab has no accessibility violations", async ({ page }) => {
  await open(page, freshBackend());
  // Let colour transitions settle so contrast is measured on the resting state.
  await page.waitForTimeout(1000);
  await page.addScriptTag({ content: axe.source });
  const result = await page.evaluate(async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const out = await (window as any).axe.run(document.querySelector("main") ?? document.body, { runOnly: ["wcag2a", "wcag2aa"] });
    return out.violations.map((v: { id: string; nodes: { target: string[]; failureSummary?: string }[] }) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ") + " " + (n.failureSummary ?? "").slice(0, 160)).join(" | ")}`);
  });
  expect(result).toEqual([]);
});

test("an enabled feature with no model, too many models, a repeat, or a malformed id blocks saving with a reason", async ({ page }) => {
  await open(page, freshBackend());
  const box = modelsBox(page, "Ingredient matching");
  const cases: [string, RegExp][] = [
    ["", /Add at least one model/],
    ["a/b, c/d, e/f, g/h", /at most 3/],
    ["a/b, a/b", /listed twice/],
    ["not a model", /provider\/model/],
    ["a/b;rm -rf", /provider\/model/],
    ["../../etc/passwd", /provider\/model/],
  ];
  for (const [value, message] of cases) {
    await box.fill(value);
    await expect(page.getByText(message)).toBeVisible();
    await expect(saveButton(page)).toBeDisabled();
  }
  await box.fill("a/b, c/d");
  await expect(saveButton(page)).toBeEnabled();
});

test("switching a feature off lets it keep an empty model list and saves it as off", async ({ page }) => {
  const backend = freshBackend();
  await open(page, backend);
  await modelsBox(page, "Shelf life").fill("");
  await expect(saveButton(page)).toBeDisabled();
  await page.getByRole("checkbox", { name: /Shelf life/ }).uncheck();
  await expect(saveButton(page)).toBeEnabled();
  await saveButton(page).click();
  await expect(status(page)).toContainText("saved");
  const sent = backend.puts[0]?.decisionFeatures as Settings["decisionFeatures"];
  expect(sent.find((f) => f.purpose === "shelf_life")).toEqual({ purpose: "shelf_life", enabled: false, models: [] });
});

test("an invalid spend cap or tolerance blocks saving", async ({ page }) => {
  await open(page, freshBackend());
  const cap = page.getByLabel("Monthly spend cap (USD)");
  for (const bad of ["", "-1", "abc", "100.01", "1e2x"]) {
    await cap.fill(bad);
    await expect(saveButton(page)).toBeDisabled();
  }
  await cap.fill("100");
  await expect(saveButton(page)).toBeEnabled();
  const tolerance = page.getByLabel(/Auto-resolve tolerance/);
  for (const bad of ["0", "-2", "10.5", "x"]) {
    await tolerance.fill(bad);
    await expect(saveButton(page)).toBeDisabled();
  }
  await tolerance.fill("10");
  await expect(saveButton(page)).toBeEnabled();
});

test("saving sends the whole form once, clears the key box, and never shows the key again", async ({ page }) => {
  const backend = freshBackend({ keyConfigured: false, keyHint: null });
  await open(page, backend);
  const secret = "sk-or-v1-topsecret-WXYZ";
  await page.getByLabel("API key").fill(secret);
  await page.getByLabel("Monthly spend cap (USD)").fill("5");
  await card(page).getByRole("button", { name: "Save key and settings" }).click();
  await expect(status(page)).toContainText("saved");
  expect(backend.puts).toHaveLength(1);
  expect(backend.puts[0]).toMatchObject({ apiKey: secret, monthlyCapUsd: "5.00", version: 1 });
  expect(Object.keys(backend.puts[0] ?? {})).not.toContain("clearApiKey_true");
  await expect(page.getByLabel("API key")).toHaveValue("");
  await expect(page.getByText(/ending in WXYZ/)).toBeVisible();
  expect(await page.content()).not.toContain(secret);
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain(secret);
});

test("a stale-version conflict is shown, keeps the owner's edits, and a retry can succeed", async ({ page }) => {
  const backend = freshBackend();
  await open(page, backend);
  await page.getByLabel("Monthly spend cap (USD)").fill("7");
  backend.failNextPutWith = 409;
  await saveButton(page).click();
  await expect(card(page).getByRole("alert")).toContainText(/changed elsewhere/);
  await expect(page.getByLabel("Monthly spend cap (USD)")).toHaveValue("7");
  await saveButton(page).click();
  await expect(status(page)).toContainText("saved");
});

test("a background refetch does not overwrite what the owner is typing", async ({ page }) => {
  const backend = freshBackend();
  await open(page, backend);
  await modelsBox(page, "Grocery tidy").fill("typed/by-hand");
  backend.settings = { ...backend.settings, spentThisMonthUsd: "0.9", monthlyCapUsd: "3" };
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    window.dispatchEvent(new Event("focus"));
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.getByText(/\$0\.90 spent this month/)).toBeVisible();
  await expect(modelsBox(page, "Grocery tidy")).toHaveValue("typed/by-hand");
});

test("removing the key sends only that request and is blocked while the form is invalid", async ({ page }) => {
  const backend = freshBackend();
  await open(page, backend);
  await page.getByLabel("Monthly spend cap (USD)").fill("nope");
  await expect(card(page).getByRole("button", { name: "Remove key" })).toBeDisabled();
  await page.getByLabel("Monthly spend cap (USD)").fill("2");
  await card(page).getByRole("button", { name: "Remove key" }).click();
  await expect(status(page)).toContainText("saved");
  expect(backend.puts[0]).toMatchObject({ clearApiKey: true });
  expect(backend.puts[0]).not.toHaveProperty("apiKey");
  await expect(page.getByText("No key saved.")).toBeVisible();
  await expect(card(page).getByRole("button", { name: "Remove key" })).toHaveCount(0);
});

test("features can be toggled and edited from the keyboard alone", async ({ page }) => {
  const backend = freshBackend();
  await open(page, backend);
  const first = page.locator(".decision-feature input[type=checkbox]").first();
  await first.focus();
  await page.keyboard.press("Space");
  await expect(first).not.toBeChecked();
  await expect(modelsBox(page, "Ingredient matching")).toBeDisabled();
  await page.keyboard.press("Space");
  await expect(first).toBeChecked();
  await page.keyboard.press("Tab");
  await expect(modelsBox(page, "Ingredient matching")).toBeFocused();
});

test("food labelling: coverage, starting a run, busy state, and the disabled reasons", async ({ page }) => {
  const backend = freshBackend();
  await open(page, backend);
  await expect(page.getByText(/120 of 8,000 USDA foods labelled \(2%\)/)).toBeVisible();
  const run = page.getByRole("button", { name: "Label foods now" });
  await expect(run).toBeEnabled();
  await run.click();
  await expect.poll(() => backend.labelRuns).toBe(1);
  await expect(page.getByRole("button", { name: "Labelling…" })).toBeDisabled();
  await expect(page.getByText(/Labelling now/)).toBeVisible();
});

test("food labelling is disabled without a key, with the feature off, or with no USDA data", async ({ page }) => {
  const noKey = freshBackend({ keyConfigured: false, keyHint: null });
  await open(page, noKey);
  await expect(page.getByRole("button", { name: "Label foods now" })).toBeDisabled();
  await page.unrouteAll();

  const noData = freshBackend();
  noData.labelSummary = { labelled: 0, total: 0, active: 0, waiting: 0, pollAfterSeconds: null };
  await open(page, noData);
  await expect(page.getByText("Install USDA reference data first.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Label foods now" })).toBeDisabled();
});

test("a failed label coverage request says so without breaking the rest of the card", async ({ page }) => {
  const backend = freshBackend();
  await mockApi(page, backend);
  await page.route("**/api/v1/jobs/food-labels", (route) => route.fulfill({ status: 500, json: { code: "boom", title: "Boom" } }));
  await page.goto("/app/settings?tab=intelligence");
  await expect(page.getByText("Label coverage could not be loaded.")).toBeVisible();
  await expect(page.locator("legend", { hasText: "Decision features" })).toBeVisible();
  await expect(saveButton(page)).toBeEnabled();
});

test("a settings request that fails offers a retry and does not show a half-built form", async ({ page }) => {
  const backend = freshBackend();
  await mockApi(page, backend);
  let fail = true;
  await page.route("**/api/v1/openrouter/settings", (route) => {
    if (route.request().method() === "GET" && fail) return route.fulfill({ status: 500, json: { code: "boom", title: "Boom" } });
    return route.fallback();
  });
  await page.goto("/app/settings?tab=intelligence");
  await expect(page.getByText("OpenRouter settings could not be loaded")).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator("legend", { hasText: "Decision features" })).toBeVisible();
});
