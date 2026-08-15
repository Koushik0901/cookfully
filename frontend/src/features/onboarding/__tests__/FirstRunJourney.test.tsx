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
  const onboarding = { state: "pending" as const, firstAction: null, referenceDataChoice: null, resolvedAt: null, version: 1 };
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/journey"]}><Routes><Route path="/journey" element={<FirstRunJourney onboarding={onboarding} />} /><Route path="/app/recipes" element={<h1>Recipe library</h1>} /><Route path="/app/recipes/new" element={<h1>Write a recipe</h1>} /><Route path="/app/plan" element={<h1>Your week</h1>} /></Routes></MemoryRouter></QueryClientProvider>);
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
    expect(screen.getByRole("dialog", { name: "Import recipes" })).toBeVisible();
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

  it("guides the nutrition choice and installs in the background without blocking", async () => {
    const putBodies: unknown[] = [];
    const postBodies: unknown[] = [];
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/owner/onboarding") && init?.method === "PUT") {
        putBodies.push(JSON.parse(String(init.body)));
        return response({ state: "completed", firstAction: null, referenceDataChoice: "foundation_sr_legacy", resolvedAt: "2026-08-13T00:00:00Z", version: 2 });
      }
      if (url.endsWith("/reference-data/install") && init?.method === "POST") {
        postBodies.push(JSON.parse(String(init.body)));
        return response({ jobId: "00000000-0000-4000-8000-000000000009", status: "queued" });
      }
      return response({ state: "pending", firstAction: null, resolvedAt: null, version: 1 });
    });
    const user = userEvent.setup();
    renderJourney();
    await user.click(await screen.findByRole("button", { name: "Set up nutrition data" }));
    expect(screen.getByRole("heading", { name: "Real nutrition numbers?" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Foundation \+ SR Legacy only/ }));
    await waitFor(() => {
      expect(putBodies).toEqual([expect.objectContaining({ state: "completed", referenceDataChoice: "foundation_sr_legacy" })]);
      expect(postBodies).toEqual([{ datasets: ["foundation_sr_legacy"] }]);
    });
    expect(await screen.findByRole("heading", { name: "Recipe library" })).toBeVisible();
  });

  it("persists 'not now' without starting an install", async () => {
    const putBodies: unknown[] = [];
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/owner/onboarding") && init?.method === "PUT") {
        putBodies.push(JSON.parse(String(init.body)));
        return response({ state: "completed", firstAction: null, referenceDataChoice: "none", resolvedAt: "2026-08-13T00:00:00Z", version: 2 });
      }
      return response({ state: "pending", firstAction: null, resolvedAt: null, version: 1 });
    });
    const user = userEvent.setup();
    renderJourney();
    await user.click(await screen.findByRole("button", { name: "Set up nutrition data" }));
    await user.click(screen.getByRole("button", { name: /^Not now/ }));
    await waitFor(() => {
      expect(putBodies).toEqual([expect.objectContaining({ referenceDataChoice: "none" })]);
    });
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/reference-data/install"))).toBe(false);
    expect(await screen.findByRole("heading", { name: "Recipe library" })).toBeVisible();
  });
});
