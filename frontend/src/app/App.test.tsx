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
    await user.keyboard("{Control>}k{/Control}");
    expect(await screen.findByRole("dialog", { name: "Search Cookfully" })).toBeVisible();
    expect(screen.getByPlaceholderText("Search recipes or jump somewhere…")).toHaveFocus();
    await user.keyboard("{Escape}");

    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/auth/session",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeVisible();
  });

  it("opens the authenticated kitchen on Home with one useful next action", async () => {
    window.history.pushState({}, "", "/app");
    document.cookie = "cookfully_csrf=home-csrf; path=/";
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = new URL(String(input), window.location.origin).pathname;
      if (path === "/api/v1/owner/preferences") {
        return json({ displayName: "Owner", timezone: "America/Vancouver", weekStartsOn: 1, version: 1 });
      }
      if (path.startsWith("/api/v1/meal-plans/")) return json({ title: "No plan" }, 404);
      if (path === "/api/v1/pantry-items") return json([]);
      if (path === "/api/v1/pantry/recipe-matches") return json([]);
      if (path === "/api/v1/recipes") return json({ items: [{
        id: "00000000-0000-4000-8000-000000000501",
        title: "Lemony lentils",
        sourceUrl: null,
        imageUrl: null,
        yieldQuantity: "4",
        yieldUnit: "servings",
        status: "ready",
        archivedFromStatus: null,
        nutritionState: "estimated",
        nutrition: null,
        version: 1,
        updatedAt: "2026-08-20T12:00:00Z",
        favorite: false,
        collections: [],
        mealRoles: ["dinner"],
        thumbnailCrop: { x: "0", y: "0", width: "1", height: "1" },
        originKind: "manual",
      }], nextCursor: null });
      return json({ title: "Not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: /^Good (morning|afternoon|evening)$/ })).toBeVisible();
    expect(await screen.findByRole("link", { name: "Plan tonight" })).toHaveAttribute("href", expect.stringMatching(/^\/app\/plan\?date=\d{4}-\d{2}-\d{2}&slot=dinner$/));
    expect(screen.getByRole("heading", { name: "No meals planned" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Use soon" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Quick actions" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Cook next" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Recently saved" })).toBeVisible();
  });
});

