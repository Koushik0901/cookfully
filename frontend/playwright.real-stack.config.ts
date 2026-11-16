import { defineConfig, devices } from "@playwright/test";

/**
 * Tests that run against the real, composed application: nginx edge, API, workers, PostgreSQL and
 * Redis. Nothing is mocked, so these catch what the mocked suite cannot, such as the frontend and
 * the backend disagreeing about an endpoint.
 *
 *   E2E_BASE_URL         the web edge (default http://localhost:8080)
 *   E2E_OWNER_EMAIL      the bootstrapped owner (default owner@example.com)
 *   E2E_OWNER_PASSWORD   the owner's bootstrap password (required)
 *
 * CI starts the stack with deploy/compose.ci.yaml; see docs/ci.md.
 */
const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e/real-stack",
  fullyParallel: false,
  workers: 1, // one owner account and one database: tests take turns
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  timeout: 90_000,
  globalTimeout: isCI ? 8 * 60 * 1000 : undefined,
  reporter: isCI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    timezoneId: "UTC",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "real-stack", use: { ...devices["Desktop Chrome"] } }],
});
