import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CommandPalette } from "../../../app/CommandPalette";
import { intelligenceApi } from "../api";

vi.mock("../api", () => ({
  intelligenceApi: {
    infer: vi.fn(),
    createDraft: vi.fn(),
    executeDraft: vi.fn(),
    getDraft: vi.fn(),
    createExtractionJob: vi.fn(),
  },
}));

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
}

function renderPalette() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CommandPalette />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CommandPalette infer preview B (0.80 gate)", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=test-csrf; path=/";
    vi.stubGlobal("fetch", vi.fn((input) => {
      const url = String(input);
      if (url.includes("/recipes")) {
        return json({ items: [], nextCursor: null });
      }
      if (url.includes("/pantry-items") || url.includes("/grocery")) {
        return json({ id: "new-id", displayName: "onions" }, 201);
      }
      return json({});
    }));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("shows preview when high conf", async () => {
    vi.mocked(intelligenceApi.infer).mockResolvedValue({
      status: "ok",
      confidence: 0.88,
      functionCalls: [{ name: "add_pantry_item", arguments: { name: "onions", quantity: 2, unit: "kg" } }],
      model: "test",
      reasoning: null,
      errorCode: null,
    } as never);

    renderPalette();
    window.dispatchEvent(new CustomEvent("cookfully:open-command"));
    const input = await screen.findByPlaceholderText(/Search recipes or jump somewhere/i, {}, { timeout: 5000 });
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    fireEvent.change(input, { target: { value: "add 2kg onions xyz-no-match-123" } });
    await waitFor(() => expect(screen.getByDisplayValue("add 2kg onions xyz-no-match-123")).toBeInTheDocument());

    // Interpret button should appear in empty state (wait for recipes query to settle)
    const interpretBtn = await screen.findByRole("menuitem", { name: /Interpret with Cookfully/i }, { timeout: 5000 });
    await user.click(interpretBtn);

    expect(await screen.findByText(/We think you mean/, {}, { timeout: 5000 })).toBeInTheDocument();
    // should show Add button
    expect(screen.getByRole("button", { name: /^Add$/ })).toBeInTheDocument();
  });

  it("shows Not sure when low conf", async () => {
    vi.mocked(intelligenceApi.infer).mockResolvedValue({
      status: "ok",
      confidence: 0.6,
      functionCalls: [],
      model: "test",
      reasoning: null,
      errorCode: null,
    } as never);

    renderPalette();
    window.dispatchEvent(new CustomEvent("cookfully:open-command"));
    const input = await screen.findByPlaceholderText(/Search recipes or jump somewhere/i, {}, { timeout: 5000 });
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    fireEvent.change(input, { target: { value: "add 2kg onions xyz-no-match-123" } });
    await waitFor(() => expect(screen.getByDisplayValue("add 2kg onions xyz-no-match-123")).toBeInTheDocument());

    const interpretBtn = await screen.findByRole("menuitem", { name: /Interpret with Cookfully/i }, { timeout: 5000 });
    await user.click(interpretBtn);

    expect(await screen.findByText(/Not sure/, {}, { timeout: 5000 })).toBeInTheDocument();
  });
});
