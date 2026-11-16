import { defineConfig, devices } from "@playwright/test";

const isCI = Boolean(process.env.CI);

// Grayscale, unhinted text renders the same whether or not a layer is GPU-composited, so
// screenshot baselines do not flip between two text renderings.
const stableChromiumText = { launchOptions: { args: ["--disable-lcd-text", "--font-render-hinting=none"] } };

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  // One dev/preview server backs every worker; more than two starves it on a CI runner.
  workers: isCI ? 2 : undefined,
  reporter: isCI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  // Font rasterisation differs per operating system, so every platform owns its baselines
  // (`-linux` for CI, `-win32` and `-darwin` for developer machines).
  snapshotPathTemplate:
    "{testDir}/__screenshots__/{testFilePath}/{arg}-{projectName}-{platform}{ext}",
  // CI sets this when no baselines exist for its platform yet, so the behavioural checks still
  // gate changes while the visual ones are bootstrapped. See e2e/README.md.
  ignoreSnapshots: process.env.PLAYWRIGHT_IGNORE_SNAPSHOTS === "1",
  use: {
    baseURL: "http://127.0.0.1:5173",
    // Dates and times render the same on every machine.
    timezoneId: "UTC",
    // CI serves the production bundle, which registers a service worker. Requests that go
    // through one bypass `page.route()` mocks in WebKit, so these tests would hit the real
    // network. The offline/PWA behaviour is covered by unit tests, not by these specs.
    serviceWorkers: "block",
    trace: "on-first-retry",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"], ...stableChromiumText } },
    {
      name: "narrow-mobile",
      use: {
        ...devices["Desktop Chrome"],
        ...stableChromiumText,
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 3,
        hasTouch: true,
        isMobile: true,
      },
    },
    {
      name: "webkit-native-select",
      testMatch: "**/native-select.spec.ts",
      use: { ...devices["Desktop Safari"] },
    },
  ],
  webServer: {
    // CI tests the production bundle that the build step just produced; locally the dev server
    // gives hot reload.
    command: isCI
      ? "pnpm exec vite preview --host 127.0.0.1 --port 5173 --strictPort"
      : "pnpm dev --host 127.0.0.1",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !isCI,
  },
});
