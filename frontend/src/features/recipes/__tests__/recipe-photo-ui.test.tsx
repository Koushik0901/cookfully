import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RecipeCard } from "../RecipeCard";
import { RecipeEditorPage } from "../RecipeEditorPage";
import type { Recipe, RecipeDetail } from "../types";

const recipe: RecipeDetail = {
  id: "00000000-0000-4000-8000-000000000001",
  title: "Lemon lentils",
  description: "A weeknight bowl.",
  sourceUrl: null,
  imageUrl: "/api/v1/media/old-cover.jpg",
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
  ingredients: [
    {
      id: "00000000-0000-4000-8000-000000000002",
      position: 0,
      originalText: "1 cup lentils",
      quantityMin: "1.000000",
      quantityMax: null,
      unit: "cup",
      food: "lentils",
      preparation: null,
      optional: false,
      parseStatus: "parsed",
      matchStatus: "matched",
      candidateEvidence: [],
      assumptions: [],
    },
  ],
  instructions: [{ position: 0, text: "Simmer until tender." }],
  sections: [],
  activeJob: null,
};

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

function renderEditor(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/app/recipes/new" element={<RecipeEditorPage />} />
          <Route path="/app/recipes/:recipeId/edit" element={<RecipeEditorPage />} />
          <Route path="/app/recipes/:recipeId" element={<RecipeEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("recipe photo UI", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=test-csrf-token; path=/";
    vi.stubGlobal("fetch", vi.fn(() => response(recipe)));
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:recipe-preview"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("previews the draft with its image fallback and structured content", async () => {
    renderEditor("/app/recipes/new");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Recipe title"), "Sheet-pan lentils");
    await user.type(screen.getByLabelText("ingredient 1 for main recipe"), "1 cup lentils");
    await user.type(screen.getByLabelText("step 1 for main recipe"), "Roast until tender.");
    await user.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByRole("heading", { name: "Sheet-pan lentils" })).toBeVisible();
    expect(screen.getByText("1 cup lentils")).toBeVisible();
    expect(screen.getByText("Roast until tender.", { selector: "li" })).toBeVisible();
    expect(screen.getByText("Nutrition is calculated after saving.")).toBeVisible();
    expect(document.querySelector(".recipe-fallback-art")).toBeInTheDocument();
  });

  it("recovers from an invalid upload and accepts a replacement after retry", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) =>
      String(input).includes("/recipes/photo-stages")
        ? fetchMock.mock.calls.length === 1
          ? response({ detail: "The image could not be decoded.", code: "recipe_photo_invalid" }, 422)
          : response({ id: "stage-1", expiresAt: "2026-08-28T11:00:00Z" })
        : response(recipe),
    );
    renderEditor("/app/recipes/new");
    const user = userEvent.setup();
    const input = screen.getByLabelText("Upload photo");
    await user.upload(input, new File(["not-an-image"], "broken.png", { type: "image/png" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be prepared/i);
    await user.upload(input, new File(["valid-image"], "cover.png", { type: "image/png" }));
    await waitFor(() => expect(screen.getByText("Photo ready to save")).toBeVisible());
  });

  it("removes an existing cover and can stage a replacement", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      if (String(input).includes("/recipes/photo-stages")) {
        return response({ id: "stage-2", expiresAt: "2026-08-28T11:00:00Z" });
      }
      if (init?.method === "DELETE") return response({ ...recipe, imageUrl: null, version: 4 });
      return response(recipe);
    });
    renderEditor(`/app/recipes/${recipe.id}/edit`);
    const user = userEvent.setup();
    await screen.findByDisplayValue("Lemon lentils");
    await user.click(screen.getByRole("button", { name: "Remove photo" }));
    await user.click(screen.getByRole("button", { name: "Remove photo" }));
    expect(screen.getByText("No cover selected.")).toBeVisible();
    await user.upload(
      screen.getByLabelText("Upload photo"),
      new File(["valid-image"], "replacement.png", { type: "image/png" }),
    );
    await waitFor(() => expect(screen.getByText("Photo ready to save")).toBeVisible());
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/recipes/photo-stages"))).toBe(
      true,
    );
  });

  it("keeps fallback art visible for a long, unpictured library title", () => {
    const value = {
      ...recipe,
      title: "A very long family recipe name that should remain readable without a cover image",
      imageUrl: null,
    } as Recipe;
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RecipeCard recipe={value} onArchive={vi.fn()} onRestore={vi.fn()} onDelete={vi.fn()} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("link", { name: value.title })).toBeVisible();
    expect(document.querySelector(".recipe-fallback-art")).toBeInTheDocument();
  });
});
