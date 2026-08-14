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
  const onboarding = { state: "pending" as const, firstAction: null, resolvedAt: null, version: 1 };
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/app/recipes"]}><Routes><Route path="/app/recipes" element={<FirstRunJourney onboarding={onboarding} />} /><Route path="/app/recipes/new" element={<h1>Write a recipe</h1>} /><Route path="/app/plan" element={<h1>Your week</h1>} /></Routes></MemoryRouter></QueryClientProvider>);
}

describe("FirstRunJourney", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("centers the first useful recipe and leads directly to writing it", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({ state: "completed", firstAction: "manual_recipe", resolvedAt: "2026-08-13T00:00:00Z", version: 2 })));
    renderJourney();
    const user = userEvent.setup();

    expect(screen.getByRole("heading", { name: "Start with a recipe you already love." })).toBeVisible();
    expect(screen.getByText(/write it from memory or bring it in from the web/i)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Write a recipe" }));
    expect(await screen.findByRole("heading", { name: "Write a recipe" })).toBeVisible();
  });

  it("does not resolve onboarding merely because the import dialog was opened", async () => {
    const fetchMock = vi.fn(() => response({ code: "unexpected" }, 500));
    vi.stubGlobal("fetch", fetchMock);
    renderJourney();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Import from the web" }));
    expect(screen.getByRole("dialog", { name: "Import a recipe" })).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("can be dismissed without changing the owner’s route", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/owner/onboarding") && init?.method === "PUT") return response({ state: "dismissed", firstAction: null, resolvedAt: "2026-08-13T00:00:00Z", version: 2 });
      return response({ state: "pending", firstAction: null, resolvedAt: null, version: 1 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderJourney();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Skip welcome" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Start with a recipe you already love." })).not.toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/owner/onboarding"), expect.objectContaining({ method: "PUT" }));
  });
});
