import { expect, test, type Page } from "@playwright/test";

import { accessibleRecipe, accessibleRecipeId } from "./support/mock-accessible-recipe";

const steps = [
  "Marinate the chicken in the fridge for at least 30 minutes.",
  "Brown the chicken, then simmer 20-25 minutes.",
  "Serve over rice.",
];

type Command = { intent: string; probability: string | null; minutes: number | null; act: boolean; alternatives: { intent: string; probability: string }[] };

async function mockCook(page: Page, command: (utterance: string) => Command | "fail", { keyConfigured = true }: { keyConfigured?: boolean } = {}) {
  const base = accessibleRecipe();
  const recipe = {
    ...base,
    title: "Braised chicken",
    status: "ready",
    archivedFromStatus: null,
    activeJob: null,
    instructions: steps.map((text, position) => ({ position, text })),
  };
  const sent: string[] = [];
  await page.addInitScript(() => window.sessionStorage.clear());
  await page.context().addCookies([{ name: "cookfully_csrf", value: "e2e-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA" });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/openrouter/settings") {
      return json({ keyConfigured, decisionFeatures: [{ purpose: "cook_command", enabled: true, models: ["model/a"] }] });
    }
    if (path === `/api/v1/recipes/${accessibleRecipeId}`) return json(recipe);
    if (path === `/api/v1/recipes/${accessibleRecipeId}/step-timers`) {
      return json({ timers: [{ step: 0, minutes: 30, longestMinutes: 30, text: "30 minutes", passive: true }, { step: 1, minutes: 20, longestMinutes: 25, text: "20-25 minutes", passive: false }] });
    }
    if (path === `/api/v1/recipes/${accessibleRecipeId}/cook-command`) {
      const utterance = String(route.request().postDataJSON().utterance);
      sent.push(utterance);
      const result = command(utterance);
      return result === "fail" ? json({ code: "boom", status: 500, title: "Boom" }, 500) : json(result);
    }
    return json({ code: "not_found", status: 404, title: "Not found" }, 404);
  });
  return sent;
}

const none: Command = { intent: "none", probability: "0.9", minutes: null, act: false, alternatives: [] };

test("each step offers the timer it describes, and a tap starts it", async ({ page }) => {
  await mockCook(page, () => none);
  await page.goto(`/app/recipes/${accessibleRecipeId}/cook`);
  const timer = page.getByRole("button", { name: /Start 30 min timer · hands-free/ });
  await expect(timer).toBeVisible();
  await timer.click();
  await expect(page.getByRole("status", { name: "Timer 30 min" })).toContainText("Timer set for 30 min");
  await page.getByRole("button", { name: "Next step" }).click();
  await expect(page.getByRole("button", { name: /Start 20 min timer \(up to 25\)/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Start 30 min timer/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Next step" }).click();
  await expect(page.getByRole("button", { name: /Start \d+ min timer \(|hands-free/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Start 15 min timer" })).toBeVisible();
});

test("a typed command moves through the recipe, and voice never finishes it", async ({ page }) => {
  const sent = await mockCook(page, (u) => (u.includes("done") ? { ...none, intent: "next", act: true, probability: "0.9", alternatives: [] } : none));
  await page.goto(`/app/recipes/${accessibleRecipeId}/cook`);
  const counter = page.locator(".cook-mode__stage-heading .eyebrow");
  const box = page.getByLabel("Say or type a command");
  await box.fill("all done here");
  await page.getByRole("button", { name: "Go" }).click();
  await expect(counter).toHaveText("Step 2 of 3");
  await box.fill("done");
  await page.getByRole("button", { name: "Go" }).click();
  await expect(counter).toHaveText("Step 3 of 3");
  await box.fill("done again");
  await page.getByRole("button", { name: "Go" }).click();
  await expect(page.getByText(/That is the last step/)).toBeVisible();
  await expect(counter).toHaveText("Step 3 of 3");
  expect(sent).toEqual(["all done here", "done", "done again"]);
});

test("an unsure answer asks which was meant; nonsense and failures explain themselves", async ({ page }) => {
  await mockCook(page, (u) => {
    if (u === "boom") return "fail";
    if (u === "hmm what now") return { intent: "next", probability: "0.45", minutes: null, act: false, alternatives: [{ intent: "next", probability: "0.45" }, { intent: "repeat", probability: "0.4" }] };
    return none;
  });
  await page.goto(`/app/recipes/${accessibleRecipeId}/cook`);
  const box = page.getByLabel("Say or type a command");
  await box.fill("hmm what now");
  await page.getByRole("button", { name: "Go" }).click();
  await expect(page.getByText("Did you mean:")).toBeVisible();
  await page.getByRole("button", { name: "Read this step again" }).click();
  await expect(page.getByText("Step 1: Marinate the chicken")).toBeVisible();
  await box.fill("the dog is barking");
  await page.getByRole("button", { name: "Go" }).click();
  await expect(page.getByText(/didn’t catch a command/)).toBeVisible();
  await box.fill("boom");
  await page.getByRole("button", { name: "Go" }).click();
  await expect(page.getByText(/unavailable right now/)).toBeVisible();
  await page.getByRole("button", { name: "Next step" }).click();
  await expect(page.locator(".cook-mode__stage-heading .eyebrow")).toHaveText("Step 2 of 3");
});

test("with no key the command box is not offered and the buttons are the whole interface", async ({ page }) => {
  await mockCook(page, () => none, { keyConfigured: false });
  await page.goto(`/app/recipes/${accessibleRecipeId}/cook`);
  await expect(page.getByRole("button", { name: "Next step" })).toBeVisible();
  await expect(page.getByLabel("Say or type a command")).toHaveCount(0);
});

test("the command box fits the viewport without horizontal overflow", async ({ page }) => {
  await mockCook(page, () => none);
  await page.goto(`/app/recipes/${accessibleRecipeId}/cook`);
  await expect(page.getByLabel("Say or type a command")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
