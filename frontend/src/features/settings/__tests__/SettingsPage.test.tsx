import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "../SettingsPage";

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
}

describe("settings page", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=settings-csrf; path=/";
    vi.stubGlobal(
      "fetch",
      vi.fn((input) => {
        const path = String(input);
        if (path.includes("/owner/preferences")) {
          return json({ displayName: "Owner", timezone: "UTC", weekStartsOn: 1, version: 1 });
        }
        if (path.includes("/auth/sessions")) {
          return json({
            sessions: [
              {
                id: "00000000-0000-4000-8000-000000000001",
                clientLabel: "Chrome on Windows",
                createdAt: "2026-08-12T00:00:00Z",
                lastSeenAt: "2026-08-12T00:00:00Z",
                isCurrent: true,
              },
            ],
          });
        }
        return json({}, 404);
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function renderPage() {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
    });
    return render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );
  }

  it("renders Account, Security, Connections, Nutrition data, Intelligence, and Jobs tabs and edits account details", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const path = String(input);
      if (init?.method === "PUT" && path.includes("/owner/preferences")) {
        return json({ displayName: "Alex", timezone: "UTC", weekStartsOn: 1, version: 2 });
      }
      if (path.includes("/owner/preferences")) {
        return json({ displayName: "Owner", timezone: "UTC", weekStartsOn: 1, version: 1 });
      }
      return json({}, 404);
    });

    renderPage();
    const user = userEvent.setup();

    expect(screen.getByRole("tab", { name: "Account" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Security" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Connections" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Nutrition data" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Intelligence" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Jobs" })).toBeVisible();

    expect(await screen.findByLabelText("Display name")).toHaveValue("Owner");
    await user.clear(screen.getByLabelText("Display name"));
    await user.type(screen.getByLabelText("Display name"), "Alex");
    await user.click(screen.getByRole("button", { name: "Save account" }));
    await waitFor(() => expect(screen.getByText("Account details saved.")).toBeVisible());
  });

  it("previews model resources before saving nutrition intelligence settings", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const path = String(input);
      if (path.includes("/nutrition-intelligence/settings") && !init?.method) {
        return json({
          backend: "hashing",
          modelName: "BAAI/bge-small-en-v1.5",
          modelRevision: null,
          concurrency: 1,
          version: 1,
          runtimeStatus: "ready",
        });
      }
      if (path.includes("/nutrition-intelligence/estimate")) {
        return json({
          backend: "fastembed",
          modelName: "BAAI/bge-small-en-v1.5",
          modelRevision: "abc123456789",
          concurrency: 2,
          activeFoodCount: 8100,
          downloadBytes: 133466304,
          diskBytes: 133466304,
          modelMemoryBytes: 268435456,
          perJobMemoryBytes: 12582912,
          totalMemoryBytes: 293601280,
          requiredCpuCores: 2,
          availableCpuCores: 8,
          availableMemoryBytes: 8589934592,
          availableDiskBytes: 21474836480,
          memoryHeadroomBytes: 8296333312,
          status: "safe",
          warnings: [],
          estimateHash: "a".repeat(64),
        });
      }
      return json({}, 404);
    });

    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Intelligence" }));

    expect(await screen.findByText("Plan the load before you save.")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Matching backend"), "fastembed");
    expect(await screen.findByText("Comfortable headroom")).toBeVisible();
    expect(screen.getByText("127 MB")).toBeVisible();
    expect(screen.getByText(/8,100 active foods/)).toBeVisible();
  });

  it("shows active sessions on the Security tab", async () => {
    renderPage();
    const user = userEvent.setup();

    await user.click(screen.getByRole("tab", { name: "Security" }));
    expect(await screen.findByText("Chrome on Windows")).toBeVisible();
    expect(screen.getByText(/This device/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Change password" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeVisible();
  });

  it("uses the shared settings-tabs structure without dead classes", () => {
    renderPage();
    const account = screen.getByRole("tab", { name: "Account" });
    expect(account).toHaveAttribute("aria-selected", "true");
    expect(account.className).not.toContain("settings-tab--active");
  });
});
