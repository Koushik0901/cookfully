import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentAccessPage } from "../AgentAccessPage";

const existingToken = {
  id: "00000000-0000-4000-8000-000000000101",
  name: "Meal planner read access",
  scopes: ["goals:read", "plans:read"],
  createdAt: "2026-03-01T12:00:00Z",
  expiresAt: null,
  lastUsedAt: "2026-03-10T18:30:00Z",
  revokedAt: null,
};

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AgentAccessPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("agent access settings", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=agent-access-csrf; path=/";
    vi.stubGlobal("crypto", {
      randomUUID: vi.fn(() => "00000000-0000-4000-8000-000000000999"),
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input, init) => {
        const path = String(input);
        if (path.endsWith("/access-tokens") && !init?.method) return json([existingToken]);
        if (path.endsWith("/access-tokens") && init?.method === "POST") {
          return json(
            {
              ...existingToken,
              id: "00000000-0000-4000-8000-000000000202",
              name: "Workout assistant",
              scopes: ["plans:read", "plans:write"],
              createdAt: "2026-03-11T10:00:00Z",
              lastUsedAt: null,
              secret: "cookfully_once_only_secret_12345678901234567890",
            },
            201,
          );
        }
        if (path.includes("/access-tokens/") && init?.method === "DELETE") return json(null, 204);
        return json({}, 404);
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("creates a least-privilege token and presents its secret exactly once", async () => {
    renderPage();
    const user = userEvent.setup({ writeToClipboard: false });
    expect(await screen.findByRole("heading", { name: "Agent access" })).toBeVisible();
    expect(await screen.findByText("Meal planner read access")).toBeVisible();
    expect(screen.getByLabelText("Read meal plans")).toBeChecked();
    expect(screen.getByLabelText("Write meal plans")).not.toBeChecked();

    await user.type(screen.getByLabelText("Token name"), "Workout assistant");
    await user.click(screen.getByLabelText("Write meal plans"));
    await user.click(screen.getByRole("button", { name: "Create access token" }));

    const oneTime = await screen.findByRole("region", { name: "One-time token secret" });
    expect(within(oneTime).getByText("cookfully_once_only_secret_12345678901234567890")).toBeVisible();
    expect(within(oneTime).getByText(/shown only once/i)).toBeVisible();
    await user.click(within(oneTime).getByRole("button", { name: "Copy token" }));
    expect(await within(oneTime).findByText("Copied to clipboard.")).toBeVisible();
    await user.click(within(oneTime).getByRole("button", { name: "I have stored it" }));
    expect(screen.queryByText("cookfully_once_only_secret_12345678901234567890")).not.toBeInTheDocument();

    const create = vi
      .mocked(fetch)
      .mock.calls.find(([input, init]) => String(input).endsWith("/access-tokens") && init?.method === "POST");
    expect(JSON.parse(String(create?.[1]?.body))).toEqual({
      name: "Workout assistant",
      scopes: ["goals:read", "plans:read", "plans:write"],
      expiresAt: null,
    });
  });

  it("requires confirmation before revoking a token and refreshes the active list", async () => {
    renderPage();
    const user = userEvent.setup();
    const token = await screen.findByRole("article", { name: "Meal planner read access" });
    await user.click(within(token).getByRole("button", { name: "Revoke" }));
    expect(screen.getByRole("dialog", { name: "Revoke access token?" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Revoke token" }));
    expect(await screen.findByText("Token revoked. Existing connections can no longer use it.")).toBeVisible();
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      `/api/v1/access-tokens/${existingToken.id}`,
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
