import { expect, type Page, test } from "@playwright/test";
import { captureUi } from "./support/visual-audit";

const recipeId = "00000000-0000-4000-8000-000000000001";
const goalId = "00000000-0000-4000-8000-000000000010";
const planId = "00000000-0000-4000-8000-000000000020";

async function mockPlanningApi(page: Page) {
  await page.clock.install({ time: new Date("2026-03-11T18:00:00Z") });
  let preferences = { timezone: "America/Vancouver", weekStartsOn: 1, version: 1 };
  let goal: Record<string, unknown> | null = null;
  let entries: Array<Record<string, unknown>> = [];
  let planVersion = 1;
  await page.context().addCookies([{ name: "cookfully_csrf", value: "plan-e2e-csrf", domain: "127.0.0.1", path: "/" }]);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const fulfill = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/owner/preferences") {
      if (method === "PUT") preferences = { ...request.postDataJSON(), version: preferences.version + 1 };
      return fulfill(preferences);
    }
    if (path === "/api/v1/goals/current") {
      if (method === "GET") return goal ? fulfill(goal) : fulfill({ code: "goal_not_found", title: "No goal" }, 404);
      goal = { id: goalId, ...request.postDataJSON(), macroCalorieDifference: "-15", version: 1 };
      return fulfill(goal);
    }
    if (path === "/api/v1/recipes") return fulfill({ items: [{ id: recipeId, title: "Protein oats", yieldQuantity: "2", yieldUnit: "servings", status: "ready", nutritionState: "estimated", version: 1 }], nextCursor: null });
    if (path.startsWith("/api/v1/meal-plans/") && path.endsWith("/entries") && method === "POST") {
      const value = request.postDataJSON();
      const item = {
        id: `00000000-0000-4000-8000-${String(entries.length + 30).padStart(12, "0")}`,
        ...value,
        recipeTitle: "Protein oats",
        nutrition: { basisServings: value.servings, caloriesKcal: value.servings === "2.000" ? "1003" : "502", proteinG: value.servings === "2.000" ? "80.1" : "40.1", carbohydrateG: value.servings === "2.000" ? "120.1" : "60.1", fatG: value.servings === "2.000" ? "22.3" : "11.2", status: "estimated", coverageRatio: "0.950000" },
        origin: "manual",
        version: 1,
      };
      entries.push(item);
      planVersion += 1;
      return fulfill(item, 201);
    }
    if (path.match(/\/api\/v1\/meal-plan-entries\/[^/]+\/swap$/) && method === "POST") {
      const sourceId = path.split("/").at(-2);
      const { targetEntryId } = request.postDataJSON() as { targetEntryId: string };
      const sourceIndex = entries.findIndex((item) => item.id === sourceId);
      const targetIndex = entries.findIndex((item) => item.id === targetEntryId);
      const source = entries[sourceIndex];
      const target = entries[targetIndex];
      entries[sourceIndex] = { ...source, localDate: target.localDate, mealSlot: target.mealSlot, position: target.position, version: Number(source.version) + 1 };
      entries[targetIndex] = { ...target, localDate: source.localDate, mealSlot: source.mealSlot, position: source.position, version: Number(target.version) + 1 };
      planVersion += 1;
      return fulfill({ source: entries[sourceIndex], target: entries[targetIndex] });
    }
    if (path.startsWith("/api/v1/meal-plan-entries/") && method === "PATCH") {
      const id = path.split("/").at(-1);
      const value = request.postDataJSON();
      const index = entries.findIndex((item) => item.id === id);
      entries[index] = { ...entries[index], ...value, version: Number(entries[index].version) + 1, nutrition: { ...(entries[index].nutrition as object), basisServings: value.servings, caloriesKcal: value.servings === "2.000" ? "1003" : "502" } };
      planVersion += 1;
      return fulfill(entries[index]);
    }
    if (path.startsWith("/api/v1/meal-plan-entries/") && method === "DELETE") {
      const id = path.split("/").at(-1);
      entries = entries.filter((item) => item.id !== id);
      planVersion += 1;
      return route.fulfill({ status: 204 });
    }
    if (path.startsWith("/api/v1/meal-plans/") && method === "GET") {
      if (!entries.length) return fulfill({ code: "meal_plan_not_found", title: "No plan" }, 404);
      const days = Object.fromEntries([...new Set(entries.map((item) => String(item.localDate)))].map((day) => [day, { caloriesKcal: "502", proteinG: "40.1", carbohydrateG: "60.1", fatG: "11.2", status: "estimated", coverageRatio: "0.950000", targetDifference: { caloriesKcal: "-1698", proteinG: "-139.9", carbohydrateG: "-159.9", fatG: "-53.8" } }]));
      return fulfill({ id: planId, weekStart: "2026-03-09", timezone: preferences.timezone, goal, entries, dayTotals: days, weekTotal: { caloriesKcal: String(entries.length * 502), proteinG: `${(entries.length * 40.1).toFixed(1)}`, carbohydrateG: `${(entries.length * 60.1).toFixed(1)}`, fatG: `${(entries.length * 11.2).toFixed(1)}`, status: "estimated", coverageRatio: "0.950000" }, groceryStatus: "absent", version: planVersion });
    }
    if (path === "/api/v1/owner/preferences" || path === "/api/v1/auth/session") return fulfill(preferences);
    return fulfill({ code: "not_found", title: "Not found" }, 404);
  });
}

