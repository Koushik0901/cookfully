import { expect, test } from "@playwright/test";

async function mockNativeSelectSettings(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA", weekStartsOn: 1, version: 1 });
    if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
    if (path === "/api/v1/nutrition-intelligence/settings") {
      return json({
        backend: "hashing",
        modelName: "BAAI/bge-small-en-v1.5",
        modelRevision: null,
        concurrency: 1,
        version: 1,
        runtimeStatus: "configured",
        downloadJobId: null,
        downloadJobStatus: null,
        downloadProgressCurrent: null,
        downloadProgressTotal: null,
        downloadFailureMessage: null,
      });
    }
    if (path === "/api/v1/nutrition-intelligence/estimate") {
      return json({
        backend: "hashing",
        modelName: "BAAI/bge-small-en-v1.5",
        modelRevision: null,
        concurrency: 1,
        activeFoodCount: 0,
        downloadBytes: 0,
        diskBytes: 0,
        modelMemoryBytes: 0,
        perJobMemoryBytes: 0,
        totalMemoryBytes: 0,
        requiredCpuCores: 1,
        availableCpuCores: 4,
        availableMemoryBytes: 8_000_000_000,
        availableDiskBytes: 8_000_000_000,
        memoryHeadroomBytes: 8_000_000_000,
        status: "safe",
        warnings: [],
        estimateHash: "native-select-estimate",
      });
    }
    return json({ code: "not_found", title: "Not found", status: 404 }, 404);
  });
}

test("WebKit preserves Cookfully's native select contract", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "webkit-native-select", "Native select compatibility is exercised in WebKit.");
  await mockNativeSelectSettings(page);
  await page.goto("/app/settings");
  await page.getByRole("tab", { name: "Intelligence" }).click();

  const backend = page.getByLabel("Matching backend");
  await expect(backend).toHaveAttribute("data-slot", "select");
  await expect(backend).toHaveJSProperty("tagName", "SELECT");
  await expect(backend).toHaveValue("hashing");

  const geometry = await backend.evaluate((element) => {
    const select = element as HTMLSelectElement;
    const shell = select.closest<HTMLElement>(".cf-select-shell");
    const chevron = shell?.querySelector<HTMLElement>(".cf-select__chevron");
    return {
      height: select.getBoundingClientRect().height,
      shellWidth: shell?.getBoundingClientRect().width ?? 0,
      selectWidth: select.getBoundingClientRect().width,
      chevronPointerEvents: chevron ? getComputedStyle(chevron).pointerEvents : null,
    };
  });
  expect(geometry.height).toBeGreaterThanOrEqual(44);
  expect(geometry.shellWidth).toBeGreaterThanOrEqual(geometry.selectWidth);
  expect(geometry.chevronPointerEvents).toBe("none");

  await backend.selectOption("fastembed");
  await expect(backend).toHaveValue("fastembed");
  await expect(page.getByLabel("Hugging Face model name")).toBeEnabled();
});
