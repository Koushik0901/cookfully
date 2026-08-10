import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("introduces the nutrition-first product", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Vigor & Vine" })).toBeInTheDocument();
    expect(screen.getByText(/honest, correctable macro plans/i)).toBeInTheDocument();
  });
});

