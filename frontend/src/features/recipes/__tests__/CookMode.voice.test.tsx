import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CookMode } from "../CookMode";
import { intelligenceApi } from "../../intelligence/api";

vi.mock("../../intelligence/api", () => ({
  intelligenceApi: {
    infer: vi.fn(),
    createDraft: vi.fn(),
    executeDraft: vi.fn(),
    getDraft: vi.fn(),
    createExtractionJob: vi.fn(),
  },
}));

const mockRecipe = {
  title: "Garlic Soup",
  ingredients: ["2 cloves garlic", "1 tsp salt", "200ml water"],
  instructions: ["Chop garlic finely", "Boil water with salt", "Add garlic and simmer"],
};

function renderCook(recipe = mockRecipe, currentStep = 0) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CookMode recipe={recipe} currentStep={currentStep} />
    </QueryClientProvider>,
  );
}

describe("CookMode voice-ready handler", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    cleanup();
  });

  it("cook timer 5 starts timer", async () => {
    vi.mocked(intelligenceApi.infer).mockResolvedValue({
      status: "ok",
      confidence: 0.9,
      functionCalls: [{ name: "cooking_action", arguments: { action: "timer", minutes: 5 } }],
      model: "test",
      reasoning: null,
      errorCode: null,
    } as never);
    renderCook(mockRecipe, 0);
    fireEvent.click(screen.getByText(/timer 5/i));
    await waitFor(() => expect(screen.getByRole("status", { name: "Timer 5 min" })).toBeInTheDocument());
    // prompt shape verification
    expect(intelligenceApi.infer).toHaveBeenCalledWith("cook", expect.stringContaining("Step: Chop garlic finely"));
    expect(intelligenceApi.infer).toHaveBeenCalledWith("cook", expect.stringContaining("Ingredients: 2 cloves garlic"));
    expect(intelligenceApi.infer).toHaveBeenCalledWith("cook", expect.stringContaining("User: timer 5"));
  });

  it("how much garlic answers only when evidenced", async () => {
    vi.mocked(intelligenceApi.infer).mockResolvedValue({
      status: "ok",
      confidence: 0.88,
      functionCalls: [{ name: "cooking_action", arguments: { action: "repeat", query: "garlic" } }],
      model: "test",
      reasoning: null,
      errorCode: null,
    } as never);
    renderCook(mockRecipe, 0);
    fireEvent.click(screen.getByText(/how much garlic/i));
    expect(await screen.findByText("2 cloves garlic")).toBeInTheDocument();
  });

  it("does not show answer chip when query not evidenced (fallback to step)", async () => {
    vi.mocked(intelligenceApi.infer).mockResolvedValue({
      status: "ok",
      confidence: 0.88,
      functionCalls: [{ name: "cooking_action", arguments: { action: "repeat", query: "saffron" } }],
      model: "test",
      reasoning: null,
      errorCode: null,
    } as never);
    const recipeNoGarlic = { ...mockRecipe, ingredients: ["1 tsp salt"] };
    renderCook(recipeNoGarlic, 0);
    fireEvent.click(screen.getByText(/how much garlic/i));
    // wait for mutation to settle
    await waitFor(() => expect(intelligenceApi.infer).toHaveBeenCalled());
    // saffron not in ingredients, so no chip; step text still visible
    expect(screen.queryByText("2 cloves garlic")).not.toBeInTheDocument();
    expect(screen.getByText("Chop garlic finely")).toBeInTheDocument();
  });

  it("manual timer starts even when optional voice interpretation is low confidence", async () => {
    vi.mocked(intelligenceApi.infer).mockResolvedValue({
      status: "ok",
      confidence: 0.6,
      functionCalls: [{ name: "cooking_action", arguments: { action: "timer", minutes: 5 } }],
      model: "test",
      reasoning: null,
      errorCode: null,
    } as never);
    renderCook(mockRecipe, 0);
    fireEvent.click(screen.getByText(/timer 5/i));
    await waitFor(() => expect(intelligenceApi.infer).toHaveBeenCalled());
    expect(screen.getByRole("status", { name: "Timer 5 min" })).toBeInTheDocument();
  });

  it("next advances step when confident", async () => {
    vi.mocked(intelligenceApi.infer).mockResolvedValue({
      status: "ok",
      confidence: 0.9,
      functionCalls: [{ name: "cooking_action", arguments: { action: "next" } }],
      model: "test",
      reasoning: null,
      errorCode: null,
    } as never);
    renderCook(mockRecipe, 0);
    expect(screen.getByText("Chop garlic finely")).toBeInTheDocument();
    fireEvent.click(screen.getByText(/^next$/i));
    await waitFor(() => expect(screen.getByText("Boil water with salt")).toBeInTheDocument());
  });
});
