import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RecipeLibraryPage } from "../RecipeLibraryPage";
import type { RecipePage } from "../types";

const firstId = "00000000-0000-4000-8000-000000000101";
const secondId = "00000000-0000-4000-8000-000000000102";

const page: RecipePage = {
  items: [
    {
      id: firstId,
      title: "Roasted salmon bowl",
      sourceUrl: null,
      imageUrl: null,
      yieldQuantity: "2",
      yieldUnit: "servings",
      status: "ready",
      archivedFromStatus: null,
      nutritionState: "estimated",
      nutrition: null,
      version: 1,
      updatedAt: "2026-08-17T10:00:00Z",
      favorite: false,
      collections: [],
      mealRoles: ["dinner"],
      thumbnailCrop: { focalX: "0.5", focalY: "0.5", zoom: "1" },
      originKind: "manual",
    },
    {
      id: secondId,
      title: "Citrus grain salad",
      sourceUrl: null,
      imageUrl: null,
      yieldQuantity: "4",
      yieldUnit: "servings",
      status: "ready",
      archivedFromStatus: null,
      nutritionState: "estimated",
      nutrition: null,
      version: 1,
      updatedAt: "2026-08-16T10:00:00Z",
      favorite: false,
      collections: [],
      mealRoles: ["lunch"],
      thumbnailCrop: { focalX: "0.5", focalY: "0.5", zoom: "1" },
      originKind: "manual",
    },
  ],
  nextCursor: null,
};

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/app/recipes"]}>
        <RecipeLibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("recipe library density", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=library-csrf; path=/";
    vi.stubGlobal("fetch", vi.fn((input, init) => {
      const path = String(input);
      if (path.includes("/owner-onboarding")) return json({ state: "completed", version: 1 });
      if (path.endsWith("/recipes/collections")) return json([]);
      if (path.endsWith("/recipes/bulk/archive") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { recipes: Array<{ id: string; version: number }> };
        return json({ results: body.recipes.map((item) => ({ id: item.id, status: "archived", version: item.version + 1, code: null, message: null })) });
      }
      if (path.includes("/recipes")) return json(page);
      return json({}, 404);
    }));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("makes search and add recipe the clear first actions", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "What would you like to cook?" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Add recipe" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Import recipe" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Give me ideas" })).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search recipes" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "All recipes" })).toHaveAttribute("aria-controls", "recipe-view-panel");
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", "recipe-view-tab-all");
  });

  it("archives selected recipes together and clears the selection", async () => {
    renderPage();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "What would you like to cook?" });

    await user.click(screen.getByRole("button", { name: "Select recipes" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Roasted salmon bowl" }));
    await user.click(screen.getByRole("checkbox", { name: "Select Citrus grain salad" }));
    expect(screen.getByRole("button", { name: "Archive 2 selected recipes" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Archive 2 selected recipes" }));
    await waitFor(() => expect(screen.getByText("2 recipes archived.")).toBeVisible());
    expect(screen.queryByRole("checkbox", { name: "Select Roasted salmon bowl" })).not.toBeInTheDocument();
  });
});
