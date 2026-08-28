import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RecipeLibraryPage } from "../RecipeLibraryPage";
import { RecipeOrganizationPanel } from "../RecipeOrganizationPanel";
import type { RecipeDetail } from "../types";

const api = vi.hoisted(() => ({
  collections: vi.fn(),
  organize: vi.fn(),
  createCollection: vi.fn(),
  updateCollection: vi.fn(),
  removeCollection: vi.fn(),
  list: vi.fn(),
  get: vi.fn(),
  archive: vi.fn(),
  restore: vi.fn(),
  permanentDelete: vi.fn(),
  bulkArchive: vi.fn(),
}));

vi.mock("../api", () => ({ recipesApi: api }));
vi.mock("../../onboarding/api", () => ({ onboardingApi: { get: vi.fn().mockResolvedValue({ state: "dismissed", version: 2 }) } }));

const collection = {
  id: "collection-weeknight",
  name: "Weeknight favourites for a very full household",
  position: 0,
  version: 1,
  recipeCount: 1,
};

const recipe: RecipeDetail = {
  id: "00000000-0000-4000-8000-000000000001",
  title: "Lemon lentils",
  description: "A weeknight bowl.",
  sourceUrl: null,
  imageUrl: null,
  yieldQuantity: "2.000",
  yieldUnit: "servings",
  prepMinutes: null,
  cookMinutes: null,
  status: "ready",
  archivedFromStatus: null,
  nutritionState: "estimated",
  nutrition: null,
  version: 3,
  updatedAt: "2026-08-28T10:00:00Z",
  favorite: false,
  collections: [],
  mealRoles: [],
  thumbnailCrop: { x: "0", y: "0", width: "1", height: "1" },
  originKind: "manual",
  ingredients: [],
  instructions: [],
  sections: [],
  activeJob: null,
};

function wrapper(children: React.ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("recipe organization UI", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=test-csrf-token; path=/";
    api.collections.mockResolvedValue([collection]);
    api.organize.mockResolvedValue({ ...recipe, favorite: true, version: 4 });
    api.createCollection.mockResolvedValue(collection);
    api.updateCollection.mockResolvedValue(collection);
    api.removeCollection.mockResolvedValue(undefined);
    api.list.mockResolvedValue({ items: [{ ...recipe, title: "A long recipe title that must stay readable on narrow screens" }], nextCursor: null });
    api.get.mockResolvedValue(recipe);
    api.archive.mockResolvedValue(undefined);
    api.restore.mockResolvedValue(recipe);
    api.permanentDelete.mockResolvedValue(undefined);
    api.bulkArchive.mockResolvedValue({ results: [] });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("keeps organization optional while saving favorite, collection, and meal role choices", async () => {
    const saved = vi.fn();
    render(wrapper(<RecipeOrganizationPanel recipe={recipe} onSaved={saved} />));
    const user = userEvent.setup();
    expect(screen.getByRole("button", { name: "Add to favorites" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Add to favorites" }));
    await waitFor(() => expect(api.organize).toHaveBeenCalledWith(recipe.id, 3, {
      favorite: true,
      collectionIds: [],
      mealRoles: [],
    }));
    await user.click(screen.getByText("Keep this easy to find"));
    expect(await screen.findByText(collection.name)).toBeVisible();
    await user.click(screen.getByLabelText(`Weeknight favourites for a very full household`));
    await user.click(screen.getByLabelText("dinner"));
    await user.click(screen.getByRole("button", { name: "Save organization" }));
    await waitFor(() => expect(api.organize).toHaveBeenLastCalledWith(recipe.id, 3, {
      favorite: true,
      collectionIds: [collection.id],
      mealRoles: ["dinner"],
    }));
    expect(saved).toHaveBeenCalled();
  });

  it("shows focused removable filters and keeps long recipe names in the library", async () => {
    render(wrapper(<RecipeLibraryPage />));
    const user = userEvent.setup();
    expect(await screen.findByText("A long recipe title that must stay readable on narrow screens")).toBeVisible();
    await user.click(screen.getByText("Refine recipes"));
    await user.selectOptions(screen.getByLabelText("Collection"), collection.id);
    await user.selectOptions(screen.getByLabelText("Meal moment"), "dinner");
    await user.click(screen.getByLabelText("Favorites only"));
    expect(await screen.findByLabelText("Active recipe filters")).toHaveTextContent("Favorites");
    expect(screen.getByLabelText("Active recipe filters")).toHaveTextContent("Collection:");
    expect(screen.getByLabelText("Active recipe filters")).toHaveTextContent("Meal: dinner");
    await user.click(screen.getByRole("button", { name: /Meal: dinner/ }));
    expect(screen.queryByText("Meal: dinner")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Active recipe filters")).toHaveTextContent("Favorites");
  });
});
