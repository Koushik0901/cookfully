import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { recipesApi } from "../api";
import { SubstituteDisclosure } from "../SubstituteDisclosure";

function renderSwap() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SubstituteDisclosure recipeId="r1" ingredientId="i1" />
    </QueryClientProvider>,
  );
}

describe("SubstituteDisclosure", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("asks for swaps only when opened and shows the ranked fit", async () => {
    const spy = vi.spyOn(recipesApi, "substitutes").mockResolvedValue({
      ingredientId: "i1",
      originalText: "1 cup buttermilk",
      ranked: true,
      substitutes: [{ name: "Kefir", amount: "Same amount", note: "", probability: "0.87" }],
    });
    const user = userEvent.setup();
    renderSwap();
    expect(spy).not.toHaveBeenCalled();
    await user.click(screen.getByText("Swap"));
    expect(await screen.findByText("Kefir")).toBeInTheDocument();
    expect(screen.getByText("87% fit for this recipe")).toBeInTheDocument();
    expect(spy).toHaveBeenCalledWith("r1", "i1");
  });

  it("says when swaps are unranked or there are none", async () => {
    vi.spyOn(recipesApi, "substitutes").mockResolvedValue({
      ingredientId: "i1",
      originalText: "2 eggs",
      ranked: false,
      substitutes: [{ name: "Flax egg", amount: "1 tbsp per egg", note: "Rest 10 minutes.", probability: null }],
    });
    const user = userEvent.setup();
    renderSwap();
    await user.click(screen.getByText("Swap"));
    expect(await screen.findByText(/Not ranked for this recipe/)).toBeInTheDocument();
  });
});
