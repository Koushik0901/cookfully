import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OpenRouterCard } from "../OpenRouterCard";

type Settings = {
  keyConfigured: boolean;
  keyHint: string | null;
  cleanupModel: string;
  decisionAssistEnabled: boolean;
  decisionAssistModel: string;
  decisionAssistToleranceDv: string;
  version: number;
};

const base: Settings = {
  keyConfigured: false,
  keyHint: null,
  cleanupModel: "",
  decisionAssistEnabled: true,
  decisionAssistModel: "typesafe/jev-1.14",
  decisionAssistToleranceDv: "0.020000",
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
    expect(bodies[0]?.decisionAssistToleranceDv).toBe("0.0200");
    await waitFor(() => expect(screen.getByText(/ending in wxyz/)).toBeInTheDocument());
    expect(screen.getByLabelText("API key")).toHaveValue("");
    expect(document.body.textContent).not.toContain("sk-or-secret-wxyz");
  });

  it("omits the key when only settings change and can remove a saved key", async () => {
    current = { ...base, keyConfigured: true, keyHint: "wxyz" };
    const user = userEvent.setup();
    renderCard();
    const model = await screen.findByLabelText("Matching model");
    await user.clear(model);
    await user.type(model, "cloudflare/clef");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByText("OpenRouter settings saved.");
    expect(bodies[0]).not.toHaveProperty("apiKey");
    expect(bodies[0]).toMatchObject({ decisionAssistModel: "cloudflare/clef", clearApiKey: false });

    await user.click(screen.getByRole("button", { name: "Remove key" }));
    await waitFor(() => expect(bodies[1]).toMatchObject({ clearApiKey: true }));
    await screen.findByText("No key saved.");
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
