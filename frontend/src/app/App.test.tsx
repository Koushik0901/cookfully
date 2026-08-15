import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

describe("App", () => {
  it("introduces the nutrition-first product on the landing page", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Good food. Clear choices. Your kind of healthy." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Cookfully" })).toBeInTheDocument();
    expect(screen.getByText(/bring in a recipe/i)).toBeInTheDocument();
  });

  it("keeps Settings and sign out discoverable from the authenticated shell", async () => {
    window.history.pushState({}, "", "/app/recipes");
    document.cookie = "cookfully_csrf=shell-csrf; path=/";
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), window.location.origin).pathname;
      if (path === "/api/v1/auth/session" && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (path === "/api/v1/owner/preferences") return json({ locale: "en-CA" });
      if (path === "/api/v1/owner/onboarding") return json({ state: "completed", version: 1 });
      if (path === "/api/v1/recipes/collections") return json([]);
      if (path === "/api/v1/recipes") return json({ items: [], nextCursor: null });
      return json({ title: "Not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const user = userEvent.setup();

    expect((await screen.findAllByRole("link", { name: "Settings" })).length).toBeGreaterThanOrEqual(1);
    const signOutButtons = screen.getAllByRole("button", { name: "Sign out" });
    expect(signOutButtons.length).toBeGreaterThanOrEqual(1);

    await user.click(signOutButtons[0]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/auth/session",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeVisible();
  });
});

