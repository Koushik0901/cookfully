import { expect, type Locator, type Page, type TestInfo } from "@playwright/test";

type CaptureOptions = {
  focus?: Locator;
};

export async function captureUi(
  page: Page,
  testInfo: TestInfo,
  name: string,
  options: CaptureOptions = {},
) {
  if (testInfo.project.name === "desktop-chromium") {
    await page.setViewportSize({ width: 1440, height: 900 });
  }
  if (options.focus) {
    await options.focus.scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollTo({ left: 0, top: Math.max(0, window.scrollY - 72) }));
  } else {
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  await page.evaluate(async () => {
    await Promise.all(
      Array.from(document.images).map(async (image) => {
        if (!image.complete) {
          await new Promise<void>((resolve) => {
            image.addEventListener("load", () => resolve(), { once: true });
            image.addEventListener("error", () => resolve(), { once: true });
          });
        }
        if (image.naturalWidth) await image.decode().catch(() => undefined);
      }),
    );
  });
  await page.waitForTimeout(200);
  await expect(page).toHaveScreenshot(`${name}.png`, {
    animations: "disabled",
    caret: "hide",
    scale: "css",
    maxDiffPixelRatio: 0,
    fullPage: false,
  });

  const directory = process.env.CAPTURE_DIR;
  if (directory) await page.screenshot({
    path: `${directory}/${testInfo.project.name}-${name}.png`,
    fullPage: false,
    animations: "disabled",
    caret: "hide",
    scale: "css",
  });
}
