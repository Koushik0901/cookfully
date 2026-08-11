import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("introduces the nutrition-first product on the landing page", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Recipes become honest, correctable macro plans." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the planner" })).toBeInTheDocument();
    expect(screen.getByText(/import from anywhere/i)).toBeInTheDocument();
  });
});

