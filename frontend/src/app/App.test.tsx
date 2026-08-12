import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("introduces the nutrition-first product on the landing page", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Good food. Clear choices. Your kind of healthy." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Cookfully" })).toBeInTheDocument();
    expect(screen.getByText(/bring in a recipe/i)).toBeInTheDocument();
  });
});

