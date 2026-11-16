import { defineConfig, devices } from "@playwright/test";

// Grayscale, unhinted text renders the same whether or not a layer is
// GPU-composited, so screenshot baselines don't flip between two text renderings.
const stableChromiumText = { launchOptions: { args: ["--disable-lcd-text", "--font-render-hinting=none"] } };

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  // One Vite dev server serves every worker; cap CI so a larger runner cannot
  // overload it into timeouts.
  workers: process.env.CI ? 2 : undefined,
  reporter: [["list"], ["html", { open: "never" }]],
  // Baselines are per platform: font rendering differs between Windows dev
  // machines and Linux CI, so each keeps its own set.
  snapshotPathTemplate: "{testDir}/__screenshots__/{testFilePath}/{arg}-{projectName}-{platform}{ext}",
  use: {
    baseURL: "http://127.0.0.1:5173",
    // The browser timezone shows up in the UI (e.g. Settings' timezone hint);
    // pin it so screenshots don't depend on the machine running the suite.
    timezoneId: "UTC",
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
    command: "pnpm dev --host 127.0.0.1",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
  },
});
