import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
  it("explains the current nutrition stage and progress in plain language", () => {
    render(<RecipeProcessingBanner job={job} nutritionState="pending" />);

    expect(screen.getByRole("status")).toHaveTextContent("Matching nutrition");
    expect(screen.getByRole("progressbar")).toHaveAccessibleName("1 of 2 ingredients");
    expect(screen.getByText(/you can keep using the recipe/i)).toBeVisible();
  });
});