test("starts food-first planning before a nutrition guide exists", async ({ page }, testInfo) => {
  await mockPlanningApi(page);
  await page.goto("/app/plan");

  await expect(page.getByRole("heading", { name: /week of march 9/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Plan the food now. Add your guide when you’re ready." })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Add nutrition guide" })).toHaveCount(1);
  await captureUi(page, testInfo, "planner-week-empty");

  await page.getByRole("tab", { name: "Day" }).click();
  await expect(page.getByRole("link", { name: "Guide my ideas" })).toHaveCount(0);
  await expect(page.locator(".plan-nutrition")).toHaveCount(0);
  await captureUi(page, testInfo, "planner-day-top");
  await page.getByRole("button", { name: "Add a recipe to Dinner" }).click();
  await page.getByRole("button", { name: "Add Protein oats to Dinner" }).click();

  await expect(page.getByRole("heading", { name: "Protein oats" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Add nutrition guide" })).toHaveCount(1);
  await expect(page.getByText("Meal added to your plan.")).toBeVisible();
  await captureUi(page, testInfo, "planner-day", { focus: page.getByRole("heading", { name: "Protein oats" }) });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("reflows the mobile week into a readable vertical agenda", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "narrow-mobile", "The vertical agenda assertion is mobile-only.");
  await mockPlanningApi(page);
  await page.goto("/app/plan");

  const board = page.locator(".week-board");
  await expect(board).toBeVisible();
  const layout = await board.evaluate((element) => {
    const days = Array.from(element.querySelectorAll<HTMLElement>(".week-day")).slice(0, 2).map((day) => day.getBoundingClientRect());
    const style = getComputedStyle(element);
    return {
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      overflowX: style.overflowX,
      firstDayWidth: days[0]?.width ?? 0,
      firstDayHeight: days[0]?.height ?? 0,
      stacked: days.length === 2 && days[1].y > days[0].bottom,
    };
  });
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth);
  expect(layout.overflowX).toBe("visible");
  expect(layout.firstDayWidth).toBeGreaterThan(340);
  expect(layout.firstDayHeight).toBeLessThan(100);
  expect(layout.stacked).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("keeps dates before today visible but read-only", async ({ page }) => {
  await mockPlanningApi(page);
  await page.goto("/app/plan");

  await expect(page.locator(".week-day--past")).toHaveCount(2);
  await page.getByRole("tab", { name: "Day" }).click();
  await page.getByRole("tab", { name: /monday.*march 9.*past/i }).click();
  await expect(page.getByText("Past day", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add a recipe to Breakfast" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add a recipe to Lunch" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add a recipe to Dinner" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add a recipe to Snack" })).toHaveCount(0);
});

test("moves a meal with the whole card drag surface", async ({ page }) => {
  await mockPlanningApi(page);
  await page.goto("/app/plan");

  await page.getByRole("tab", { name: "Day" }).click();
  await page.getByRole("button", { name: "Add a recipe to Dinner" }).click();
  await page.getByRole("button", { name: "Add Protein oats to Dinner" }).click();
  await expect(page.getByRole("heading", { name: "Protein oats" })).toBeVisible();

  await page.getByRole("tab", { name: "Week" }).click();
  const meal = page.locator(".week-meal").first();
  const destination = page.locator('.week-slot[aria-label="Breakfast on Wednesday"]');
  const moveRequest = page.waitForRequest((request) => request.method() === "PATCH" && request.url().includes("/meal-plan-entries/"));
  // The mobile week board is horizontally scrollable; bring the source day
  // into the viewport before sending a touch gesture.
  await meal.scrollIntoViewIfNeeded();
  const sourceBox = await meal.boundingBox();
  expect(sourceBox).not.toBeNull();
  const sourcePoint = { x: sourceBox!.x + sourceBox!.width / 2, y: sourceBox!.y + sourceBox!.height / 2 };
  const touchEnvironment = await page.evaluate(() => navigator.maxTouchPoints > 0);
  const touchClient = touchEnvironment ? await page.context().newCDPSession(page) : null;
  if (touchEnvironment) {
    await touchClient!.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: sourcePoint.x, y: sourcePoint.y, id: 1 }], modifiers: 0 });
  } else {
    await page.mouse.move(sourcePoint.x, sourcePoint.y);
    await page.mouse.down();
  }
  // The touch pointer sensor intentionally waits 250ms before activating so
  // a scroll gesture is not mistaken for a drag.
  await page.waitForTimeout(350);
  await expect(page.locator(".week-overview--dragging")).toBeVisible();
  await destination.scrollIntoViewIfNeeded();
  const destinationBox = await destination.boundingBox();
  expect(destinationBox).not.toBeNull();
  const destinationPoint = { x: destinationBox!.x + destinationBox!.width / 2, y: destinationBox!.y + destinationBox!.height / 2 };
  if (touchEnvironment) {
    await touchClient!.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: destinationPoint.x, y: destinationPoint.y, id: 1 }], modifiers: 0 });
  } else {
    await page.mouse.move(destinationPoint.x, destinationPoint.y, { steps: 12 });
  }
  await page.waitForTimeout(250);
  if (touchEnvironment) {
    await touchClient!.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [], modifiers: 0 });
  } else {
    await page.mouse.up();
  }
  await moveRequest;
  await expect(destination).toContainText("Protein oats");
});

