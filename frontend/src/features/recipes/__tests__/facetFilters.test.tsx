import { afterEach, describe, expect, it, vi } from "vitest";

import { recipesApi } from "../api";

describe("recipe facet filters", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends each selected facet as a repeated query parameter", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "content-type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    await recipesApi.list({ facets: ["vegetarian", "freezes_well"] });
    const url = String((fetchMock.mock.calls[0] as unknown as [string])[0]);
    expect(new URL(url, "http://x").searchParams.getAll("facet")).toEqual(["vegetarian", "freezes_well"]);
  });
});
