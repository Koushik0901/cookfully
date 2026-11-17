import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { foodLabelsApi } from "../api";
import { FoodLabelsPanel } from "../FoodLabelsPanel";

function renderPanel(enabled = true) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <FoodLabelsPanel enabled={enabled} />
    </QueryClientProvider>,
  );
}

describe("FoodLabelsPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows coverage and starts a labelling run", async () => {
    vi.spyOn(foodLabelsApi, "summary").mockResolvedValue({ labelled: 2000, total: 8000, active: 0, waiting: 0, pollAfterSeconds: null });
    const run = vi.spyOn(foodLabelsApi, "run").mockResolvedValue({ jobId: "j1", status: "queued" });
    const user = userEvent.setup();
    renderPanel();
    expect(await screen.findByText(/2,000 of 8,000 USDA foods labelled \(25%\)/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Label foods now/ }));
    await waitFor(() => expect(run).toHaveBeenCalled());
  });

  it("is disabled while running or when the feature cannot run", async () => {
    vi.spyOn(foodLabelsApi, "summary").mockResolvedValue({ labelled: 10, total: 100, active: 1, waiting: 0, pollAfterSeconds: 2 });
    renderPanel();
    expect(await screen.findByRole("button", { name: /Labelling…/ })).toBeDisabled();
    cleanup();
    vi.spyOn(foodLabelsApi, "summary").mockResolvedValue({ labelled: 0, total: 100, active: 0, waiting: 0, pollAfterSeconds: null });
    renderPanel(false);
    expect(await screen.findByRole("button", { name: /Label foods now/ })).toBeDisabled();
  });
});
