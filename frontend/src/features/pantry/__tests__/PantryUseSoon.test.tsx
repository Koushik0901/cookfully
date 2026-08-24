/* eslint-disable @typescript-eslint/no-explicit-any */
import { cleanup, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { daysLeft, expiryBadge } from "../expiry";

describe("pantry expiry helper", () => {
  it("daysLeft calculates correctly", () => {
    expect(daysLeft("2026-08-29", "2026-08-24")).toBe(5);
    expect(daysLeft("2026-08-24", "2026-08-24")).toBe(0);
    expect(daysLeft("2026-08-23", "2026-08-24")).toBe(-1);
    expect(daysLeft("2026-08-26", "2026-08-24")).toBe(2);
  });

  it("expiryBadge tones and labels", () => {
    expect(expiryBadge("2026-08-23", "2026-08-24")).toEqual({ label: "Expired 1d ago", tone: "danger" });
    expect(expiryBadge("2026-08-24", "2026-08-24").tone).toBe("amber");
    expect(expiryBadge("2026-08-24", "2026-08-24").label).toMatch(/Use soon/);
    expect(expiryBadge("2026-08-25", "2026-08-24").tone).toBe("amber");
    expect(expiryBadge("2026-08-27", "2026-08-24").label).toMatch(/Expires in 3d/);
    expect(expiryBadge("2026-08-29", "2026-08-24").tone).toBe("mint");
    expect(expiryBadge("2026-08-30", "2026-08-24").label).toBe("Expires 2026-08-30");
  });

  it("sorts pantry by expiresOn with nulls last", () => {
    const items = [
      { displayName: "Rice", expiresOn: null },
      { displayName: "Milk", expiresOn: "2026-08-25" },
      { displayName: "Tomatoes", expiresOn: "2026-08-24" },
      { displayName: "Cheese", expiresOn: "2026-08-23" },
    ] as any[];
    const sorted = items.slice().sort((a, b) => (a.expiresOn ? 0 : 1) - (b.expiresOn ? 0 : 1) || (a.expiresOn || "").localeCompare(b.expiresOn || ""));
    expect(sorted.map((i) => i.displayName)).toEqual(["Cheese", "Tomatoes", "Milk", "Rice"]);
  });
});

describe("pantry use-soon chips and sort", () => {
  beforeEach(() => {
    vi.setSystemTime(new Date("2026-08-24T12:00:00Z"));
    vi.stubGlobal("fetch", vi.fn((input) => {
      const path = String(input);
      if (path.includes("/owner/preferences")) {
        return Promise.resolve(
          new Response(JSON.stringify({ displayName: "Owner", timezone: "UTC", weekStartsOn: 1, version: 1 }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }
      if (path.includes("/pantry-items") && !path.includes("recipe-matches")) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                id: "1",
                displayName: "Milk",
                normalizedFoodName: "milk",
                quantity: "1",
                unit: "l",
                expiresOn: "2026-08-25",
                foodReferenceId: null,
                matchStatus: "matched",
                matchConfidence: null,
                version: 1,
                purchasedAt: null,
                expirySource: "label",
              },
              {
                id: "2",
                displayName: "Rice",
                normalizedFoodName: "rice",
                quantity: "1",
                unit: "kg",
                expiresOn: null,
                foodReferenceId: null,
                matchStatus: "matched",
                matchConfidence: null,
                version: 1,
                purchasedAt: null,
                expirySource: null,
              },
              {
                id: "3",
                displayName: "Tomatoes",
                normalizedFoodName: "tomato",
                quantity: "500",
                unit: "g",
                expiresOn: "2026-08-24",
                foodReferenceId: null,
                matchStatus: "matched",
                matchConfidence: null,
                version: 1,
                purchasedAt: null,
                expirySource: "auto",
              },
            ]),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      if (path.includes("/pantry/recipe-matches")) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "content-type": "application/json" } }));
      }
      if (path.includes("/recipes")) {
        return Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "content-type": "application/json" } }));
      }
      return Promise.resolve(new Response(JSON.stringify({}), { status: 404, headers: { "content-type": "application/json" } }));
    }));
    document.cookie = "cookfully_csrf=test; path=/";
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders pantry sorted with expiry chips", async () => {
    const { PantryPage } = await import("../PantryPage");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PantryPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // wait for items to load — Tomatoes appears in both attention row and shelf card
    expect((await screen.findAllByText("Tomatoes")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Milk").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Rice").length).toBeGreaterThanOrEqual(1);

    // chips should appear with expiry tone classes
    const chips = document.querySelectorAll("[class*='expiry-chip']");
    // at least two dated items should have chips
    expect(chips.length).toBeGreaterThanOrEqual(2);

    // verify amber/mint tones exist
    const chipClasses = Array.from(chips).map((el) => el.className).join(" ");
    expect(chipClasses).toMatch(/expiry-chip--(amber|mint|danger)/);

    // verify sorted order: dated items first sorted ascending, undated last
    //Tomatoes (2026-08-24) should appear before Milk (2026-08-25) and Rice (null) last
    const cards = Array.from(document.querySelectorAll(".pantry-staple"));
    const titles = cards.map((card) => within(card as HTMLElement).getByRole("heading", { level: 3 }).textContent);
    const tomatoIdx = titles.indexOf("Tomatoes");
    const milkIdx = titles.indexOf("Milk");
    const riceIdx = titles.indexOf("Rice");
    expect(tomatoIdx).toBeLessThan(milkIdx);
    expect(milkIdx).toBeLessThan(riceIdx);

    // chip labels use expiryBadge logic
    expect(screen.getAllByText(/Use soon/).length).toBeGreaterThanOrEqual(2);
    expect(document.querySelector(".expiry-chip--amber")).toBeInTheDocument();
  });

  it("shows danger chip for expired item", async () => {
    // override fetch for this test: expired item
    vi.mocked(fetch).mockImplementation((input) => {
      const path = String(input);
      if (path.includes("/owner/preferences")) {
        return Promise.resolve(new Response(JSON.stringify({ displayName: "Owner", timezone: "UTC", weekStartsOn: 1, version: 1 }), { status: 200, headers: { "content-type": "application/json" } }));
      }
      if (path.includes("/pantry-items")) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                id: "9",
                displayName: "Berries",
                normalizedFoodName: "berries",
                quantity: "200",
                unit: "g",
                expiresOn: "2026-08-23",
                foodReferenceId: null,
                matchStatus: "matched",
                matchConfidence: null,
                version: 1,
                purchasedAt: null,
                expirySource: "auto",
              },
            ]),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        );
      }
      if (path.includes("/pantry/recipe-matches")) return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
      if (path.includes("/recipes")) return Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify({}), { status: 404 }));
    });

    const { PantryPage: PantryPage2 } = await import("../PantryPage");
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PantryPage2 />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect((await screen.findAllByText("Berries")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Expired 1d ago/)).toBeInTheDocument();
    expect(document.querySelector(".expiry-chip--danger")).toBeInTheDocument();
  });
});
