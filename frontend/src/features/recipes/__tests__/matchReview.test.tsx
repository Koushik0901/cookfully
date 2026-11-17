import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { foodsApi } from "../../foods/api";
import { ModelPickButton } from "../ModelPickButton";
import { modelPick, reviewImpact, reviewOrder, reviewSummary } from "../matchReview";
import type { RecipeDetail } from "../types";

type Ingredient = RecipeDetail["ingredients"][number];

function ingredient(id: string, overrides: Partial<Ingredient> = {}): Ingredient {
  return {
    id,
    position: 0,
    originalText: id,
    optional: false,
    parseStatus: "parsed",
    matchStatus: "ambiguous",
    candidateEvidence: [],
    assumptions: [],
    ...overrides,
  } as Ingredient;
}

function referee(impactDv: string | null, pick: Record<string, string> | null = null) {
  return { kind: "match_referee", action: "keep", impactDv, pick };
}

describe("match review helpers", () => {
  it("reads the models' pick only from referee evidence with usable fields", () => {
    const pick = { foodReferenceId: "f1", description: "Butter, salted", probability: "0.8731" };
    expect(modelPick(ingredient("a", { candidateEvidence: [referee("0.1", pick)] }))).toEqual({
      foodReferenceId: "f1",
      description: "Butter, salted",
      probability: 0.8731,
    });
    expect(modelPick(ingredient("b", { candidateEvidence: [{ kind: "decision_assist", pick }] }))).toBeNull();
    expect(modelPick(ingredient("c", { candidateEvidence: [referee("0.1", { ...pick, probability: "x" })] }))).toBeNull();
    expect(modelPick(ingredient("d"))).toBeNull();
  });

  it("orders review lines by nutrition at stake, then keeps recipe order", () => {
    const items = [
      ingredient("matched", { matchStatus: "matched" }),
      ingredient("no-evidence-1"),
      ingredient("small", { candidateEvidence: [referee("0.01")] }),
      ingredient("no-evidence-2", { matchStatus: "unmatched" }),
      ingredient("large", { candidateEvidence: [referee("0.4")] }),
      ingredient("unknown", { candidateEvidence: [referee(null)] }),
    ];
    expect(reviewOrder(items).map((item) => item.id)).toEqual([
      "large",
      "small",
      "no-evidence-1",
      "no-evidence-2",
      "unknown",
    ]);
    expect(reviewImpact(items[4]!)).toBe(0.4);
  });

  it("summarizes each review state", () => {
    expect(reviewSummary(ingredient("a"))).toBe("Several possible foods");
    expect(reviewSummary(ingredient("b", { matchStatus: "unmatched" }))).toBe("No food selected yet");
    expect(reviewSummary(ingredient("c", { resolutionKind: "provisional", candidateEvidence: [{}, {}] }))).toBe(
      "Estimated from 2 possible foods",
    );
  });
});

describe("ModelPickButton", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("confirms the models' pick in one tap and remembers it like a manual choice", async () => {
    const select = vi.spyOn(foodsApi, "selectIngredientFood").mockResolvedValue({ jobId: "job-1" } as never);
    const onSelected = vi.fn();
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ModelPickButton
          recipeId="r1"
          ingredientId="i1"
          pick={{ foodReferenceId: "f1", description: "Rice, white, cooked", probability: 0.92 }}
          onSelected={onSelected}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Model pick · 92%/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Use Rice, white, cooked" }));
    await waitFor(() => expect(onSelected).toHaveBeenCalledWith({ jobId: "job-1" }));
    expect(select).toHaveBeenCalledWith("r1", "i1", "f1", true);
  });
});
