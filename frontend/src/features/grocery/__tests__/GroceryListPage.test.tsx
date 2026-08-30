import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiProblem } from "../../recipes/api";
import { GroceryListPage } from "../GroceryListPage";
import type { GroceryItem, GroceryList, GroceryShoppingStop } from "../types";

const mocks = vi.hoisted(() => ({
  preferences: vi.fn(),
  plan: vi.fn(),
  get: vi.fn(),
  stops: vi.fn(),
  update: vi.fn(),
  complete: vi.fn(),
  reopen: vi.fn(),
  regenerate: vi.fn(),
  createEmpty: vi.fn(),
  create: vi.fn(),
  remove: vi.fn(),
  createStop: vi.fn(),
  updateStop: vi.fn(),
  removeStop: vi.fn(),
  applyDeductions: vi.fn(),
  reverseDeduction: vi.fn(),
}));

vi.mock("../api", () => ({ groceryApi: mocks }));
vi.mock("../../plans/api", () => ({ planningApi: { preferences: mocks.preferences, plan: mocks.plan } }));
vi.mock("../../pantry/api", () => ({ pantryApi: { applyDeductions: mocks.applyDeductions, reverseDeduction: mocks.reverseDeduction } }));

const stop: GroceryShoppingStop = {
  id: "stop-market",
  name: "Market",
  position: 0,
  version: 1,
};

function item(overrides: Partial<GroceryItem>): GroceryItem {
  return {
    id: overrides.id ?? "item-1",
    displayName: overrides.displayName ?? "Apples",
    quantity: overrides.quantity ?? "2.000000",
    unit: overrides.unit ?? "count",
    checked: overrides.checked ?? false,
    position: overrides.position ?? 0,
    origin: overrides.origin ?? "generated",
    needsReview: overrides.needsReview ?? false,
    shoppingStop: overrides.shoppingStop ?? null,
    sources: overrides.sources ?? [],
    version: overrides.version ?? 1,
  };
}

function list(items: GroceryItem[], status: GroceryList["status"] = "current"): GroceryList {
  return {
    id: "list-1",
    weekStart: "2026-08-24",
    status,
    generatedAt: "2026-08-24T10:00:00Z",
    completedAt: status === "completed" ? "2026-08-24T12:00:00Z" : null,
    items,
    version: 4,
  };
}

const plan = {
  id: "plan-1",
  weekStart: "2026-08-24",
  timezone: "UTC",
  entries: [],
  dayTotals: {},
  weekTotal: {},
  version: 1,
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/app/grocery"]}>
        <GroceryListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("GroceryListPage", () => {
  let currentList: GroceryList;

  beforeEach(() => {
    currentList = list([
      item({ id: "item-market", displayName: "Apples", shoppingStop: stop }),
      item({ id: "item-unassigned", displayName: "Oat milk", position: 1, shoppingStop: null }),
    ]);
    mocks.preferences.mockResolvedValue({ displayName: "Owner", timezone: "UTC", weekStartsOn: 1, version: 1 });
    mocks.plan.mockResolvedValue(plan);
    mocks.get.mockImplementation(async () => currentList);
    mocks.stops.mockResolvedValue([stop]);
    mocks.update.mockImplementation(async (id: string, _version: number, value: Partial<GroceryItem>) => {
      currentList = {
        ...currentList,
        items: currentList.items.map((candidate) => candidate.id === id ? { ...candidate, ...value, version: candidate.version + 1 } : candidate),
      };
      return currentList.items.find((candidate) => candidate.id === id)!;
    });
    mocks.complete.mockImplementation(async () => {
      currentList = list(currentList.items.map((candidate) => ({ ...candidate, checked: true })), "completed");
      return currentList;
    });
    mocks.reopen.mockImplementation(async () => {
      currentList = list(currentList.items, "current");
      return currentList;
    });
    mocks.regenerate.mockResolvedValue(currentList);
    mocks.createEmpty.mockResolvedValue(currentList);
    mocks.create.mockResolvedValue(currentList.items[0]);
    mocks.remove.mockResolvedValue(undefined);
    mocks.createStop.mockResolvedValue(stop);
    mocks.updateStop.mockResolvedValue(stop);
    mocks.removeStop.mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("groups assigned and unassigned items and offers remembered placement", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "Everything you need this week" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Market" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Unassigned" })).toBeVisible();
    expect(screen.getByText("Apples")).toBeVisible();
    expect(screen.getByText("Oat milk")).toBeVisible();

    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Edit Apples"));
    expect(screen.getByLabelText("Shopping stop for Apples")).toHaveValue(stop.id);
    expect(screen.getByLabelText("Always put Apples at this stop")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Always put Apples at this stop"));
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith("item-market", 1, { rememberPlacement: true }));
  });

  it("recovers a stale check-off conflict by offering a list reload", async () => {
    mocks.update.mockRejectedValueOnce(new ApiProblem(409, "The item changed elsewhere."));
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("checkbox", { name: "Oat milk purchased" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed elsewhere/i);
    const before = mocks.get.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Reload list" }));
    await waitFor(() => expect(mocks.get.mock.calls.length).toBeGreaterThan(before));
  });

  it("uses a shopping-first phone composition with sheets for secondary actions", async () => {
    vi.stubGlobal("matchMedia", () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    renderPage();
    expect(await screen.findByRole("heading", { name: "2 left to pick up" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Everything you need this week" })).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Edit Apples"));
    expect(await screen.findByRole("dialog", { name: "Apples" })).toBeVisible();
    expect(screen.getByLabelText("Shopping stop")).toHaveValue(stop.id);

    await user.click(screen.getByLabelText("Close item editor"));
    await user.click(screen.getByLabelText("More grocery actions"));
    expect(await screen.findByRole("dialog", { name: "List actions" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Refresh from plan" })).toBeVisible();
  });

  it("shows all-items-complete state, finishes the pass, and supports reopen", async () => {
    currentList = list([
      item({ id: "item-done", displayName: "Apples", checked: true, shoppingStop: stop }),
    ]);
    renderPage();
    const user = userEvent.setup();
    expect(await screen.findByText("All picked up")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Finish this shopping pass" }));
    await user.click(screen.getByRole("button", { name: "Finish shopping pass" }));
    expect(await screen.findByText("This shopping pass is complete")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reopen list" }));
    await waitFor(() => expect(screen.getByText("Ready when you are")).toBeVisible());
    expect(mocks.reopen).toHaveBeenCalledWith("2026-08-24", 4);
  });
});
