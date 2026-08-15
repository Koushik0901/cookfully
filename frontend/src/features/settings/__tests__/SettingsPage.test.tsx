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

  it("renders Account, Security, Connections, and Nutrition data tabs and edits account details", async () => {
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

    expect(await screen.findByLabelText("Display name")).toHaveValue("Owner");
    await user.clear(screen.getByLabelText("Display name"));
    await user.type(screen.getByLabelText("Display name"), "Alex");
    await user.click(screen.getByRole("button", { name: "Save account" }));
    await waitFor(() => expect(screen.getByText("Account details saved.")).toBeVisible());
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
