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
      assumptions: [],
    },
  ],
  instructions: ["Mix and chill."],
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

function renderRoute(element: React.ReactNode, path = "/app/recipes/00000000-0000-4000-8000-000000000001") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
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

  it("renders a keyboard-accessible card with human-readable nutrition", async () => {
    const onArchive = vi.fn();
    render(
      <MemoryRouter>
        <RecipeCard recipe={recipe as Recipe} onArchive={onArchive} onRestore={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Exact oats" })).toHaveAttribute(
      "href",
      `/app/recipes/${recipe.id}`,
    );
    expect(screen.getByText("512 kcal")).toBeVisible();
    expect(screen.getByText("31.1 g")).toBeVisible();
    expect(document.querySelector('[data-fallback-kind="breakfast"]')).toHaveAttribute("src", "/media/recipe-fallbacks/breakfast.jpg");
    expect(screen.getByText("estimated", { selector: ".recipe-card__state" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /archive exact oats/i }));
    expect(onArchive).toHaveBeenCalledWith(recipe.id, 3);
  });

  it("labels manually corrected nutrition consistently on recipe cards", () => {
    render(
      <MemoryRouter>
        <RecipeCard recipe={{ ...recipe, nutrition: { ...recipe.nutrition!, status: "manual" } } as Recipe} onArchive={vi.fn()} onRestore={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("manual", { selector: ".recipe-card__state" })).toBeVisible();
  });

  it("keeps a real recipe image ahead of generated fallback art", () => {
    render(
      <MemoryRouter>
        <RecipeCard recipe={{ ...recipe, imageUrl: "/media/actual-recipe.jpg" } as Recipe} onArchive={vi.fn()} onRestore={vi.fn()} />
      </MemoryRouter>,
    );
    expect(document.querySelector(".recipe-card__media img")).toHaveAttribute("src", "/media/actual-recipe.jpg");
    expect(document.querySelector(".recipe-fallback-art")).not.toBeInTheDocument();
  });

  it("guides cooking as a focused step flow with an ingredient checklist and completion moment", async () => {
    vi.mocked(fetch).mockImplementation(() => response({
      ...recipe,
      instructions: ["Mix the oats.", "Chill and serve."],
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

    await user.click(screen.getByRole("button", { name: "Cook again" }));
    expect(screen.getByText("Mix the oats.")).toBeVisible();
  });

  it("keeps stale lifecycle warnings ahead of manual provenance on recipe cards", () => {
    render(
      <MemoryRouter>
        <RecipeCard recipe={{ ...recipe, nutritionState: "stale", nutrition: { ...recipe.nutrition!, status: "manual" } } as Recipe} onArchive={vi.fn()} onRestore={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("stale", { selector: ".recipe-card__state" })).toBeVisible();
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
    await user.type(screen.getByLabelText("Ingredients, one per line"), "1 1/4 cups rolled oats");
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
    expect(screen.getByText(/planning aid, not medical advice/i)).toBeVisible();
    expect(screen.getByText("Basis: 2.5 servings · Coverage: 88%")).toBeVisible();
    await userEvent.click(screen.getByText(/what the nutrition status means/i));
    expect(screen.getByText(/calculated from matched ingredients/i)).toBeVisible();
    expect(screen.getByText(/percentage of quantified ingredients/i)).toBeVisible();
    expect(screen.getByText("USDA Foundation Foods")).toBeVisible();
    expect(screen.getByText("8.5 g")).toBeVisible();
    expect(screen.getByText(/0 mg · source-reported zero/i)).toBeVisible();
    expect(screen.getAllByText(/USDA 1079/).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByText("Ingredient matching and assumptions"));
    expect(screen.getByText(/level tablespoon/i)).toBeVisible();
    expect(screen.getByText(/package label/i)).toBeVisible();
    expect(screen.getByText("1.25 cups rolled oats")).toBeVisible();
  });

  it("creates and resets a correction with CSRF and idempotency headers", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      if (String(input).includes("/nutrition/corrections") && init?.method === "POST") {
        return response({ ...recipe.nutrition, status: "manual" });
      }
      if (String(input).includes("/nutrition/corrections/") && init?.method === "DELETE") {
        return response({ ...recipe.nutrition, corrections: [] });
      }
      return response({ ...recipe, nutritionState: "stale" });
    });
    renderRoute(<RecipeDetailPage />);
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Exact oats" });
    await user.selectOptions(screen.getByLabelText("Nutrition field"), "protein_g");
    await user.type(screen.getByLabelText("Corrected decimal value"), "32.000000");
    await user.type(screen.getByLabelText("Correction reason"), "Updated label");
    await user.click(screen.getByRole("button", { name: "Apply correction" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(new Headers(call?.[1]?.headers).get("x-csrf-token")).toBe("test-csrf-token");
      expect(new Headers(call?.[1]?.headers).get("idempotency-key")).toBeTruthy();
      expect(screen.getByText("stale", { selector: ".nutrition-state" })).toBeVisible();
      expect(screen.getByText(/nutrition is stale because/i)).toBeVisible();
    });
    await user.click(screen.getByRole("button", { name: /reset protein_g correction/i }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true));
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
    expect(screen.getByText("running")).toBeVisible();
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
    vi.mocked(fetch).mockImplementation(() =>
      response({ ...recipe, nutritionState: "stale", activeJob: retryJob }),
    );
    renderRoute(<RecipeDetailPage />);
    expect(await screen.findByText(/attempt 2 of 3/i)).toBeVisible();
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
    await user.click(screen.getByRole("button", { name: "Permanently delete recipe" }));
    expect(screen.getByText(/historical plan and grocery records remain detached/i)).toBeVisible();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true));
  });
});
