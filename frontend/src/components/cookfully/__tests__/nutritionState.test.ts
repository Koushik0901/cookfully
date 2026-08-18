import { describe, expect, it } from "vitest";

import { nutritionPresentation } from "../nutritionState";

describe("nutritionPresentation", () => {
  it.each([
    ["estimated", undefined, "ready", "Ready"],
    ["source_provided", undefined, "ready", "Ready"],
    ["stale", "manual", "needs_review", "Needs review"],
    ["partial", undefined, "needs_review", "Needs review"],
    ["pending", undefined, "updating", "Updating"],
    ["processing", undefined, "updating", "Updating"],
    ["retry_wait", undefined, "updating", "Updating"],
    ["failed", undefined, "unavailable", "Unavailable"],
    ["unavailable", undefined, "unavailable", "Unavailable"],
    ["estimated", "manual", "manual", "Manual"],
  ])("maps %s/%s to %s", (state, nutritionStatus, key, label) => {
    expect(nutritionPresentation(state, nutritionStatus)).toMatchObject({ key, label });
  });
});
