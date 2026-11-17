import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { AvoidBadge, AvoidWarningsProvider } from "../../plans/avoidWarnings";
import type { MealPlan } from "../../plans/types";
import { AvoidNotice } from "../AvoidNotice";
import type { RecipeDetail } from "../types";

const recipe = {
  id: "r1",
  ingredients: [
    { id: "i1", originalText: "150 g shrimp" },
    { id: "i2", originalText: "2 tbsp Worcestershire sauce" },
  ],
  avoidWarnings: [
    { ingredientId: "i1", item: "shellfish", source: "ingredient", probability: null },
    { ingredientId: "i2", item: "fish", source: "model", probability: "0.91" },
  ],
} as unknown as RecipeDetail;

afterEach(cleanup);

describe("avoid-list warnings", () => {
  it("lists named and model-suspected items with their lines", () => {
    render(<MemoryRouter><AvoidNotice recipe={recipe} /></MemoryRouter>);
    expect(screen.getByText("On your avoid list")).toBeInTheDocument();
    expect(screen.getByText("shellfish: 150 g shrimp")).toBeInTheDocument();
    expect(screen.getByText(/May contain fish: 2 tbsp Worcestershire sauce \(91%\), suggested by a decision model/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit avoid list" })).toHaveAttribute("href", "/app/goals");
  });

  it("renders nothing without warnings", () => {
    const { container } = render(<MemoryRouter><AvoidNotice recipe={{ ...recipe, avoidWarnings: [] }} /></MemoryRouter>);
    expect(container).toBeEmptyDOMElement();
  });

  it("badges planned meals whose recipe has warnings", () => {
    const plan = { avoidWarnings: [{ recipeId: "r1", items: ["shellfish", "peanuts"] }] } as unknown as MealPlan;
    render(
      <AvoidWarningsProvider plan={plan}>
        <AvoidBadge recipeId="r1" />
        <AvoidBadge recipeId="r2" />
      </AvoidWarningsProvider>,
    );
    expect(screen.getAllByRole("note")).toHaveLength(1);
    expect(screen.getByText("Contains shellfish, peanuts")).toBeInTheDocument();
  });
});
