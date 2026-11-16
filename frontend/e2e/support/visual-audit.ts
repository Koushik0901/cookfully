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
  // Entrance motion can restart after a re-render; the app's reduced-motion
  // contract collapses it so every capture shows the settled layout.
  await page.emulateMedia({ reducedMotion: "reduce" });
  // The app uses smooth scrolling; captures need instant, settled offsets.
  await page.evaluate(() => { document.documentElement.style.scrollBehavior = "auto"; });
  const scrollIntoPlace = async () => {
    if (options.focus) {
      await options.focus.scrollIntoViewIfNeeded();
      await page.evaluate(() => window.scrollTo({ left: 0, top: Math.max(0, window.scrollY - 72), behavior: "instant" }));
    } else {
      await page.evaluate(() => window.scrollTo({ left: 0, top: 0, behavior: "instant" }));
    }
  };
  await scrollIntoPlace();
  await page.evaluate(async () => {
    await Promise.all(
      Array.from(document.images).map(async (image) => {
        if (!image.complete) {
          await new Promise<void>((resolve) => {
            image.addEventListener("load", () => resolve(), { once: true });
            image.addEventListener("error", () => resolve(), { once: true });
            // A stalled request must not hang the capture until the test times out.
            setTimeout(resolve, 5000);
          });
        }
        if (image.naturalWidth) await image.decode().catch(() => undefined);
      }),
    );
  });
  // The variable display font settles after images; capture only once it has.
  await page.evaluate(async () => {
    await document.fonts.ready;
    // Jump finite entrance motion (e.g. page-arrive) to its end so layout is final.
    for (const animation of document.getAnimations()) {
      if (animation.effect?.getComputedTiming().iterations === Infinity) continue;
      try { animation.finish(); } catch { /* not finishable; leave it */ }
    }
  });
  // Wait until the main content stops moving (late layout, settling motion).
  await page.evaluate(async () => {
    const probe = () => {
      const target = document.querySelector("main h1, main, h1");
      const box = target?.getBoundingClientRect();
      return box ? `${box.top}:${box.left}:${box.height}` : "";
    };
    let previous = probe();
    for (let stable = 0, tries = 0; stable < 3 && tries < 40; tries += 1) {
      await new Promise((resolve) => setTimeout(resolve, 50));
      const next = probe();
      stable = next === previous ? stable + 1 : 0;
      previous = next;
    }
  });
  // A pointer left over a control from an earlier step paints its hover state.
  await page.mouse.move(-10, -10);
  // Pages may scroll themselves while settling (e.g. focusing a field); restore the offset.
  await scrollIntoPlace();
  const intendedScrollY = await page.evaluate(() => window.scrollY);
  await page.waitForTimeout(200);
  expect(await page.evaluate(() => window.scrollY), "capture scroll offset moved before the screenshot").toBe(intendedScrollY);
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