test("only stages an occupied-slot swap after the card is released", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "The touch release path is covered by the mobile drag test.");
  await mockPlanningApi(page);
  await page.goto("/app/plan");

  await page.getByRole("tab", { name: "Day" }).click();
  await page.getByRole("button", { name: "Add a recipe to Dinner" }).click();
  await page.getByRole("button", { name: "Add Protein oats to Dinner" }).click();
  await page.getByRole("button", { name: "Add a recipe to Lunch" }).click();
  await page.getByRole("button", { name: "Add Protein oats to Lunch" }).click();
  await page.getByRole("tab", { name: "Week" }).click();

  const meals = page.locator(".week-meal");
  await expect(meals).toHaveCount(2);
  const source = meals.nth(0);
  const target = meals.nth(1);
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  expect(sourceBox).not.toBeNull();
  expect(targetBox).not.toBeNull();
  let swapRequests = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/swap")) swapRequests += 1;
  });

  await page.mouse.move(sourceBox!.x + sourceBox!.width / 2, sourceBox!.y + sourceBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(targetBox!.x + targetBox!.width / 2, targetBox!.y + targetBox!.height / 2, { steps: 12 });
  await page.waitForTimeout(150);
  expect(swapRequests).toBe(0);
  await expect(page.getByRole("alert").filter({ hasText: "Swap these meals?" })).toHaveCount(0);
  await page.mouse.up();

  await expect(page.getByRole("alert").filter({ hasText: "Swap these meals?" })).toBeVisible();
  expect(swapRequests).toBe(0);
  const swapRequest = page.waitForRequest((request) => request.method() === "POST" && request.url().includes("/swap"));
  await page.getByRole("button", { name: "Swap meals" }).click();
  await swapRequest;
  await expect(page.getByText("Protein oats swapped places.")).toBeVisible();
});

