import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { Job } from "../types";
import { RecipeProcessingBanner } from "../RecipeProcessingBanner";

const job: Job = {
  id: "job-1",
  kind: "nutrition_match",
  aggregateId: "recipe-1",
  status: "running",
  attempt: 1,
  maxAttempts: 5,
  inputHash: "sha256:test",
  progressCurrent: 1,
  progressTotal: 2,
  nextRetryAt: null,
  terminalDeadlineAt: "2026-08-16T20:00:00Z",
  failureCode: null,
  failureMessage: null,
  createdAt: "2026-08-16T19:45:00Z",
  finishedAt: null,
  pollAfterSeconds: 2,
  recoveryActions: [],
};

describe("RecipeProcessingBanner", () => {
  afterEach(cleanup);

  it("explains the current nutrition stage and progress in plain language", () => {
    render(<RecipeProcessingBanner job={job} nutritionState="pending" />);

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Matching nutrition");
    expect(screen.getByRole("progressbar")).toHaveAccessibleName("1 of 2 ingredients");
    expect(status.textContent?.match(/1 of 2 ingredients/g)).toHaveLength(1);
    expect(screen.getByText(/working in the background/i)).toBeVisible();
  });

  it("keeps a failed estimate quiet but gives the owner a clear next action", () => {
    render(
      <MemoryRouter>
        <RecipeProcessingBanner
          job={{ ...job, status: "failed", failureMessage: "Model unavailable" }}
          nutritionState="unavailable"
          reviewHref="/app/recipes/recipe-1/edit#nutrition"
        />
      </MemoryRouter>,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Nutrition not available");
    expect(screen.getByRole("link", { name: /review nutrition/i })).toHaveAttribute(
      "href",
      "/app/recipes/recipe-1/edit#nutrition",
    );
    expect(status).not.toHaveTextContent("Model unavailable");
  });
});
