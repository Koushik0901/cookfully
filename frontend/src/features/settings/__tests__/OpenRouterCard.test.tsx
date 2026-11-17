import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OpenRouterCard } from "../OpenRouterCard";

type Feature = { purpose: string; enabled: boolean; models: string[] };

type Settings = {
  keyConfigured: boolean;
  keyHint: string | null;
  cleanupModel: string;
  decisionAssistToleranceDv: string;
  decisionFeatures: Feature[];
  monthlyCapUsd: string;
  spentThisMonthUsd: string;
  version: number;
};

const panel = ["typesafe/jev-1.14", "cloudflare/clef"];

const base: Settings = {
  keyConfigured: false,
  keyHint: null,
  cleanupModel: "",
  decisionAssistToleranceDv: "0.08",
  decisionFeatures: [
    { purpose: "match_referee", enabled: true, models: panel },
    { purpose: "shelf_life", enabled: true, models: panel },
  ],
  monthlyCapUsd: "2",
  spentThisMonthUsd: "0.00042",
  version: 1,
};

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OpenRouterCard />
    </QueryClientProvider>,
  );
}

describe("OpenRouter settings card", () => {
  let current: Settings = base;
  let bodies: Record<string, unknown>[] = [];

  beforeEach(() => {
    current = base;
    bodies = [];
    document.cookie = "cookfully_csrf=csrf; path=/";
    vi.stubGlobal(
      "fetch",
      vi.fn((_input, init?: RequestInit) => {
        if (init?.method === "PUT") {
          const body = JSON.parse(String(init.body)) as Record<string, unknown>;
          bodies.push(body);
          current = {
            ...current,
            keyConfigured: body.clearApiKey ? false : Boolean(body.apiKey) || current.keyConfigured,
            keyHint: body.clearApiKey ? null : body.apiKey ? "wxyz" : current.keyHint,
            version: current.version + 1,
          };
        }
        return json(current);
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("saves a key write-only and then shows only its hint", async () => {
    const user = userEvent.setup();
    renderCard();
    const keyInput = await screen.findByLabelText("API key");
    expect(keyInput).toHaveAttribute("type", "password");
    await user.type(keyInput, "sk-or-secret-wxyz");
    await user.click(screen.getByRole("button", { name: "Save key and settings" }));

    await screen.findByText("OpenRouter settings saved.");
    expect(bodies[0]).toMatchObject({ apiKey: "sk-or-secret-wxyz", clearApiKey: false, version: 1 });
    expect(bodies[0]?.decisionAssistToleranceDv).toBe("0.0800");
    expect(bodies[0]?.monthlyCapUsd).toBe("2.00");
    expect(bodies[0]?.decisionFeatures).toEqual(base.decisionFeatures);
    await waitFor(() => expect(screen.getByText(/ending in wxyz/)).toBeInTheDocument());
    expect(screen.getByLabelText("API key")).toHaveValue("");
    expect(document.body.textContent).not.toContain("sk-or-secret-wxyz");
  });

  it("omits the key when only settings change and can remove a saved key", async () => {
    current = { ...base, keyConfigured: true, keyHint: "wxyz" };
    const user = userEvent.setup();
    renderCard();
    const model = await screen.findByLabelText("Ingredient matching models");
    await user.clear(model);
    await user.type(model, "cloudflare/clef");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByText("OpenRouter settings saved.");
    expect(bodies[0]).not.toHaveProperty("apiKey");
    expect(bodies[0]).toMatchObject({ clearApiKey: false });
    expect(bodies[0]?.decisionFeatures).toContainEqual({
      purpose: "match_referee",
      enabled: true,
      models: ["cloudflare/clef"],
    });

    await user.click(screen.getByRole("button", { name: "Remove key" }));
    await waitFor(() => expect(bodies[1]).toMatchObject({ clearApiKey: true }));
    await screen.findByText("No key saved.");
  });

  it("shows spend against the cap and switches a feature off", async () => {
    const user = userEvent.setup();
    renderCard();
    expect(await screen.findByText(/\$0\.0004 spent this month/)).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Shelf life/ }));
    expect(screen.getByLabelText("Shelf life models")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByText("OpenRouter settings saved.");
    expect(bodies[0]?.decisionFeatures).toContainEqual({ purpose: "shelf_life", enabled: false, models: panel });
  });

  it("blocks invalid model lists and caps", async () => {
    const user = userEvent.setup();
    renderCard();
    const models = await screen.findByLabelText("Shelf life models");
    await user.clear(models);
    expect(screen.getByText("Add at least one model or switch this off.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
    await user.type(models, "a/b, a/b");
    expect(screen.getByText("A model is listed twice.")).toBeInTheDocument();
    await user.clear(models);
    await user.type(models, "a/b, c/d, e/f, g/h");
    expect(screen.getByText("Use at most 3 models.")).toBeInTheDocument();
    await user.clear(models);
    await user.type(models, "bad model!");
    expect(screen.getByText("Use model ids like provider/model.")).toBeInTheDocument();
    await user.clear(models);
    await user.type(models, "a/b");
    expect(screen.getByRole("button", { name: "Save settings" })).toBeEnabled();
    const cap = screen.getByLabelText(/Monthly spend cap/);
    await user.clear(cap);
    await user.type(cap, "500");
    expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
  });

  it("blocks an out-of-range tolerance", async () => {
    const user = userEvent.setup();
    renderCard();
    const tolerance = await screen.findByLabelText(/Auto-resolve tolerance/);
    await user.clear(tolerance);
    await user.type(tolerance, "50");
    expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
  });
});
