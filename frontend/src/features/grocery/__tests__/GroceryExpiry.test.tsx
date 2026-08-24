/* eslint-disable @typescript-eslint/no-explicit-any */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GroceryRow } from "../GroceryListPage";

function wrapper(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Grocery expiry", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ id: "1", displayName: "Tomatoes", checked: true, expiresOn: "2026-08-29", expirySource: "auto", needsExpiryDate: false, version: 2, quantity: "1", unit: "lb", origin: "manual", needsReview: false, position: 0, sources: [], shoppingStop: null }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    ));
    document.cookie = "cookfully_csrf=test; path=/";
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("auto badge shows for tomato", () => {
    render(
      wrapper(
        <GroceryRow
          item={
            {
              id: "1",
              displayName: "Tomatoes",
              checked: true,
              expiresOn: "2026-08-29",
              expirySource: "auto",
              needsExpiryDate: false,
              quantity: "1",
              unit: "lb",
              version: 1,
              origin: "manual",
              needsReview: false,
              position: 0,
              sources: [],
              shoppingStop: null,
            } as any
          }
          weekStart="2026-08-18"
          stops={[]}
          readOnly={false}
          sourceMealsByEntry={new Map()}
        />,
      ),
    );
    expect(screen.getByText(/Expir/)).toBeInTheDocument();
    expect(document.querySelector(".expiry-badge")).toBeInTheDocument();
  });

  it("badge has aria-label with expires date", () => {
    render(
      wrapper(
        <GroceryRow
          item={
            {
              id: "2",
              displayName: "Tomatoes",
              checked: true,
              expiresOn: "2026-08-29",
              expirySource: "auto",
              needsExpiryDate: false,
              quantity: "1",
              unit: "lb",
              version: 1,
              origin: "manual",
              needsReview: false,
              position: 0,
              sources: [],
              shoppingStop: null,
            } as any
          }
          weekStart="2026-08-18"
          stops={[]}
          readOnly={false}
          sourceMealsByEntry={new Map()}
        />,
      ),
    );
    expect(screen.getByLabelText(/Expires 2026-08-29/)).toBeInTheDocument();
  });

  it("label sheet opens when needsExpiryDate", async () => {
    render(
      wrapper(
        <GroceryRow
          item={
            {
              id: "3",
              displayName: "Whole Milk",
              checked: true,
              expiresOn: null,
              expirySource: null,
              needsExpiryDate: true,
              quantity: "1",
              unit: "gal",
              version: 1,
              origin: "manual",
              needsReview: false,
              position: 0,
              sources: [],
              shoppingStop: null,
            } as any
          }
          weekStart="2026-08-18"
          stops={[]}
          readOnly={false}
          sourceMealsByEntry={new Map()}
        />,
      ),
    );
    expect(await screen.findByText(/Save expiry/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Expiry date/i)).toBeInTheDocument();
  });

  it("tapping badge reopens sheet", async () => {
    const user = userEvent.setup();
    render(
      wrapper(
        <GroceryRow
          item={
            {
              id: "4",
              displayName: "Tomatoes",
              checked: true,
              expiresOn: "2026-08-29",
              expirySource: "auto",
              needsExpiryDate: false,
              quantity: "1",
              unit: "lb",
              version: 1,
              origin: "manual",
              needsReview: false,
              position: 0,
              sources: [],
              shoppingStop: null,
            } as any
          }
          weekStart="2026-08-18"
          stops={[]}
          readOnly={false}
          sourceMealsByEntry={new Map()}
        />,
      ),
    );
    const badge = screen.getByLabelText(/Expires 2026-08-29/);
    await user.click(badge);
    expect(await screen.findByText(/Save expiry/)).toBeInTheDocument();
  });

  it("saving expiry calls PATCH", async () => {
    const fetchMock = vi.mocked(fetch);
    const user = userEvent.setup();
    render(
      wrapper(
        <GroceryRow
          item={
            {
              id: "5",
              displayName: "Whole Milk",
              checked: true,
              expiresOn: null,
              expirySource: null,
              needsExpiryDate: true,
              quantity: "1",
              unit: "gal",
              version: 1,
              origin: "manual",
              needsReview: false,
              position: 0,
              sources: [],
              shoppingStop: null,
            } as any
          }
          weekStart="2026-08-18"
          stops={[]}
          readOnly={false}
          sourceMealsByEntry={new Map()}
        />,
      ),
    );
    const input = await screen.findByLabelText(/Expiry date/i);
    await user.clear(input);
    await user.type(input, "2026-08-30");
    await user.click(screen.getByRole("button", { name: /Save expiry/ }));
    await waitFor(() => {
      const called = fetchMock.mock.calls.some(([url, init]) => String(url).includes("/grocery-items/5") && (init as RequestInit)?.method === "PATCH");
      expect(called).toBe(true);
    });
  });
});