test("creates a goal, fills the remaining days, adjusts, copies, moves, and refreshes snapshots", async ({ page }, testInfo) => {
  await mockPlanningApi(page);
  await page.goto("/app/goals");
  await expect(page.getByRole("heading", { name: "Shape how Cookfully plans for you" })).toBeVisible();
  await captureUi(page, testInfo, "goals-new");
  await page.getByText("Energy baseline and dates", { exact: true }).click();
  await page.getByLabel("Maintenance calories").fill("2500.000000");
  await page.getByLabel("Daily calories").fill("2200.000000");
  await page.getByLabel("Daily protein").fill("180.000000");
  await page.getByLabel("Daily carbohydrate").fill("220.000000");
  await page.getByLabel("Daily fat").fill("65.000000");
  await page.getByLabel("Effective from").fill("2026-03-01");
  await page.getByRole("button", { name: "Save my guide" }).click();
  await expect(page.getByText("Your planning guide is saved.")).toBeVisible();
  await expect(page.locator('.goal-saved-status [data-companion-moment="success"]')).toBeVisible();
  await expect(page.getByLabel("Current daily nutrition guide")).toContainText("2,200 kcal");
  await expect(page.getByRole("button", { name: "Adjust daily guide" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save my guide" })).toHaveCount(0);
  await captureUi(page, testInfo, "goals-saved", { focus: page.getByLabel("Current daily nutrition guide") });

  await page.getByRole("main").getByRole("link", { name: "Back to meal plan" }).click();
  await expect(page.getByRole("heading", { name: /week of march 9/i })).toBeVisible();
  await page.getByRole("tab", { name: "Day" }).click();
  const dayTabs = page.getByRole("tablist", { name: "Days in planning week" }).getByRole("tab");
  await expect(dayTabs).toHaveCount(7);
  for (let index = 2; index < 7; index += 1) {
    await dayTabs.nth(index).click();
    await page.getByRole("button", { name: "Add a recipe to Breakfast" }).click();
    await page.getByRole("button", { name: "Add Protein oats to Breakfast" }).click();
    await expect(page.getByRole("heading", { name: "Protein oats" })).toBeVisible();
  }

  await dayTabs.nth(2).click();
  const plannedEntry = page.getByRole("article").filter({ has: page.getByRole("heading", { name: "Protein oats" }) });
  const ensureAdjustmentsOpen = async () => {
    const disclosure = plannedEntry.locator("details.plan-entry__adjust");
    if (!(await disclosure.evaluate((element) => (element as HTMLDetailsElement).open))) await plannedEntry.getByText("Adjust meal", { exact: true }).click();
  };
  await ensureAdjustmentsOpen();
  await plannedEntry.getByLabel("Protein oats servings").fill("2.000");
  await plannedEntry.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("1,003 kcal")).toBeVisible();
  await plannedEntry.getByRole("button", { name: "Copy to next day" }).click();
  await ensureAdjustmentsOpen();
  await plannedEntry.getByLabel("Protein oats meal slot").selectOption("lunch");
  await plannedEntry.getByRole("button", { name: "Save changes" }).click();
  const lunchSlot = page.locator("section.meal-slot").filter({ has: page.getByRole("heading", { name: "Lunch" }) });
  const movedEntry = lunchSlot.getByRole("article").filter({ has: page.getByRole("heading", { name: "Protein oats" }) });
  await expect(movedEntry).toBeVisible();
  await movedEntry.getByText("Adjust meal", { exact: true }).click();
  await expect(movedEntry.getByRole("button", { name: "Refresh nutrition" })).toBeVisible();
  await movedEntry.getByRole("button", { name: "Refresh nutrition" }).click();
  await expect(page.getByText(/snapshot refreshed/i)).toBeVisible();

  await page.getByRole("tab", { name: "Week" }).click();
  await expect(page.getByRole("heading", { name: "Your week at a glance" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Weekly nutrition guidance" })).toBeVisible();
  const overflowingMeals = await page.locator(".week-meal").evaluateAll((meals) => meals.filter((meal) => meal.scrollWidth > meal.clientWidth + 1 || meal.scrollHeight > meal.clientHeight + 1).length);
  expect(overflowingMeals).toBe(0);
  await captureUi(page, testInfo, "planner-week-guided");
  await page.getByRole("tab", { name: "Prep" }).click();
  await expect(page.getByRole("heading", { name: "Cook 1 dish for 6 meals" })).toBeVisible();
  await expect(page.getByText("8 total servings")).toBeVisible();
  await captureUi(page, testInfo, "planner-prep");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
