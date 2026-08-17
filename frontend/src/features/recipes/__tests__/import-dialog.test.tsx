import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ImportPreview } from "../types";
import { RecipeImportDialog } from "../RecipeImportDialog";

const preview: ImportPreview = {
  parseId: "parse-0001",
  title: "Shawarma bowl",
  yieldQuantity: null,
  yieldText: null,
  imageSources: [],
  duplicates: [{ id: "00000000-0000-4000-8000-000000000001", title: "Shawarma bowl", version: 4 }],
  sections: [
    {
      title: "The chicken",
      ingredients: [
        { originalText: "1 lb chicken breast", needsQuantity: false },
        { originalText: "olive oil", needsQuantity: true },
      ],
      instructions: ["Season the chicken."],
    },
  ],
};

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const onImported = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/app/recipes"]}>
        <Routes>
          <Route path="/app/recipes" element={<RecipeImportDialog trigger={<button>Import</button>} onImported={onImported} />} />
          <Route path="/app/recipes/:recipeId" element={<div>Recipe detail</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onImported };
}

async function openPreview(merge: { recipeId: string; parseId: string; expectedVersion: number; title: string; yieldQuantity: string | null; components: unknown[] }) {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Import" }));
  await user.type(screen.getByLabelText("Recipe or cookbook URL"), "https://example.com/shawarma");
  const fetchMock = vi.mocked(fetch);
  fetchMock.mockImplementation(async (input, init) => {
    const path = String(input);
    if (path.endsWith("/import/preview") && init?.method === "POST") return response(preview);
    if (path.endsWith("/import/merge") && init?.method === "POST") {
      Object.assign(merge, JSON.parse(String(init.body)));
      return response({ jobId: "job-0001", resourceId: merge.recipeId, status: "queued" }, 202);
    }
    return response({});
  });
  await user.click(screen.getByRole("button", { name: "Start import" }));
  await screen.findByText(/It looks like you already have/);
  return user;
}

describe("recipe import merge", () => {
  beforeEach(() => {
    document.cookie = "cookfully_csrf=test-csrf-token; path=/";
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("posts a merge with the existing recipe id, expected version, and reviewed draft", async () => {
    const merge = { recipeId: "", parseId: "", expectedVersion: 0, title: "", yieldQuantity: null as string | null, components: [] as unknown[] };
    renderDialog();
    const user = await openPreview(merge);

    await user.click(screen.getByRole("button", { name: "Merge into existing" }));

    await waitFor(() => expect(merge.recipeId).toBe("00000000-0000-4000-8000-000000000001"));
    expect(merge.parseId).toBe("parse-0001");
    expect(merge.expectedVersion).toBe(4);
    expect(merge.title).toBe("Shawarma bowl");
    expect(merge.components).toHaveLength(1);
    const component = merge.components[0] as { title: string; ingredients: { originalText: string }[] };
    expect(component.title).toBe("The chicken");
    expect(component.ingredients).toHaveLength(2);
    expect(merge.components).toBeInstanceOf(Array);
  });

  it("shows a merge action for every reported duplicate", async () => {
    renderDialog();
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith("/import/preview") && init?.method === "POST") {
        return response({
          ...preview,
          duplicates: [
            { id: "00000000-0000-4000-8000-000000000001", title: "Old shawarma", version: 2 },
            { id: "00000000-0000-4000-8000-000000000002", title: "Earlier shawarma", version: 9 },
          ],
        });
      }
      return response({ jobId: "job-0001", resourceId: "00000000-0000-4000-8000-000000000001", status: "queued" }, 202);
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Import" }));
    await user.type(screen.getByLabelText("Recipe or cookbook URL"), "https://example.com/shawarma");
    await user.click(screen.getByRole("button", { name: "Start import" }));
await screen.findByText(/It looks like you already have/);

    expect(screen.getAllByRole("button", { name: "Merge into existing" })).toHaveLength(2);
  });
});
