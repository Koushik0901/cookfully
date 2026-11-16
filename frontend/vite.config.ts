import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import svgr from "vite-plugin-svgr";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [svgr(), react(), tailwindcss()],
  resolve: {
    alias: {
      "@": new URL("./src", import.meta.url).pathname,
    },
  },
  server: {
    port: 5173,
    allowedHosts: ["127.0.0.1", "localhost", "host.docker.internal"],
    proxy: {
      "/api": {
        // Reuse the healthy Docker edge in local UI development so HMR can
        // talk to the same API/session surface as the composed application.
        target: "http://localhost:8080",
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
    // Several UI suites replace global browser primitives such as fetch and
    // cookies. Keep them isolated in time so a passing result is repeatable.
    maxWorkers: 1,
    fileParallelism: false,
    testTimeout: 20000,
    coverage: {
      provider: "v8",
      // List the files to measure instead of relying on what the tests happen to import:
      // a module no test touches must show up as 0% rather than disappear from the report.
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/**/*.{test,spec}.{ts,tsx}",
        "src/**/*.d.ts",
        "src/test/**",
        // Generated from specs/**/openapi.yaml; CI checks it for drift instead.
        "src/app/api/generated/**",
        "src/main.tsx",
      ],
      reporter: ["text-summary", "html", "lcov", "json-summary"],
      // A ratchet, not an aspiration: set just under the measured baseline so coverage cannot
      // silently regress. Raise these whenever the measured numbers rise.
      thresholds: {
        lines: 72,
        functions: 55,
        branches: 61,
        statements: 65,
      },
    },
  },
});
