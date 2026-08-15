import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NutritionDataTab } from "../NutritionDataTab";

function json(value: unknown) {
  return { ok: true, status: 200, json: async () => value } as Response;
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NutritionDataTab />
    </QueryClientProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("NutritionDataTab", () => {
  it("shows missing datasets and install buttons when nothing is installed", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({
      available: false,
      missing: ["foundation", "sr_legacy"],
      releases: [],
      requestedDatasets: null,
      job: null,
    })));
    renderTab();
    expect(await screen.findByText("Foundation + SR Legacy")).toBeVisible();
    expect(screen.getByRole("button", { name: "Install Foundation + SR Legacy" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Install Branded foods" })).toBeVisible();
  });

  it("shows active releases with license and disables installed buttons", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({
      available: true,
      missing: [],
      releases: [
        { datasetType: "foundation", releaseId: "foundation-2024-04", releasedOn: "2024-04-18", sourceUrl: "https://fdc.nal.usda.gov/fdc-datasets.html", license: "CC0-1.0", reviewOverdue: false },
        { datasetType: "sr_legacy", releaseId: "sr-legacy-2018-04", releasedOn: "2018-04-01", sourceUrl: "https://fdc.nal.usda.gov/fdc-datasets.html", license: "CC0-1.0", reviewOverdue: false },
      ],
      requestedDatasets: null,
      job: null,
    })));
    renderTab();
    expect(await screen.findByText("CC0-1.0")).toBeVisible();
    expect(screen.getByRole("button", { name: "Install Foundation + SR Legacy" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Install Branded foods" })).toBeEnabled();
  });

  it("posts the selected datasets on install", async () => {
    const fetchMock = vi.fn(async () => json({
      available: false, missing: ["foundation", "sr_legacy"], releases: [],
      requestedDatasets: null, job: null,
    }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderTab();
    await screen.findByText("Foundation + SR Legacy");
    await user.click(screen.getByRole("button", { name: "Install Foundation + SR Legacy" }));
    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([input]) => String(input).includes("/reference-data/install"));
      expect(call).toBeDefined();
      const [, init] = call as [unknown, RequestInit];
      expect(init.method).toBe("POST");
      expect(JSON.parse(String(init.body))).toEqual({ datasets: ["foundation_sr_legacy"] });
    });
  });

  it("shows progress while a job is running", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      calls += 1;
      return json({
        available: false, missing: ["foundation", "sr_legacy"], releases: [],
        requestedDatasets: ["foundation_sr_legacy"],
        job: {
          id: "00000000-0000-4000-8000-000000000001", kind: "reference_data_install",
          aggregateId: "00000000-0000-4000-8000-000000000002", status: "running", attempt: 1,
          maxAttempts: 5, inputHash: "sha256:abc", progressCurrent: 1, progressTotal: 2,
          nextRetryAt: null, terminalDeadlineAt: "2026-08-15T00:00:00Z",
          failureCode: null, failureMessage: null, createdAt: "2026-08-15T00:00:00Z",
          finishedAt: null, pollAfterSeconds: 2, recoveryActions: [],
        },
      });
    }));
    renderTab();
    expect(await screen.findByText(/Installing/)).toBeVisible();
    expect(calls).toBeGreaterThanOrEqual(1);
  });
});