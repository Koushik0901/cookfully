import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JobsTab } from "../JobsTab";

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
}

describe("settings jobs", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=jobs-csrf; path=/";
    vi.stubGlobal(
      "fetch",
      vi.fn((input, init) => {
        const path = String(input);
        if (path.includes("/recipes?") && !init?.method) {
          return json({
            items: [
              { id: "recipe-ready", status: "ready", nutritionState: "estimated" },
              { id: "recipe-missing", status: "partial", nutritionState: "partial" },
            ],
            nextCursor: null,
          });
        }
        if (path.includes("/reference-data/status")) {
          return json({ available: true, missing: [], releases: [], requestedDatasets: [], job: null });
        }
        if (path.includes("/jobs/recipe-processing")) {
          return json({ active: 0, waiting: 0, missing: 1, pollAfterSeconds: null });
        }
        if (path.includes("/nutrition/recalculate") && init?.method === "POST") {
          return json({ jobId: "job-1", resourceId: "recipe-missing", status: "queued" });
        }
        return json({}, 404);
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("shows real queue counts and can queue only missing recipe work", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <JobsTab />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Recipe processing" })).toBeVisible();
    expect((await screen.findAllByText("Missing", { selector: "span" })).length).toBe(2);

    const user = userEvent.setup();
    const missingButtons = screen.getAllByRole("button", { name: "Run missing only" });
    await waitFor(() => expect(missingButtons[0]).not.toBeDisabled());
    await user.click(missingButtons[0]);

    expect(await screen.findByText("Queued 1 recipe for processing.")).toBeVisible();
    expect(vi.mocked(fetch).mock.calls.some(([input, init]) => String(input).includes("/nutrition/recalculate") && init?.method === "POST")).toBe(true);
  });
});
