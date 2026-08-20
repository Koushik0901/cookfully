import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { unavailableMicronutrients } from "../../../test/fixtures";

import type { Job, Recipe, RecipeDetail } from "../types";
import { CookModePage } from "../CookModePage";
import { RecipeCard } from "../RecipeCard";
import { RecipeDetailPage } from "../RecipeDetailPage";
import { RecipeEditorPage } from "../RecipeEditorPage";

const recipe: RecipeDetail = {
  id: "00000000-0000-4000-8000-000000000001",
  title: "Exact oats",
  description: "A measured breakfast",
  sourceUrl: "https://example.com/oats",
  imageUrl: null,
  yieldQuantity: "2.500",
  yieldUnit: "servings",
  status: "ready",
  archivedFromStatus: null,
      nutritionState: "estimated",
      favorite: false,
      collections: [],
      mealRoles: [],
  nutrition: {
    status: "estimated",
    basisServings: "2.500",
    coverageRatio: "0.875000",
    caloriesKcal: "512.340000",
    proteinG: "31.125000",
    carbohydrateG: "61.500000",
    fatG: "14.250000",
    micronutrients: {
      ...unavailableMicronutrients,
      dietaryFiberG: { ...unavailableMicronutrients.dietaryFiberG, value: "8.5", coverageRatio: "0.875", source: "reference" },
      sodiumMg: { ...unavailableMicronutrients.sodiumMg, value: "0", explicitZero: true, coverageRatio: "0.875", source: "reference" },
    },
    provenance: [{ kind: "reference", label: "USDA Foundation Foods", version: "2026-04-30" }],
    assumptions: ["A level tablespoon was converted by density."],
    corrections: [
      {
        id: "00000000-0000-4000-8000-000000000009",
        ingredientId: null,
        field: "protein_g",
        decimalValue: "31.125000",
        active: true,
        createdAt: "2026-08-10T10:00:00Z",
        reason: "Package label",
      },
    ],
  },
  version: 3,
  updatedAt: "2026-08-10T10:00:00Z",
  thumbnailCrop: { focalX: "0.5", focalY: "0.5", zoom: "1" },
  originKind: "manual",
  ingredients: [
    {
      id: "00000000-0000-4000-8000-000000000002",
      position: 0,
      originalText: "1.250000 cups rolled oats",
      quantityMin: "1.250000",
      quantityMax: null,
      unit: "cups",
      food: "rolled oats",
      preparation: null,
      optional: false,
      parseStatus: "parsed",
      matchStatus: "matched",
      candidateEvidence: [],
      assumptions: [],
    },
  ],
  instructions: [{ position: 0, text: "Mix and chill." }],
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

function renderRoute(element: React.ReactNode, path = "/app/recipes/00000000-0000-4000-8000-000000000001", state?: unknown) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[{ pathname: path, state }]}>
        <Routes>
          <Route path="/app/recipes/:recipeId" element={element} />
          <Route path="/app/recipes/:recipeId/cook" element={element} />
          <Route path="/app/recipes/:recipeId/edit" element={element} />
          <Route path="/app/recipes/new" element={element} />
          <Route path="/app/recipes" element={<div>Recipe library</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("recipe UI", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=test-csrf-token; path=/";
    vi.stubGlobal("fetch", vi.fn(() => response(recipe)));
  });

  afterEach(() => {
    cleanup();
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function renderCard(value: Recipe = recipe as Recipe, handlers: Partial<{ onArchive: (id: string, version: number) => void; onRestore: (id: string, version: number) => void; onDelete: (id: string, version: number) => void }> = {}) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <RecipeCard
            recipe={value}
            onArchive={handlers.onArchive ?? vi.fn()}
            onRestore={handlers.onRestore ?? vi.fn()}
            onDelete={handlers.onDelete ?? vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("renders a keyboard-accessible card with human-readable nutrition", () => {
    renderCard();

    expect(screen.getByRole("link", { name: "Exact oats" })).toHaveAttribute(
      "href",
      `/app/recipes/${recipe.id}`,
    );
    expect(screen.getByText("512 kcal")).toBeVisible();
    expect(screen.getByText("31.1 g")).toBeVisible();
    expect(document.querySelector('[data-fallback-kind="breakfast"]')).toHaveAttribute("src", "/media/recipe-fallbacks/breakfast.jpg");
    expect(screen.getByText("Ready", { selector: ".recipe-card__state" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Add Exact oats to favorites" })).toBeVisible();
  });

  it("offers a compact action menu instead of a permanent archive pill", async () => {
    const onArchive = vi.fn();
    renderCard(recipe as Recipe, { onArchive });
    const user = userEvent.setup();

    expect(screen.queryByRole("button", { name: /archive exact oats/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "More actions for Exact oats" }));
    expect(screen.getByRole("menuitem", { name: /edit recipe/i })).toHaveAttribute("href", `/app/recipes/${recipe.id}/edit`);
    expect(screen.getByRole("menuitem", { name: /archive recipe/i })).toBeVisible();
    expect(screen.getByRole("menuitem", { name: /delete recipe/i })).toBeVisible();
    await user.click(screen.getByRole("menuitem", { name: /archive recipe/i }));
    expect(onArchive).toHaveBeenCalledWith(recipe.id, 3);
  });

  it("shows restore instead of archive for archived recipes", async () => {
    const onRestore = vi.fn();
    renderCard({ ...recipe, status: "archived" } as Recipe, { onRestore });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "More actions for Exact oats" }));
    expect(screen.queryByRole("menuitem", { name: /archive recipe/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: /restore recipe/i }));
    expect(onRestore).toHaveBeenCalledWith(recipe.id, 3);
  });

  it("moves recipes between collections from the card menu without leaving the library", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      if (String(input).endsWith("/recipes/collections") && init?.method !== "POST") {
        return response([{ id: "c1", name: "Weeknights", position: 0, version: 1, recipeCount: 0 }]);
      }
      if (String(input).endsWith("/organization") && init?.method === "PUT") {
        return response({ ...recipe, collections: [{ id: "c1", name: "Weeknights", position: 0 }], version: 4 });
      }
      return response(recipe);
    });
    renderCard();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "More actions for Exact oats" }));
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Weeknights" })).toBeVisible());
    await user.click(screen.getByRole("menuitem", { name: "Weeknights" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith("/organization") && init?.method === "PUT");
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        favorite: false,
        collectionIds: ["c1"],
        mealRoles: [],
      });
    });
  });

  it("labels manually corrected nutrition consistently on recipe cards", () => {
    renderCard({ ...recipe, nutrition: { ...recipe.nutrition!, status: "manual" } } as Recipe);
    expect(screen.getByText("Manual", { selector: ".recipe-card__state" })).toBeVisible();
  });

  it("keeps nutrition state in the metadata line, not over the food image", () => {
    renderCard();
    expect(document.querySelector(".recipe-card__media .recipe-card__state")).not.toBeInTheDocument();
    expect(document.querySelector(".recipe-card__body .recipe-card__state")).toBeVisible();
  });

  it("keeps a real recipe image ahead of generated fallback art", () => {
    renderCard({ ...recipe, imageUrl: "/media/actual-recipe.jpg" } as Recipe);
    expect(document.querySelector(".recipe-card__media img")).toHaveAttribute("src", "/media/actual-recipe.jpg");
    expect(document.querySelector(".recipe-fallback-art")).not.toBeInTheDocument();
  });

  it("guides cooking as a focused step flow with an ingredient checklist and completion moment", async () => {
    vi.mocked(fetch).mockImplementation(() => response({
      ...recipe,
      instructions: [
        { position: 0, text: "Mix the oats." },
        { position: 1, text: "Chill and serve." },
      ],
    }));
    renderRoute(<CookModePage />, `/app/recipes/${recipe.id}/cook`);
    const user = userEvent.setup();

    expect(await screen.findByRole("heading", { name: "Exact oats" })).toBeVisible();
    expect(screen.getByText("Step 1 of 2")).toBeVisible();
    expect(screen.getByText("Mix the oats.")).toBeVisible();
    expect(screen.getByRole("link", { name: "Leave" })).toHaveAttribute("href", `/app/recipes/${recipe.id}`);

    await user.click(screen.getByRole("checkbox"));
    expect(screen.getByText("Everything’s ready to cook.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Next step" }));
    expect(screen.getByText("Chill and serve.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Finish cooking" }));
    expect(screen.getByRole("heading", { name: "Time to eat." })).toBeVisible();
    expect(document.querySelector('.cook-mode__complete [data-companion-moment="milestone"]')).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Cook again" }));
    expect(screen.getByText("Mix the oats.")).toBeVisible();
  });

  it("keeps stale lifecycle warnings ahead of manual provenance on recipe cards", () => {
    renderCard({ ...recipe, nutritionState: "stale", nutrition: { ...recipe.nutrition!, status: "manual" } } as Recipe);
    expect(screen.getByText("Needs review", { selector: ".recipe-card__state" })).toBeVisible();
  });

  it("attributes an imported recipe to its source with a prominent new-tab link", async () => {
    renderRoute(<RecipeDetailPage />);
    expect(await screen.findByRole("heading", { name: "Exact oats" })).toBeVisible();
    const sourceLink = screen.getByRole("link", { name: /example\.com/i });
    expect(sourceLink).toHaveAttribute("href", "https://example.com/oats");
    expect(sourceLink).toHaveAttribute("target", "_blank");
    expect(sourceLink).toHaveAttribute("rel", "noopener noreferrer");
    expect(document.querySelector(".recipe-hero__facts .recipe-source")).toBeTruthy();
    expect(screen.queryByText("Original source")).not.toBeInTheDocument();
  });

  it("validates exact decimals and preserves original ingredient text in the editor", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      if (String(input).endsWith("/recipes") && init?.method === "POST") return response(recipe, 201);
      return response(recipe);
    });
    renderRoute(<RecipeEditorPage />, "/app/recipes/new");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Recipe title"), "Exact oats");
    await user.clear(screen.getByLabelText("Yield quantity"));
    await user.type(screen.getByLabelText("Yield quantity"), "2.1234567");
    await user.type(screen.getByLabelText("ingredient 1 for main recipe"), "1 1/4 cups rolled oats");
    await user.click(screen.getByRole("button", { name: "Save recipe" }));
    expect(await screen.findByText(/up to six decimal places/i)).toBeVisible();

    await user.clear(screen.getByLabelText("Yield quantity"));
    await user.type(screen.getByLabelText("Yield quantity"), "2.500");
    await user.click(screen.getByRole("button", { name: "Save recipe" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const createCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      yieldQuantity: "2.500",
      ingredients: [{ originalText: "1 1/4 cups rolled oats" }],
    });
  });

  it("discloses provenance, assumptions, corrections, and planning limitations", async () => {
    renderRoute(<RecipeDetailPage />);
    expect(await screen.findByRole("heading", { name: "Exact oats" })).toBeVisible();
    expect(screen.getByText("1.25 cups rolled oats")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Nutrition" })).toBeVisible();
    expect(document.querySelectorAll(".recipe-nutrition-summary dt")).toHaveLength(4);
    expect(document.querySelector(".recipe-nutrition-overview")).not.toBeInTheDocument();
    expect(screen.getByText("Nutrition details and evidence")).toBeVisible();
    expect(screen.queryByLabelText("Nutrition field")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Nutrition details and evidence"));
    expect(screen.getByText(/planning aid, not medical advice/i)).toBeVisible();
    expect(screen.getByText("Basis: 2.5 servings · 88% ingredient coverage")).toBeVisible();
    await userEvent.click(screen.getByText(/what does this status mean/i));
    expect(screen.getByText(/calculated from matched ingredients/i)).toBeVisible();
    expect(screen.getByText(/percentage of quantified ingredients/i)).toBeVisible();
    expect(screen.getByText("USDA Foundation Foods")).toBeVisible();
    expect(screen.getByText("8.5 g")).toBeVisible();
    expect(screen.getByText(/level tablespoon/i)).toBeVisible();
    expect(screen.getByText(/package label/i)).toBeVisible();
  });

  it("confirms a saved recipe with the one-shot companion moment", async () => {
    renderRoute(<RecipeDetailPage />, `/app/recipes/${recipe.id}`, { recipeSaved: true });

    expect(await screen.findByText("Recipe saved")).toBeVisible();
    expect(document.querySelector('.recipe-saved-moment [data-companion-moment="success"]')).toBeVisible();
  });

  it("edits macro and micronutrient values through the common recipe editor", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      if (String(input).endsWith(`/recipes/${recipe.id}`) && init?.method === "PUT") {
        return response(recipe);
      }
      if (String(input).includes("/nutrition/corrections") && init?.method === "POST") {
        return response({ ...recipe.nutrition, status: "manual" });
      }
      return response(recipe);
    });
    renderRoute(<RecipeEditorPage />, `/app/recipes/${recipe.id}/edit`);
    const user = userEvent.setup();
    await screen.findByDisplayValue("Exact oats");
    await user.click(screen.getByText("Nutrition values"));
    await user.clear(screen.getByLabelText("Protein (g)"));
    await user.type(screen.getByLabelText("Protein (g)"), "32.000000");
    await user.click(screen.getByText("Edit micronutrients"));
    await user.clear(screen.getByLabelText("Sodium (mg)"));
    await user.type(screen.getByLabelText("Sodium (mg)"), "125");
    await user.type(screen.getByLabelText("Source or reason"), "Updated package label");
    await user.click(screen.getByRole("button", { name: "Save recipe" }));
    await waitFor(() => {
      const corrections = fetchMock.mock.calls.filter(([input, init]) => String(input).includes("/nutrition/corrections") && init?.method === "POST");
      expect(corrections).toHaveLength(2);
      expect(corrections.map(([, init]) => JSON.parse(String(init?.body)))).toEqual(expect.arrayContaining([
        expect.objectContaining({ field: "protein_g", decimalValue: "32.000000", reason: "Updated package label" }),
        expect.objectContaining({ field: "sodium_mg", decimalValue: "125", reason: "Updated package label" }),
      ]));
      for (const [, init] of corrections) {
        expect(new Headers(init?.headers).get("x-csrf-token")).toBe("test-csrf-token");
        expect(new Headers(init?.headers).get("idempotency-key")).toBeTruthy();
      }
    });
  });

  it("switches between edit and a live preview of the draft recipe", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(() => response(recipe));
    renderRoute(<RecipeEditorPage />, "/app/recipes/new");
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Recipe title"), "Sheet pan chicken");
    const firstIngredient = screen.getByLabelText("ingredient 1 for main recipe");
    await user.click(firstIngredient);
    await user.paste("1 chicken breast\n2 cups rice");
    const firstStep = screen.getByLabelText("step 1 for main recipe");
    await user.click(firstStep);
    await user.paste("Roast the chicken.\nRest before serving.");

    await user.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByRole("heading", { name: "Sheet pan chicken" })).toBeVisible();
    expect(screen.getByText("1 chicken breast")).toBeVisible();
    expect(screen.getByText("2 cups rice")).toBeVisible();
    expect(screen.getByText("Roast the chicken.", { selector: "li" })).toBeVisible();
    expect(screen.getByText("Rest before serving.", { selector: "li" })).toBeVisible();
    expect(screen.getByText("1 serving")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Recipe title")).toHaveValue("Sheet pan chicken");
    expect(screen.getByLabelText("ingredient 1 for main recipe")).toHaveValue("1 chicken breast");
    expect(screen.getByLabelText("ingredient 2 for main recipe")).toHaveValue("2 cups rice");
  });

  it("surfaces provisional estimates in the editor review list", async () => {
    const provisionalRecipe = {
      ...recipe,
      ingredients: [
        {
          ...recipe.ingredients[0],
          matchStatus: "unmatched",
          resolutionKind: "provisional",
          candidateEvidence: [
            { foodReferenceId: "00000000-0000-4000-8000-000000000010" },
            { foodReferenceId: "00000000-0000-4000-8000-000000000011" },
          ],
        },
      ],
    };
    vi.mocked(fetch).mockImplementation(() => response(provisionalRecipe));
    renderRoute(<RecipeEditorPage />, `/app/recipes/${recipe.id}/edit`);

    await screen.findByDisplayValue("Exact oats");
    expect(screen.getByText("Improve nutrition matches")).toBeInTheDocument();
    expect(screen.getByText(/provisional estimate from 2 foods/i)).toBeInTheDocument();
  });

  it("polls visible work after two seconds and recovers authoritative state after reload", async () => {
    vi.useFakeTimers();
    const running: Job = {
      id: "00000000-0000-4000-8000-000000000003",
      kind: "recipe.nutrition",
      aggregateId: recipe.id,
      status: "running",
      attempt: 1,
      maxAttempts: 3,
      inputHash: "abc",
      progressCurrent: 1,
      progressTotal: 2,
      nextRetryAt: null,
      terminalDeadlineAt: "2026-08-10T10:05:00Z",
      failureCode: null,
      failureMessage: null,
      createdAt: "2026-08-10T10:00:00Z",
      finishedAt: null,
      pollAfterSeconds: 2,
      recoveryActions: [],
    };
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) =>
      String(input).includes("/jobs/")
        ? response({ ...running, status: "succeeded", pollAfterSeconds: null })
        : response({ ...recipe, status: "processing", activeJob: running }),
    );
    renderRoute(<RecipeDetailPage />);
    await act(async () => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText(/calculating nutrition/i)).toBeVisible();
    const before = fetchMock.mock.calls.length;
    await act(async () => vi.advanceTimersByTimeAsync(2_000));
    expect(fetchMock.mock.calls.length).toBeGreaterThan(before);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes(`/jobs/${running.id}`))).toBe(true);
  });

  it("reduces active-job polling to fifteen seconds while the page is hidden", async () => {
    vi.useFakeTimers();
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    const running = {
      ...recipe,
      status: "processing" as const,
      activeJob: {
        id: "00000000-0000-4000-8000-000000000003",
        kind: "recipe.nutrition",
        aggregateId: recipe.id,
        status: "running" as const,
        attempt: 1,
        maxAttempts: 3,
        inputHash: "abc",
        progressCurrent: 1,
        progressTotal: 2,
        nextRetryAt: null,
        terminalDeadlineAt: "2026-08-10T10:05:00Z",
        failureCode: null,
        failureMessage: null,
        createdAt: "2026-08-10T10:00:00Z",
        finishedAt: null,
        pollAfterSeconds: 2,
        recoveryActions: [],
      },
    };
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(() => response(running));
    renderRoute(<RecipeDetailPage />);
    await act(async () => vi.advanceTimersByTimeAsync(0));
    const before = fetchMock.mock.calls.length;
    await act(async () => vi.advanceTimersByTimeAsync(14_999));
    expect(fetchMock.mock.calls).toHaveLength(before);
    await act(async () => vi.advanceTimersByTimeAsync(1_001));
    expect(fetchMock.mock.calls.length).toBeGreaterThan(before);
  });

  it("shows bounded retry timing, deadlines, failure recovery, and stale-yield actions", async () => {
    const retryJob: Job = {
      id: "00000000-0000-4000-8000-000000000003",
      kind: "recipe.nutrition",
      aggregateId: recipe.id,
      status: "retry_wait",
      attempt: 2,
      maxAttempts: 3,
      inputHash: "abc",
      progressCurrent: null,
      progressTotal: null,
      nextRetryAt: "2026-08-10T10:02:00Z",
      terminalDeadlineAt: "2026-08-10T10:05:00Z",
      failureCode: "provider_timeout",
      failureMessage: "Reference lookup timed out.",
      createdAt: "2026-08-10T10:00:00Z",
      finishedAt: null,
      pollAfterSeconds: 2,
      recoveryActions: ["wait", "edit_recipe"],
    };
    vi.mocked(fetch).mockImplementation((input) =>
      String(input).includes("/jobs/")
        ? response(retryJob)
        : response({ ...recipe, nutritionState: "stale", activeJob: retryJob }),
    );
    renderRoute(<RecipeDetailPage />);
    expect(await screen.findByText(/nutrition will retry automatically/i)).toBeVisible();
    await userEvent.click(screen.getByText("Nutrition details and evidence"));
    expect(screen.getByText(/attempt 2 of 3/i)).toBeVisible();
    expect(screen.getByText(/next retry/i)).toBeVisible();
    expect(screen.getByText(/deadline/i)).toBeVisible();
    expect(screen.getByRole("button", { name: /recalculate nutrition/i })).toBeVisible();
    expect(screen.getByRole("link", { name: /edit recipe/i })).toBeVisible();
  });

  it("archives and restores using the current quoted version", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      if (init?.method === "DELETE") return response(null, 204);
      if (String(input).endsWith("/restore")) return response({ ...recipe, status: "ready", version: 5 });
      return response({ ...recipe, status: "archived", archivedFromStatus: "ready", version: 4 });
    });
    renderRoute(<RecipeDetailPage />);
    await screen.findByRole("heading", { name: "Exact oats" });
    await userEvent.click(screen.getByText("More recipe options"));
    await userEvent.click(screen.getByRole("button", { name: "Restore recipe" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/restore"));
      expect(new Headers(call?.[1]?.headers).get("if-match")).toBe('"4"');
    });
  });

  it("requires explicit confirmation before permanent deletion and explains retained history", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) =>
      init?.method === "DELETE" && String(input).endsWith("/permanent")
        ? response(null, 204)
        : response({ ...recipe, status: "archived", archivedFromStatus: "ready", version: 4 }),
    );
    renderRoute(<RecipeDetailPage />);
    await screen.findByRole("heading", { name: "Exact oats" });
    const user = userEvent.setup();
    await user.click(screen.getByText("More recipe options"));
    await user.click(screen.getByRole("button", { name: "Permanently delete recipe" }));
    expect(screen.getByText(/historical plan and grocery records remain detached/i)).toBeVisible();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true));
  });
});
