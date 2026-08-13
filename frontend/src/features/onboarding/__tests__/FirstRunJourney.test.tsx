import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FirstRunJourney } from "../FirstRunJourney";

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

function renderJourney() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/app/recipes"]}><Routes><Route path="/app/recipes" element={<FirstRunJourney />} /><Route path="/app/recipes/new" element={<h1>Write a recipe</h1>} /><Route path="/app/plan" element={<h1>Your week</h1>} /></Routes></MemoryRouter></QueryClientProvider>);
}

describe("FirstRunJourney", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("starts with familiar food instead of measurements and leads directly to a recipe", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/owner/onboarding") && init?.method !== "PUT") return response({ state: "pending", firstAction: null, resolvedAt: null, version: 1 });
      return response({ state: "completed", firstAction: "manual_recipe", resolvedAt: "2026-08-13T00:00:00Z", version: 2 });
    }));
    renderJourney();
    const user = userEvent.setup();

    expect(await screen.findByRole("heading", { name: "Start with the food you already know." })).toBeVisible();
    expect(screen.getByText(/do not need a diet label, body measurements/i)).toBeVisible();
    await user.click(screen.getAllByRole("button", { name: "Choose this" })[0]);
    expect(await screen.findByRole("heading", { name: "Write a recipe" })).toBeVisible();
  });

  it("leaves the kitchen uncluttered if the optional preference cannot load", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({ code: "unavailable" }, 503)));
    renderJourney();

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled());
    expect(screen.queryByText("Preparing your kitchen")).not.toBeInTheDocument();
    expect(screen.queryByText("Your welcome guide could not be loaded")).not.toBeInTheDocument();
  });

  it("can be dismissed without changing the owner’s route", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/owner/onboarding") && init?.method === "PUT") return response({ state: "dismissed", firstAction: null, resolvedAt: "2026-08-13T00:00:00Z", version: 2 });
      return response({ state: "pending", firstAction: null, resolvedAt: null, version: 1 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderJourney();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Skip for now" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Start with the food you already know." })).not.toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/owner/onboarding"), expect.objectContaining({ method: "PUT" }));
  });
});
